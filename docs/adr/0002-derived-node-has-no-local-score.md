---
status: accepted
---

# A derived node carries no local score

A conclusion's belief is revisable, so it does not belong in the fixed-reliability slot (ADR 0001). A `derived` node takes its belief from its `leads_to` premises, and validation rejects a derived node without at least one premise. `posterior` is allowed alongside them and overrides premise propagation once the overall belief is calibrated, but it does not replace the derivation: a calibrated conclusion still shows what it was derived from, and a belief with no derivation belongs on an `assumption`, `evidence`, or `candidate_solution` node instead. Doubt about the inference itself -- clock skew, a rule that may not apply here -- is an unstated premise: it is modelled as an `assumption` with a `prior` linked by `leads_to`, which keeps the doubt visible and lets it update with everything downstream.

## Considered Options

Weighted decision matrix, 1-5, weighted total out of 5.

| option | correct math under misuse | writer clarity | failure containment | soft-inference expressiveness | auditability | lean surface | total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **no local score, premises required (chosen)** | 5 | 4 | 5 | 3 | 5 | 3 | **4.20** |
| `posterior` always required | 5 | 3 | 4 | 2 | 5 | 4 | 3.85 |
| `confidence` or `posterior` | 3 | 3 | 3 | 5 | 3 | 5 | 3.60 |
| dedicated `step_confidence` name | 3 | 4 | 2 | 5 | 3 | 3 | 3.35 |
| `confidence` as step reliability | 2 | 3 | 2 | 5 | 2 | 5 | 3.10 |
| `prior` or `posterior` | 2 | 2 | 2 | 5 | 3 | 5 | 3.05 |

Weights: correct math under misuse 0.20, writer clarity 0.20, failure containment 0.15, expressiveness 0.15, auditability 0.15, lean surface 0.15.

- **`confidence` as step reliability (the original proposal).** Dominated on every criterion except expressiveness: a writer holding an overall belief of `0.72` for the conclusion writes it into the local factor, and the premises multiply it again with no error raised.
- **`prior` or `posterior`.** Rejected for the same double-count reason, with worse naming: the field reads like the assumption rule while the value is multiplied.
- **`confidence` or `posterior`.** The runner-up and the design to beat: it keeps single-node soft inferences, but leaves the double-count trap open behind a documentation warning.
- **`posterior` always required.** Safer than the chosen option on misinterpretation, but forces premature calibration on intermediate conclusions.

Sensitivity: convenience-weighted criteria were the closest call. With expressiveness 0.25 and lean surface 0.20 (and auditability 0.10), the chosen option scores 3.95 against 3.90 for `confidence` or `posterior` -- requiring a premise is what closes the `posterior`-only shortcut that made the runner-up competitive.

## Consequences

- A genuinely probabilistic inference costs one extra `assumption` node; the judgment becomes testable and updatable instead of hidden in a factor.
- A belief with no derivation cannot be typed as `derived`; it becomes an `assumption` with a `prior`, `evidence` with `confidence`, or `candidate_solution` with `posterior`, which states where the number came from.
