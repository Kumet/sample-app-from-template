from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from . import git_utils, validation, worktree
from .events import Event, EventStore
from .evidence import redact
from .parser import WorkConfig, resolve_feature
from .state import RunState, contract_digest, read_state, write_state


MAX_APPROVED_PATHS = 32
MAX_CHANGED_PATHS = 128
MAX_PATH_LENGTH = 240
MAX_REASON_LENGTH = 500
EVENT_DATA_LIMIT = 3500
SENSITIVE_DIRECTORIES = {".ssh", ".aws", ".azure", ".gnupg", ".kube"}
SENSITIVE_FILENAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    ".dockerconfigjson",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


@dataclass(frozen=True)
class RecoveryInspection:
    feature: str
    state_status: str
    state_task: str | None
    failure_class: str | None
    worktree: str
    ownership_valid: bool
    branch: str
    branch_match: bool
    saved_head: str
    current_head: str
    head_match: bool
    saved_contract_digest: str
    current_contract_digest: str
    contract_match: bool
    prior_changed_paths: tuple[str, ...]
    approved_paths: tuple[str, ...]
    current_changed_paths: tuple[str, ...]
    paths_match: bool
    diff_digest: str
    can_apply: bool
    blocking_reasons: tuple[str, ...]

    def payload(self) -> dict:
        value = asdict(self)
        value["planned_mutations"] = (
            [
                "append recovery approval evidence",
                "re-attribute saved state",
                "append recovery application evidence",
            ]
            if self.can_apply
            else []
        )
        return value


def parse_approved_paths(value: str) -> tuple[str, ...]:
    raw = value.split()
    if not raw:
        raise ValueError("At least one approved recovery path is required")
    if len(raw) > MAX_APPROVED_PATHS:
        raise ValueError("Too many approved recovery paths")
    paths = tuple(sorted(set(_normalize_path(path) for path in raw)))
    if len(paths) != len(raw):
        raise ValueError("Approved recovery paths must be unique")
    return paths


def preview(
    repo: Path,
    feature_dir: Path,
    config: WorkConfig,
    approved_paths: tuple[str, ...],
    reason: str,
) -> dict:
    _validate_reason(reason)
    return inspect(repo, feature_dir, config, approved_paths).payload()


def apply(
    repo: Path,
    feature_dir: Path,
    config: WorkConfig,
    approved_paths: tuple[str, ...],
    reason: str,
) -> dict:
    _validate_reason(reason)
    inspection = inspect(repo, feature_dir, config, approved_paths)
    if not inspection.can_apply:
        raise ValueError(
            "Recovery patch cannot be approved: "
            + "; ".join(inspection.blocking_reasons)
        )
    state_path = repo / ".agent-work" / feature_dir.name / "state.json"
    events = EventStore(repo / ".agent-work" / feature_dir.name / "events.jsonl")
    saved = read_state(state_path)
    proposed_at = dt.datetime.now(dt.UTC).isoformat()
    data = _binding_data(inspection, proposed_at)
    _require_bounded_event_data(data)
    approval = events.append(
        feature=feature_dir.name,
        repository=str(repo),
        branch=inspection.branch,
        worktree=inspection.worktree,
        phase="approval",
        kind="recovery-patch-approved",
        result="PASS",
        head_sha=inspection.current_head,
        detail=redact(reason, MAX_REASON_LENGTH),
        data=data,
    )
    confirmed = inspect(repo, feature_dir, config, approved_paths)
    if confirmed != inspection:
        raise ValueError("Recovery patch changed after approval evidence was recorded")
    updated = replace(
        saved,
        head_commit=inspection.current_head,
        changed_paths=inspection.current_changed_paths,
        updated_at=proposed_at,
        recovery_event_sequence=approval.sequence,
        recovery_diff_digest=inspection.diff_digest,
    )
    write_state(state_path, updated)
    applied = events.append(
        feature=feature_dir.name,
        repository=str(repo),
        branch=inspection.branch,
        worktree=inspection.worktree,
        phase="approval",
        kind="recovery-patch-applied",
        result="PASS",
        head_sha=inspection.current_head,
        detail="Approved recovery patch re-attributed to failed state",
        data={
            **data,
            "approval_event_sequence": approval.sequence,
        },
    )
    result = inspection.payload()
    result.update(
        {
            "state_updated_at": proposed_at,
            "approval_event_sequence": approval.sequence,
            "applied_event_sequence": applied.sequence,
        }
    )
    return result


