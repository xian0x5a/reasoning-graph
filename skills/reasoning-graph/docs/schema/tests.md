# Tests and Result Evidence

Use `test` nodes for procedures, checks, experiments, commands, or follow-up actions. A proposed test is not evidence until performed and connected to result evidence.

## Status values

- `proposed` — recommended next verification; not evidence and should not be treated as support
- `performed` — check was conducted; add resulting `evidence` or `derived` nodes and connect them to affected branches
- `inconclusive` — check was conducted but did not settle the claim

Only `test` nodes may use `status`.

## Canonical pattern

```txt
A1 --prompts--> T1
T1 --leads_to--> E9
E9 --supports|contradicts--> A1
```

Meaning:

- `A1` is a claim/assumption that motivates a check.
- `T1` is the procedure.
- `E9` is the observed result.
- The result evidence updates the claim, not the test node itself.

Put `confidence` on result evidence when scripts, OCR, external services, or manual transcription could be wrong.

## Resume after a proposed test

When a proposed test is later conducted:

1. Update the test node `status` to `performed` or `inconclusive`.
2. Add result `evidence` or `derived` nodes when there is a result.
3. Connect result nodes with `supports`, `contradicts`, or `leads_to` as appropriate.
4. Recompute and re-sort active frontier items against latest graph evidence.
5. Keep the original test node so the audit trail shows recommendation-to-result transition.

`evidence_version` may be kept as trace metadata, but active dedupe uses latest evidence and does not include `evidence_version`.

Score changes alone do not reopen exhausted work. If evidence creates new work for an already-visited node, add a new frontier item for that node. If it only changes ranking or penalty, close the expansion with `no_new_work_reason`.

Use `exhaustion_reason` only when marking a node or family `exhausted: true`.