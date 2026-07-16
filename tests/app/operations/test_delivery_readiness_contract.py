import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
VALIDATION_CONTRACT = (
    PROJECT_ROOT
    / "specs"
    / "020-containerized-operational-readiness"
    / "validation.toml"
)


def _contract() -> dict[str, object]:
    with VALIDATION_CONTRACT.open("rb") as contract_file:
        return tomllib.load(contract_file)


def test_delivery_stays_high_risk_bounded_and_human_approved() -> None:
    contract = _contract()

    assert contract["version"] == 2
    assert contract["risk"] == "high"
    assert contract["risk_domains"] == ["infrastructure", "ci"]
    assert contract["auto_merge"] is False
    assert contract["max_final_validation_attempts"] == 3
    assert contract["max_review_attempts"] == 3
    assert contract["max_ci_attempts"] == 3


def test_final_task_requires_full_and_real_container_validation() -> None:
    contract = _contract()
    validations = contract["validations"]
    dependencies = contract["dependencies"]

    assert isinstance(validations, dict)
    assert validations["full"] == "validate"
    assert validations["container-smoke"] == "container-smoke"
    assert validations["full"] != validations["container-smoke"]
    assert isinstance(dependencies, dict)
    assert dependencies["T010"] == ["T008", "T009"]


def test_scope_fail_closes_application_policy_and_prior_evidence() -> None:
    contract = _contract()
    scope = contract["scope"]

    assert isinstance(scope, dict)
    forbidden = set(scope["forbidden"])
    assert {
        "src/project_board/**",
        "pyproject.toml",
        "scripts/agent/**",
        ".agent-policy.toml",
        "migrations/**",
        "specs/001*/**",
        "specs/019*/**",
        ".agent-work/**",
    } <= forbidden


def test_t010_requirements_remain_traceable_to_final_acceptance() -> None:
    contract = _contract()
    traceability = contract["traceability"]

    assert isinstance(traceability, dict)
    expected_acceptance = {
        "REQ-011": {"AC-005", "AC-006", "AC-007"},
        "REQ-012": {"AC-007"},
        "REQ-016": {"AC-002", "AC-012"},
        "REQ-017": {"AC-010", "AC-011"},
        "REQ-018": {"AC-003", "AC-005", "AC-007"},
    }
    for requirement, acceptance_criteria in expected_acceptance.items():
        links = set(traceability[requirement])
        assert "T010" in links
        assert acceptance_criteria <= links