def inspect(
    repo: Path,
    feature_dir: Path,
    config: WorkConfig,
    approved_paths: tuple[str, ...],
) -> RecoveryInspection:
    approved_paths = tuple(sorted(_normalize_path(path) for path in approved_paths))
    if not approved_paths or len(approved_paths) > MAX_APPROVED_PATHS:
        raise ValueError("Approved recovery paths are empty or exceed the limit")
    if len(set(approved_paths)) != len(approved_paths):
        raise ValueError("Approved recovery paths must be unique")
    validation.validate_scope(list(approved_paths), config)
    state_path = repo / ".agent-work" / feature_dir.name / "state.json"
    saved = read_state(state_path)
    expected = repo / ".agent-worktrees" / feature_dir.name
    blockers: list[str] = []
    if saved.feature != feature_dir.name:
        blockers.append("saved state names another feature")
    if saved.status != "failed":
        blockers.append("recovery re-attribution requires failed state")
    if saved.recovery_event_sequence is not None:
        blockers.append("saved state already has active recovery evidence")
    try:
        saved_path = Path(saved.worktree)
        path_match = (
            saved_path.is_absolute()
            and saved_path == expected.absolute()
            and saved_path.exists()
            and saved_path.resolve() == expected.resolve()
        )
    except (OSError, RuntimeError):
        path_match = False
    if not path_match:
        blockers.append("saved state names another worktree")
    owned = path_match and worktree.owns_registered_worktree(
        repo, expected, feature_dir.name
    )
    if not owned:
        blockers.append("worktree ownership is invalid")
    try:
        current_branch = git_utils.branch(expected) if path_match else ""
        current_head = (
            git_utils.run_git(expected, ["rev-parse", "HEAD"]).stdout.strip()
            if path_match
            else ""
        )
        current_paths = tuple(
            git_utils.changed_paths_read_only(expected) if path_match else ()
        )
    except Exception as error:
        blockers.append(f"worktree Git inspection failed: {type(error).__name__}")
        current_branch, current_head, current_paths = "", "", ()
    branch_match = current_branch == saved.branch
    head_match = current_head == saved.head_commit
    if not branch_match:
        blockers.append("worktree branch differs from saved state")
    if not head_match:
        blockers.append("worktree HEAD differs from saved state")
    try:
        isolated_feature = resolve_feature(expected, feature_dir.name)
        current_contract = contract_digest(isolated_feature)
    except Exception as error:
        blockers.append(f"worktree contract inspection failed: {type(error).__name__}")
        current_contract = ""
    contract_match = current_contract == saved.contract_digest
    if not contract_match:
        blockers.append("feature contract differs from saved state")
    prior_paths = tuple(sorted(saved.changed_paths))
    current_paths = tuple(sorted(current_paths))
    if len(current_paths) > MAX_CHANGED_PATHS:
        blockers.append("current changed paths exceed the recovery inspection limit")
    added_paths = tuple(sorted(set(current_paths) - set(prior_paths)))
    removed_paths = tuple(sorted(set(prior_paths) - set(current_paths)))
    paths_match = added_paths == approved_paths and not removed_paths
    if not paths_match:
        blockers.append("approved paths do not exactly match newly changed paths")
    try:
        validation.validate_scope(list(current_paths), config)
    except ValueError as error:
        blockers.append(str(error))
    try:
        digest = diff_digest(expected, current_paths) if path_match else ""
    except (OSError, ValueError, git_utils.GitError) as error:
        blockers.append(f"recovery diff inspection failed: {type(error).__name__}")
        digest = ""
    return RecoveryInspection(
        feature_dir.name,
        saved.status,
        saved.task,
        saved.failure_class,
        str(expected.absolute()),
        owned,
        current_branch,
        branch_match,
        saved.head_commit,
        current_head,
        head_match,
        saved.contract_digest,
        current_contract,
        contract_match,
        prior_paths,
        approved_paths,
        current_paths,
        paths_match,
        digest,
        not blockers,
        tuple(blockers),
    )


