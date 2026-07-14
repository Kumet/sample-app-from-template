# Validation log: 021-container-validation-target-policy

## Approved baseline

- Source: human-approved Feature 021 prompt.
- Starting template main: `df7aedf3f3ef4a5223a63c4a80a23c520e292e63`.
- Sample repository: read-only and unchanged.
- Policy strategy: add two exact allowlist entries; do not change
  `scripts/agent/**` or ordinary `make validate` behavior.

## Runs

- Spec lint before implementation: PASS, no warnings.
- Targeted command: `python3.11 -m unittest -v tests.test_spec_lint tests.test_autonomous_core`.
- Repair loop 1: FAIL because the new rejection test referenced an unimported
  `ContractError` name. The assertion was aligned with the existing test style
  by checking its `ValueError` base class; production behavior was unchanged.
- Targeted rerun: PASS, 37 tests.
- Exact container targets, both-target contracts, all legacy targets,
  non-container contracts, exact case-sensitive rejection, injection rejection,
  and Docker-independent `validate` dependencies are covered.
- Full validation on implementation HEAD `460b5dd5cde6255228b9c21d151a0f1eb12fdf19`:
  PASS, including quality policy, secret filename check, and 174 framework tests.
- No Docker command was invoked by `make validate`.
