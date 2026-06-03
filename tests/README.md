# Reasoning Graph Test Packets

Messy/blind test inputs and spoiler validators for reviewing the `reasoning-graph` skill.

## Files

- `prompts/no-skill-ab-prompt.md` — reusable A/B prompt for the normal/no-skill run. Replace `{{PROBLEM_FILE}}` and optional `{{HTML_OUTPUT_FILE}}`.
- `prompts/skill-ab-prompt.md` — reusable A/B prompt for the `reasoning-graph` skill run. Replace `{{PROBLEM_FILE}}` and optional `{{HTML_OUTPUT_FILE}}`.
- `countdown-island/problem.md` — pure countdown-island problem definition: questions + case file only, with no agent/skill prompt and no leading Section 16 notes.
- `countdown-island/problem-harder.md` — harder countdown-island variant with several direct identity/motive clues removed or made ambiguous; use same validator expectation, but score clue recovery more carefully.
- `countdown-island/problem-hardest.md` — stronger discriminator variant with loaded question words and direct identity/motive tells further muddied; use same validator expectation, but expect lower confidence.
- `countdown-island/problem-discriminator.md` — branchier discriminator attempt: identity-substitution, Ada-flight, crawl, motive, and Oren-route evidence are all conflicted/muddied; use same validator expectation, but confidence should be lower and alternative handling matters more.
- `countdown-island/validator.md` — spoiler validator plus withheld leading investigator notes. Do not give to blind solvers.
- `sea-shanty/problem.md` — real-world Gold Bug DC33 / CryptoVillage 2025 Sea Shanty puzzle fixture with local rum-bottle image asset.
- `sea-shanty/validator.md` — spoiler validator for Sea Shanty. Do not give to blind solvers.
- `theo-crypto-v2/problem.md` — text-only cold fixture for a two-line crypto challenge; no validator exists yet because intended plaintext is not independently verified.
- `reasoning-graph-hard-jp-closed-circle-messy-input.md` — hard original Japanese detective-style closed-circle packet.
- `reasoning-graph-hard-jp-closed-circle-validator.md` — spoiler validator for the closed-circle packet. Do not give to blind solvers.
- `reasoning-graph-hard-detective-messy-input.md` — Sherlock-style impossible-room packet.
- `reasoning-graph-sherlock-conan-blind.md` — earlier blind observatory test.
- `reasoning-graph-sherlock-conan-validator.md` — spoiler validator. Do not give to blind solvers.
- `locked-observatory-baseline-blind.md` — baseline prompt used for non-skill comparison.
- `reasoning-graph-strict-good.json` — minimal strict-mode state that should validate/audit.

## Review notes

- Use validator files only after blind runs complete.
- Keep generated outputs separate from these inputs unless they are named clearly as run artifacts.
- A/B output artifacts live in `../test-results/`.
