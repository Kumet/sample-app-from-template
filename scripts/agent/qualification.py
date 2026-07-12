from __future__ import annotations

from pathlib import Path

from .adapters import detect, load_adapters


def qualify(repo: Path) -> dict[str, str]:
    adapters = load_adapters(repo)
    results = {}
    for name in ("python", "node", "go"):
        selected, evidence = detect(repo / "fixtures" / name, adapters)
        if selected.name != name:
            raise ValueError(f"{name} fixture selected {selected.name}")
        results[name] = ",".join(evidence)
    return results
