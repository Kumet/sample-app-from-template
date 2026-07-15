from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
MAKEFILE = PROJECT_ROOT / "Makefile"


def _target_rule(makefile: str, target: str) -> tuple[str, list[str]]:
    lines = makefile.splitlines()
    rule_index = next(
        index for index, line in enumerate(lines) if line.startswith(f"{target}:")
    )
    recipes: list[str] = []
    for line in lines[rule_index + 1 :]:
        if not line.startswith("\t"):
            break
        recipes.append(line.removeprefix("\t"))
    return lines[rule_index], recipes


def test_container_targets_are_explicit_phony_entry_points() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    phony = next(line for line in makefile.splitlines() if line.startswith(".PHONY:"))

    assert "container-build" in phony.split()
    assert "container-smoke" in phony.split()
    assert _target_rule(makefile, "container-build") == (
        "container-build:",
        ["docker build --tag local-project-board:local ."],
    )
    assert _target_rule(makefile, "container-smoke") == (
        "container-smoke:",
        ["$(PYTHON) scripts/operations/container_smoke.py"],
    )


def test_ordinary_validation_remains_container_independent() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert _target_rule(makefile, "validate") == (
        "validate: quality-check secrets ci",
        [],
    )
    for target in ("ci", "test", "test-app", "test-framework", "integration-test"):
        rule, recipes = _target_rule(makefile, target)
        contract = "\n".join([rule, *recipes])
        assert "container-build" not in contract
        assert "container-smoke" not in contract
