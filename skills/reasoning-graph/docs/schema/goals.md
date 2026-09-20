# Goals and Candidates

Use this page as the shape and example reference for goal/candidate schema. Usage policy lives in `../../SKILL.md`.

## Node shapes

### Goal

```json
{"id": "G1", "type": "goal", "text": "Recover the exact plaintext", "probability": 1.0}
```

### Candidate solution

```json
{
  "id": "CS1",
  "type": "candidate_solution",
  "text": "Plaintext is ...",
  "answer_kind": "exact_answer",
  "posterior": 0.8
}
```

A candidate answers a goal through an `answers` edge:

```json
{"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "This candidate supplies the answer requested by the goal."}
```

## `answer_kind` values

```txt
exact_answer       exact answer to the accepted goal, e.g. plaintext/value/name
exact_method       exact reproducible method that entails the accepted goal
method_hypothesis  plausible method branch, not enough to answer a concrete solve goal
clue_path          clue-family/path candidate for an explicit clue-finding goal
blocker            insufficiency/blocker candidate for an explicit epistemic goal
```

## Multiple-goal policy shape

```json
{
  "goal_policy": {
    "accepted_goals": ["G1", "G2"],
    "preferred_goals": ["G1"]
  },
  "goal_groups": [
    {"id": "GG1", "goals": ["G1", "G2"], "exclusive": true}
  ]
}
```

Fields:

- `accepted_goals` — goal ids that candidates may validly answer. If absent, all goal nodes are accepted.
- `preferred_goals` — goal ids preferred in presentation or priority discussion; does not change validity.
- `goal_groups[].exclusive` — marks mutually incompatible outcomes in that group.

## Examples

### Solve-or-identify-blocker goals

```json
{
  "goal_policy": {"accepted_goals": ["G1", "G2"], "preferred_goals": ["G1"]},
  "goal_groups": [{"id": "GG1", "goals": ["G1", "G2"], "exclusive": true}],
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Find a valid solution", "probability": 1.0},
    {"id": "G2", "type": "goal", "text": "Identify blocker proving no valid solution exists", "probability": 1.0},
    {"id": "CS2", "type": "candidate_solution", "text": "No solution exists under the constraints", "answer_kind": "blocker", "confidence": 0.9}
  ],
  "edges": [
    {"id": "CS2-G2", "from": "CS2", "to": "G2", "type": "answers", "reasoning": "This candidate supplies the answer requested by the goal."}
  ]
}
```

A method hypothesis remains an `assumption` (for example, `prior: 0.5`) with a
`prompts` edge to a test. It cannot answer an exact-answer goal until verified.

## Validation checklist

- `candidate_solution -> goal` edges use `type: "answers"`.
- `answers` edges connect only `candidate_solution -> goal`.
- Each candidate connects to at least one goal with an `answers` edge.
- Each candidate connects to an accepted goal when `goal_policy.accepted_goals` is present.
- Candidate `answer_kind` is one of the listed values.
- Concrete exact-answer goals accept only `exact_answer` or `exact_method` candidates.
- `method_hypothesis`, `clue_path`, and `blocker` candidates target matching method, clue, or epistemic goals.
- `assumption -> goal` direct edges are invalid; route through tests, derived conclusions, or candidates.
- `constraint -> goal` with `requires` is invalid; use `goal -> constraint` or `candidate_solution -> constraint`.
