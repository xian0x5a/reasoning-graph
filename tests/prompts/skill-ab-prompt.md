# Skill A/B Prompt

Use the `reasoning-graph` skill if available. Strict mode is recommended when the problem has misleading reports, ambiguous facts, staged signals, or competing explanations.

Read `{{PROBLEM_FILE}}`, build the reasoning state needed by the skill, and answer the problem questions.

Return a clear user-facing answer. Include enough support to make the answer auditable, but do not force a special user-facing format unless the skill needs internal artifacts for validation.

Also create a standalone reasoning-graph HTML report for review. If file writing is available, save the validated state as JSON, run `scripts/rg.py validate`, run `scripts/rg.py audit` when strict mode/events are used, then generate `{{HTML_OUTPUT_FILE}}` with `scripts/rg.py html`. Do not hand-write a custom HTML summary as the requested graph artifact; if you want a custom page, save it as an extra `*-custom.html` file. If file writing is unavailable, include the state JSON plus Mermaid/HTML output in your response.
