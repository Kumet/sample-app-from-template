from __future__ import annotations


REQUIRED = ("lint", "typecheck", "test", "build")


def validate(settings: dict) -> list[str]:
    errors = []
    for name in REQUIRED:
        value = settings.get(name)
        if not isinstance(value, dict):
            errors.append(f"Missing quality gate policy: {name}")
        elif value.get("enabled") is not True and not str(value.get("reason", "")).strip():
            errors.append(f"Disabled quality gate requires reason: {name}")
    return errors
