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