def diff_digest(repo: Path, paths: tuple[str, ...]) -> str:
    normalized = tuple(sorted(_normalize_path(path) for path in paths))
    if len(normalized) > MAX_CHANGED_PATHS:
        raise ValueError("Too many changed paths for recovery diff inspection")
    digest = hashlib.sha256()
    digest.update(b"approved-recovery-diff-v1\0")
    for path in normalized:
        digest.update(path.encode("utf-8") + b"\0")
    for args in (
        ["diff", "--raw", "-z", "--no-ext-diff", "HEAD", "--", *normalized],
        [
            "diff",
            "--raw",
            "-z",
            "--no-ext-diff",
            "--cached",
            "HEAD",
            "--",
            *normalized,
        ],
    ):
        result = _run_git_bytes(repo, args)
        digest.update(len(result).to_bytes(8, "big"))
        digest.update(result)
    for path in normalized:
        candidate = repo / path
        try:
            status = candidate.lstat()
        except FileNotFoundError:
            digest.update(b"missing\0")
            continue
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise ValueError("Recovery paths must be private regular files")
        digest.update(f"mode:{stat.S_IMODE(status.st_mode):o}\0".encode())
        with candidate.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def verify_active_evidence(
    repo: Path,
    feature_dir: Path,
    saved: RunState,
    current_branch: str | None,
    current_head: str | None,
    current_paths: list[str],
) -> tuple[str, ...]:
    if saved.recovery_event_sequence is None and saved.recovery_diff_digest is None:
        return ()
    if saved.recovery_event_sequence is None or not saved.recovery_diff_digest:
        return ("saved recovery evidence binding is incomplete",)
    blockers: list[str] = []
    expected_worktree = repo / ".agent-worktrees" / feature_dir.name
    try:
        saved_worktree = Path(saved.worktree)
        worktree_valid = (
            saved_worktree.is_absolute()
            and saved_worktree == expected_worktree.absolute()
            and saved_worktree.exists()
            and saved_worktree.resolve() == expected_worktree.resolve()
            and worktree.owns_registered_worktree(
                repo, expected_worktree, feature_dir.name
            )
        )
    except (OSError, RuntimeError):
        worktree_valid = False
    if not worktree_valid:
        return ("active recovery evidence names an invalid worktree",)
    events = EventStore(
        repo / ".agent-work" / feature_dir.name / "events.jsonl"
    ).read()
    approval = _event_at(events, saved.recovery_event_sequence)
    if approval is None or not _valid_approval_event(approval, saved, repo):
        blockers.append("saved recovery approval evidence is missing or invalid")
    applied = next(
        (
            event
            for event in events
            if event.kind == "recovery-patch-applied"
            and event.result == "PASS"
            and isinstance(event.data, dict)
            and type(event.data.get("approval_event_sequence")) is int
            and event.data.get("approval_event_sequence") == saved.recovery_event_sequence
        ),
        None,
    )
    if applied is None:
        blockers.append("recovery state update lacks applied evidence")
    expected_paths = tuple(sorted(saved.changed_paths))
    if tuple(sorted(current_paths)) != expected_paths:
        blockers.append("recovery changed paths differ from re-attributed state")
    if current_branch != saved.branch or current_head != saved.head_commit:
        blockers.append("recovery branch or HEAD binding changed")
    try:
        current_digest = diff_digest(expected_worktree, expected_paths)
    except (OSError, ValueError, git_utils.GitError):
        current_digest = ""
    if current_digest != saved.recovery_diff_digest:
        blockers.append("recovery diff changed after approval")
    if approval is not None and isinstance(approval.data, dict):
        comparisons = {
            "feature": saved.feature,
            "branch": saved.branch,
            "saved_head": saved.head_commit,
            "current_head": saved.head_commit,
            "contract_digest": saved.contract_digest,
            "worktree": saved.worktree,
            "current_changed_paths": list(expected_paths),
            "diff_digest": saved.recovery_diff_digest,
            "state_updated_at": saved.updated_at,
            "ownership_valid": True,
        }
        if any(approval.data.get(key) != value for key, value in comparisons.items()):
            blockers.append("recovery approval evidence does not match saved state")
        prior = approval.data.get("prior_changed_paths")
        approved = approval.data.get("approved_paths")
        if (
            not isinstance(prior, list)
            or not isinstance(approved, list)
            or not approved
            or not all(isinstance(path, str) for path in prior + approved)
            or set(prior) & set(approved)
            or sorted(prior + approved) != list(expected_paths)
        ):
            blockers.append("recovery approval path attribution is invalid")
        if applied is not None and (
            applied.feature != saved.feature
            or applied.repository != str(repo)
            or applied.branch != saved.branch
            or applied.worktree != saved.worktree
            or applied.phase != "approval"
            or applied.head_sha != saved.head_commit
            or not isinstance(applied.data, dict)
            or any(applied.data.get(key) != value for key, value in comparisons.items())
            or {
                key: value
                for key, value in applied.data.items()
                if key != "approval_event_sequence"
            }
            != approval.data
        ):
            blockers.append("recovery applied evidence does not match saved state")
    return tuple(dict.fromkeys(blockers))


