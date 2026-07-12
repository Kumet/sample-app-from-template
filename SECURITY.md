# Security policy

## AI agent safety rules

AI agents must not:

- Read `.env`, credentials, private keys, tokens, or secret files.
- Execute `curl | bash` or remote scripts without human review.
- Modify GitHub Actions secrets or repository security settings.
- Access production databases or production services.
- Run destructive commands such as `rm -rf` without explicit approval.
- Weaken tests to make validation pass.

## Reporting security issues

Open a private security advisory or contact the repository owner directly.
Do not disclose vulnerabilities in public issues.
