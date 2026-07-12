from __future__ import annotations

import tomllib
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Adapter:
    name: str
    markers: tuple[str, ...]
    targets: dict[str, str]
    fallback: str | None
    commands: dict[str, tuple[str, ...]] | None = None
    tool_markers: tuple[str, ...] = ()


def load_adapters(repo: Path) -> list[Adapter]:
    values = []
    for path in sorted((repo / "adapters").glob("*.toml")):
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        commands = {name: tuple(command) for name, command in raw.get("commands", {}).items()}
        values.append(Adapter(raw["name"], tuple(raw["markers"]), dict(raw["targets"]),
                              raw.get("fallback"), commands, tuple(raw.get("tool_markers", ()))))
    return values


def detect(repo: Path, adapters: list[Adapter]) -> tuple[Adapter, tuple[str, ...]]:
    matches = []
    for adapter in adapters:
        evidence = tuple(marker for marker in adapter.markers if (repo / marker).exists())
        if evidence:
            matches.append((adapter, evidence))
    specific = [item for item in matches if item[0].name != "generic"]
    if len(specific) > 1:
        names = ", ".join(item[0].name for item in specific)
        raise ValueError(f"Ambiguous stack detection: {names}")
    if specific:
        return specific[0]
    if matches:
        return matches[0]
    generic = next((a for a in adapters if a.name == "generic"), None)
    if generic:
        return generic, ()
    raise ValueError("No stack adapter detected")


def render_make_proposal(adapter: Adapter) -> str:
    lines = [f"# Proposed targets for stack: {adapter.name}"]
    if adapter.commands:
        for target, command in adapter.commands.items():
            lines.extend((f"{target}:", f"\t{shlex.join(command)}", ""))
    else:
        for validation, target in adapter.targets.items():
            lines.extend((f"{target}:", f'\t@echo "TODO: configure {adapter.name} {validation}"', ""))
    return "\n".join(lines).rstrip() + "\n"


def write_proposal(repo: Path, adapter: Adapter) -> Path:
    output = repo / f"Makefile.{adapter.name}.proposed"
    if output.exists():
        raise ValueError(f"Refusing to overwrite {output.name}")
    output.write_text(render_make_proposal(adapter), encoding="utf-8")
    return output
