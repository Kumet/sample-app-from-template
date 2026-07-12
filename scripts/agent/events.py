from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .evidence import redact


@dataclass(frozen=True)
class Event:
    version: int
    sequence: int
    timestamp: str
    feature: str
    repository: str
    branch: str
    worktree: str
    phase: str
    kind: str
    result: str
    head_sha: str
    detail: str = ""
    data: dict | None = None


class EventStore:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> list[Event]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        events = []
        for index, line in enumerate(lines):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                if index == len(lines) - 1:
                    break
                raise ValueError(f"Corrupt event at line {index + 1}") from error
            event = Event(**raw)
            if event.version != 1 or event.sequence != len(events) + 1:
                raise ValueError("Invalid event version or sequence")
            events.append(event)
        return events

    def append(
        self,
        *,
        feature: str,
        repository: str,
        branch: str,
        worktree: str,
        phase: str,
        kind: str,
        result: str,
        head_sha: str,
        detail: str = "",
        data: dict | None = None,
    ) -> Event:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._repair_truncated_tail()
            sequence = len(self.read()) + 1
            event = Event(
                1,
                sequence,
                dt.datetime.now(dt.UTC).isoformat(),
                feature,
                repository,
                branch,
                worktree,
                phase,
                kind,
                result,
                head_sha,
                redact(detail, 4000),
                _redact_data(data),
            )
            payload = (json.dumps(asdict(event), sort_keys=True) + "\n").encode()
            descriptor = os.open(
                self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
            )
            try:
                offset = 0
                while offset < len(payload):
                    offset += os.write(descriptor, payload[offset:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)
        return event

    def _repair_truncated_tail(self) -> None:
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        if data and not data.endswith(b"\n"):
            last = data.rfind(b"\n")
            self.path.write_bytes(data[: last + 1] if last >= 0 else b"")


def render_validation_log(
    events: list[Event],
    feature: str,
    validation_contract_digest: str = "",
    generated_at: str | None = None,
) -> str:
    rows = []
    for event in events:
        detail = event.detail.replace("|", "\\|").replace("\n", " ")
        rows.append(
            f"| {event.sequence} | {event.phase}/{event.kind} | "
            f"{event.result} | `{event.head_sha[:12]}` | {detail} |"
        )
    final = events[-1].result if events else "NOT_STARTED"
    metadata = json.dumps(
        {
            "feature": feature,
            "event_schema_version": 1,
            "snapshot_format_version": 2,
            "included_event_sequence": events[-1].sequence if events else 0,
            "generated_at": generated_at or dt.datetime.now(dt.UTC).isoformat(),
            "validation_contract_digest": validation_contract_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        f"# Validation log: {feature}\n<!-- validation-snapshot: {metadata} -->\n\n"
        "This tracked snapshot does not embed its own commit SHA. Its commit "
        "and blob are attributed by the append-only "
        "tracked-evidence-snapshot event.\n\n"
        f"## Summary\n\nFinal included event result: {final}.\n\n"
        "## Runs\n\n| # | Event | Result | HEAD | Notes |\n|---:|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n"
    )


def _redact_data(data: dict | None) -> dict | None:
    if data is None:
        return None
    return {
        str(key): redact(value) if isinstance(value, str) else value
        for key, value in data.items()
    }
