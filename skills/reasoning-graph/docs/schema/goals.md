# Goals and Candidates

Use this page as the shape and example reference for goal/candidate schema. Usage policy lives in `../../SKILL.md`.

## Node shapes

### Goal

```json
{"id": "G1", "type": "goal", "text": "Recover the exact plaintext"}
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
- `optional_goals` — goal ids that may remain unanswered at a `solved`/candidate-count/threshold stop; also exempt as required sub-goals.
- `goal_groups[].exclusive` — marks mutually incompatible outcomes in that group.

## Sub-goals

Chained or nested goals are plain `goal` nodes; there is no sub-goal node type. Link them with `parent goal --requires--> child goal`:

```json
{
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Find the URL path into the manor"},
    {"id": "G2", "type": "goal", "text": "Find the next URL path under /TwoSigns/"}
  ],
  "edges": [
    {"id": "G1-G2", "from": "G1", "to": "G2", "type": "requires", "reasoning": "The trail continues into room 2."}
  ]
}
```

A goal is **answered** when it has an `answers` edge from a `candidate_solution` and every goal it `requires` is answered (optional goals excepted). The open leaf goal is therefore structural, not inferred from insertion order. A candidate-bearing stop (`solved`, `candidate_threshold_met`, `candidate_count_met`) is rejected by `stop`, `audit`, and `stop-review` while any accepted, non-optional goal is unanswered.

## Proof-shaped tasks

| task vocabulary | graph shape |
| --- | --- |
| theorem | `goal` |
| axiom, given | `observation` with `prior: 1.0`, or `constraint` |
| lemma, proposition, corollary, conjecture | `hypothesis` |
| proof | `candidate_solution` with `answer_kind: "exact_method"` |
| remark | report text |

### Lemma-shaped steps

A lemma is one `hypothesis` node for its whole life. Once evidence-grounded it can `supports`/`contradicts` other claims, weighted by its belief (`docs/cost-model.md`); while it rests on its prior alone, its support has no effect. While open it carries a `prior`:

```json
{
  "reason": "Suspect a divisibility lemma",
  "nodes": [
    {"id": "H3", "type": "hypothesis", "text": "Every row sum is divisible by 3", "prior": 0.5}
  ]
}
```

Once proved, a later `record` adds its `leads_to` premises to the same node and sets the local `prior` to the certainty of the inference step (`1.0` for an exact derivation, so belief comes from the premises alone):

```json
{
  "nodes": [
    {"id": "O4", "type": "observation", "text": "Row generator appends only multiples of 3 (src/rows.py:12-30)", "source": "src/rows.py", "prior": 0.95}
  ],
  "edges": [
    {"id": "O4-H3", "from": "O4", "to": "H3", "type": "leads_to", "reasoning": "If every appended term is a multiple of 3, each row sum is too."}
  ],
  "update_nodes": [
    {"id": "H3", "set": {"prior": 1.0}}
  ],
  "no_new_work_reason": "H3 is now premise-backed; the route continues from the candidate that uses it."
}
```

## Examples

### Single exact-answer goal

```json
{
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Find the exact passcode"},
    {"id": "CS1", "type": "candidate_solution", "text": "Passcode is 314159", "answer_kind": "exact_answer", "prior": 0.5}
  ],
  "edges": [
    {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "This candidate supplies the answer requested by the goal."}
  ]
}
```

### Solve-or-identify-blocker goals

```json
{
  "goal_policy": {"accepted_goals": ["G1", "G2"], "preferred_goals": ["G1"]},
  "goal_groups": [{"id": "GG1", "goals": ["G1", "G2"], "exclusive": true}],
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Find a valid solution"},
    {"id": "G2", "type": "goal", "text": "Identify blocker proving no valid solution exists"},
    {"id": "CS2", "type": "candidate_solution", "text": "No solution exists under the constraints", "answer_kind": "blocker", "prior": 0.5}
  ],
  "edges": [
    {"id": "CS2-G2", "from": "CS2", "to": "G2", "type": "answers", "reasoning": "This candidate supplies the answer requested by the goal."}
  ]
}
```

### Method hypothesis that is not final answer

```json
{
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Recover the exact plaintext"},
    {"id": "H1", "type": "hypothesis", "text": "The cipher likely uses columnar transposition", "prior": 0.5},
    {"id": "T1", "type": "test", "text": "Try columnar transposition keys"}
  ],
  "edges": [
    {"id": "H1-T1", "from": "H1", "to": "T1", "type": "prompts", "reasoning": "This claim motivates the follow-up check."}
  ]
}
```

## Validation checklist

- `candidate_solution -> goal` edges use `type: "answers"`.
- `answers` edges connect only `candidate_solution -> goal`.
- Each candidate connects to at least one goal with an `answers` edge.
- Each candidate connects to an accepted goal when `goal_policy.accepted_goals` is present.
- Candidate `answer_kind` is one of the listed values.
- Concrete exact-answer goals accept only `exact_answer` or `exact_method` candidates.
- `method_hypothesis`, `clue_path`, and `blocker` candidates target matching method, clue, or epistemic goals.
- `hypothesis -> goal` edges are invalid; claims reach goals only through `candidate_solution --answers--> goal`.
- `goal -> goal` edges use `requires`; goal requirement cycles are invalid.
- `goal_policy.optional_goals` reference existing goals.
- `constraint -> goal` with `requires` is invalid; use `goal -> constraint` or `candidate_solution -> constraint`.
