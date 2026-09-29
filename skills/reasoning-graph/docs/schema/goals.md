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
  "answer_kind": "exact_answer"
}
```

A candidate answers a goal through an `answers` edge:

```json
{"from": "CS1", "to": "G1", "type": "answers"}
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
- `optional_goals` — goal ids a claimed answer may leave unanswered; also exempt as required sub-goals, and the answer need not name a candidate for them.
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
    {"from": "G1", "to": "G2", "type": "requires"}
  ]
}
```

A goal is **answered** when it has an `answers` edge from a `candidate_solution` and every goal it `requires` is answered (optional goals excepted). The open leaf goal is therefore structural, not inferred from insertion order. `audit` fails a claimed answer while any accepted, non-optional goal is unanswered.

## Proof-shaped tasks

| task vocabulary | graph shape |
| --- | --- |
| theorem | `goal` |
| axiom, given | `observation`, or `constraint` |
| lemma, proposition, corollary, conjecture | `hypothesis` |
| proof | `candidate_solution` with `answer_kind: "exact_method"` |
| remark | report text |

### Lemma-shaped steps

A lemma is one `hypothesis` node for its whole life. Once evidence-grounded it can `supports`/`contradicts` other claims, weighted by its belief (`docs/cost-model.md`); while it rests on its score alone, its support has no effect. While open it takes the default score 3, or one you set:

```json
{
  "nodes": [
    {"id": "H3", "type": "hypothesis", "text": "Every row sum is divisible by 3"}
  ]
}
```

Once proved, a later `record` adds its `leads_to` premises to the same node. Belief then comes from the premises alone; unset a score you wrote while it was open, unless the inference step itself is doubtful:

```json
{
  "nodes": [
    {"id": "O4", "type": "observation", "text": "Row generator appends only multiples of 3 (src/rows.py:12-30)", "source": "src/rows.py"}
  ],
  "edges": [
    {"from": "O4", "to": "H3", "type": "leads_to", "note": "If every appended term is a multiple of 3, each row sum is too."}
  ]
}
```

## Examples

### Single exact-answer goal

```json
{
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Find the exact passcode"},
    {"id": "CS1", "type": "candidate_solution", "text": "Passcode is 314159", "answer_kind": "exact_answer"}
  ],
  "edges": [
    {"from": "CS1", "to": "G1", "type": "answers"}
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
    {"id": "CS2", "type": "candidate_solution", "text": "No solution exists under the constraints", "answer_kind": "blocker"}
  ],
  "edges": [
    {"from": "CS2", "to": "G2", "type": "answers"}
  ]
}
```

### Method hypothesis that is not final answer

```json
{
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Recover the exact plaintext"},
    {"id": "H1", "type": "hypothesis", "text": "The cipher likely uses columnar transposition"},
    {"id": "T1", "type": "test", "text": "Try columnar transposition keys"}
  ],
  "edges": [
    {"from": "H1", "to": "T1", "type": "prompts"}
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
