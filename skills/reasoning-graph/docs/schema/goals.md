# Goals, Candidates, and Hypothetical Branches

Use goals to define accepted destinations. Use candidates only for answers that satisfy an accepted goal.

## Hypothetical branches

A hypothetical branch is an established reasoning chain under one or more assumptions. It represents one possible route to truth if those assumptions hold.

Rules:

- Treat derived nodes inside a hypothetical branch as conditional truth, not global truth.
- Every derived node under an assumption inherits dependency on that assumption until verified or proven independent.
- Do not create separate `solution` nodes. The final answer is the currently best-supported `candidate_solution`.
- Use `candidate_solution -> goal` with `answers` when the candidate satisfies the goal.
- A method/source branch is not a `candidate_solution` unless it itself answers the goal; keep it as `assumption` or `derived`.
- Do not point an `assumption` directly at a `goal`. Route it through tests, derived conclusions, or candidate answers. Direct `assumption -> goal` smuggles “this branch solves the task” without evidence.

## Candidate answer kinds

```txt
exact_answer       exact answer to the accepted goal, e.g. plaintext/value/name
exact_method       exact reproducible method that entails the accepted goal
method_hypothesis  plausible method branch, not enough to answer a concrete solve goal
clue_path          clue-family/path candidate for an explicit clue-finding goal
blocker            insufficiency/blocker candidate for an explicit epistemic goal
```

Rules:

- Every `candidate_solution` needs `answer_kind` in strict states.
- For concrete solve/exact-answer goals, only `exact_answer` and `exact_method` may connect to the accepted goal.
- `method_hypothesis`, `clue_path`, and `blocker` must target explicit method/clue/epistemic goals or remain assumptions/derived nodes.
- Do not make “not solved”, “cannot establish”, or “missing dependency” a `candidate_solution` for a normal solve goal. That is a stop outcome or derived blocker.
- A true “no valid solution exists” candidate is allowed only when it answers an accepted epistemic/negative goal and is supported by positive impossibility evidence.

## Multiple goals

Use multiple `goal` nodes only when the user explicitly accepts more than one outcome, such as solving a puzzle, proving no valid solution exists, or deciding evidence is insufficient under constraints.

Optional top-level policy:

```json
{
  "goal_policy": {
    "accepted_goals": ["G1", "G2"],
    "preferred_goals": ["G1"]
  },
  "goal_groups": [
    {"id": "GG1", "goals": ["G1", "G2", "G3"], "exclusive": true}
  ]
}
```

Rules:

- If `accepted_goals` is absent, all goal nodes are acceptable destinations.
- `preferred_goals` affects presentation/priority discussion, not validity.
- `exclusive: true` means goals in that group are mutually incompatible outcomes; do not add noisy candidate-to-other-goal `contradicts` edges.
- Candidate viability is per accepted goal: `candidate_solution -> accepted goal` with `answers`.
- Goal-group exclusivity is logical incompatibility between outcomes; contradictions apply through normal truth-cost penalties.

For a normal solve request, use one goal. For “solve it or prove impossible”, use two accepted goals. For “solve it or say evidence is insufficient”, add an explicit epistemic goal; then “insufficient evidence” may be a candidate only for that goal.