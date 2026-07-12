# Claude bounded loop command

```text
Run a bounded validation loop.

Command: make validate
Maximum loops: 5

Stop if:
- the same error appears twice
- a test would need to be weakened
- scope expansion is required
- a specification change is required
- a security-sensitive file must be touched

After each loop, update validation-log.md with:
- command
- result
- failure summary
- change made
- next action
```