def _binding_data(inspection: RecoveryInspection, updated_at: str) -> dict:
    return {
        "feature": inspection.feature,
        "branch": inspection.branch,
        "saved_head": inspection.saved_head,
        "current_head": inspection.current_head,
        "contract_digest": inspection.current_contract_digest,
        "worktree": inspection.worktree,
        "ownership_valid": inspection.ownership_valid,
        "prior_changed_paths": list(inspection.prior_changed_paths),
        "approved_paths": list(inspection.approved_paths),
        "current_changed_paths": list(inspection.current_changed_paths),
        "diff_digest": inspection.diff_digest,
        "state_updated_at": updated_at,
    }


def _valid_approval_event(event: Event, saved: RunState, repo: Path) -> bool:
    return (
        event.feature == saved.feature
        and event.repository == str(repo)
        and event.branch == saved.branch
        and event.worktree == saved.worktree
        and event.phase == "approval"
        and event.kind == "recovery-patch-approved"
        and event.result == "PASS"
        and event.head_sha == saved.head_commit
        and isinstance(event.data, dict)
    )


def _event_at(events: list[Event], sequence: int) -> Event | None:
    return events[sequence - 1] if 0 < sequence <= len(events) else None


def _normalize_path(path: str) -> str:
    if (
        not path
        or len(path) > MAX_PATH_LENGTH
        or path.startswith("/")
        or "\\" in path
        or any(character in path for character in "*?[")
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        raise ValueError("Invalid approved recovery path")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Invalid approved recovery path")
    if any(
        part in {".agent-work", ".agent-worktrees", ".agent-worktree-owned"}
        for part in parts
    ):
        raise ValueError("Runtime paths cannot be approved as recovery paths")
    lowered = [part.lower() for part in parts]
    filename = lowered[-1]
    if (
        any(part in SENSITIVE_DIRECTORIES for part in lowered)
        or filename in SENSITIVE_FILENAMES
        or filename == ".env"
        or filename.startswith(".env.")
        or any(filename.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)
        or filename.startswith(("credentials.", "secrets."))
    ):
        raise ValueError("Sensitive paths cannot be approved as recovery paths")
    return path


def _validate_reason(reason: str) -> None:
    if not reason.strip() or len(reason) > MAX_REASON_LENGTH:
        raise ValueError("A bounded recovery approval reason is required")
    if any(ord(character) < 32 and character not in "\t\n" for character in reason):
        raise ValueError("Recovery approval reason contains control characters")


def _require_bounded_event_data(data: dict) -> None:
    if len(json.dumps(data, sort_keys=True).encode("utf-8")) > EVENT_DATA_LIMIT:
        raise ValueError("Recovery approval evidence exceeds the bounded event size")


def _run_git_bytes(repo: Path, args: list[str]) -> bytes:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, check=False
    )
    if result.returncode:
        raise git_utils.GitError(
            result.stderr.decode("utf-8", errors="replace").strip()
            or "git recovery diff failed"
        )
    return result.stdout
