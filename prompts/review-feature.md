Independently review the supplied approved feature artifacts and Git diff.
Review shard: {review_focus}.
Shard responsibility: {review_guidance}
Review only this assigned responsibility. Do not repeat checks assigned to other
shards.
All required review inputs are embedded below. Do not run commands or inspect
other repository files; evaluate only this bounded input.

<spec path="{spec_path}">
{spec_text}
</spec>

<plan path="{plan_path}">
{plan_text}
</plan>

<tasks path="{tasks_path}">
{tasks_text}
</tasks>

<validation-log>
{validation_text}
</validation-log>

<validation-contract>
{validation_contract_text}
</validation-contract>

<runtime-evidence>
{runtime_evidence_text}
</runtime-evidence>

<evidence-semantics>
{evidence_semantics_text}
</evidence-semantics>

Evidence interpretation is normative: validation-log is a tracked pre-final
snapshot only through its watermark. The snapshot event itself and later
post-evidence events intentionally remain in append-only runtime evidence to
avoid a self-referential tracked commit. Their absence from validation-log is
normal and is not, by itself, stale evidence. Report stale or unattributable
evidence only for an actual mismatch named by the mechanically verified
evidence-semantics object. Only final-validation-accepted/PASS opens the gate;
attempt-only, rejected, ordinary validation, and legacy events do not.

<git-diff>
{diff_text}
</git-diff>

Do not edit files.
This is the pre-push review phase: push, PR creation, CI monitoring, merge-state,
and cleanup happen only after this review passes. Do not report missing evidence
for those future phases as a finding. Review whether the implementation and
current mechanical evidence are ready for those phases.
Return only JSON matching the provided schema. A required finding must describe
a concrete issue that blocks delivery. Return at most five findings. Do not
include credentials or secrets.
