# Goals and Candidates

Use this page as the shape and example reference for goal/candidate schema. Usage policy lives in `../../SKILL.md`.

## Node shapes

### Goal

```json
{"id": "G1", "type": "goal", "text": "Recover the exact plaintext"}
```

### Candidate answer

A candidate is a hypothesis whose text states the whole claim:

```json
{"id": "H2", "type": "hypothesis", "text": "The plaintext is HELLO WORLD"}
```

An `answers` edge to the goal it would settle makes it a candidate, and carries the `answer_kind`:

```json
{"from": "H2", "to": "G1", "type": "answers", "answer_kind": "exact_answer"}
```

A hypothesis that settles two goals has an `answers` edge to each, each with its own kind.

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

A goal is **answered** when a hypothesis has an `answers` edge to it and every goal it `requires` is answered (optional goals excepted). The open leaf goal is therefore structural, not inferred from insertion order. `audit` fails a claimed answer while any accepted, non-optional goal is unanswered.

## Proof-shaped tasks

| task vocabulary | graph shape |
| --- | --- |
| theorem | `goal` |
| axiom, given | `observation`, or `constraint` |
| lemma, proposition, corollary, conjecture | `hypothesis` |
| proof | `hypothesis` answering the theorem with `answer_kind: "exact_method"` |
| remark | a `note` on the node it concerns, or the final response |

### Lemma-shaped steps

A lemma is one `hypothesis` node for its whole life. Once evidence-grounded it can `supports`/`contradicts` other claims, weighted by its belief (`docs/cost-model.md`); while it rests on its score alone, its support has no effect. While open it takes the default score 3, or one you set:

```json
{
  "nodes": [
    {"id": "H3", "type": "hypothesis", "text": "Every row sum is divisible by 3", "score": 2}
  ]
}
```

Once proved, a later `record` adds its premises to the same node and unsets any score you wrote while it was open; belief then comes from the premises alone (choosing the edge, `../../SKILL.md`):

```json
{
  "nodes": [
    {"id": "O4", "type": "observation", "text": "Row generator appends only multiples of 3 (src/rows.py:12-30)", "source": "src/rows.py"}
  ],
  "edges": [
    {"from": "O4", "to": "H3", "type": "premise_of", "note": "If every appended term is a multiple of 3, each row sum is too."}
  ],
  "update_nodes": [{"id": "H3", "unset": ["score"]}]
}
```

A lemma that turns out to settle a goal, such as a sub-goal, becomes a candidate the same way: a later patch adds its `answers` edge, and it stays one node.

## Examples

### Single exact-answer goal

```json
{
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Find the exact passcode"},
    {"id": "H1", "type": "hypothesis", "text": "The passcode is 314159"}
  ],
  "edges": [
    {"from": "H1", "to": "G1", "type": "answers", "answer_kind": "exact_answer"}
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
    {"id": "H2", "type": "hypothesis", "text": "No solution exists under the constraints"}
  ],
  "edges": [
    {"from": "H2", "to": "G2", "type": "answers", "answer_kind": "blocker"}
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

- `answers` edges connect only `hypothesis -> goal`, and are the only edges from a hypothesis to a goal.
- Each `answers` edge carries an `answer_kind` from the listed values; no other edge, and no node, carries one.
- Each candidate answers an accepted goal when `goal_policy.accepted_goals` is present.
- Concrete exact-answer goals accept only `exact_answer` or `exact_method` edges.
- `method_hypothesis`, `clue_path`, and `blocker` edges target matching method, clue, or epistemic goals.
- `goal -> goal` edges use `requires`; goal requirement cycles are invalid.
- `goal_policy.optional_goals` reference existing goals.
- `constraint -> goal` with `requires` is invalid; use `goal -> constraint` or `hypothesis -> constraint`.
