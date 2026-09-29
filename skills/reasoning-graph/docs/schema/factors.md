# Correlation groups

`factors` holds correlation groups: edges into one target that share a source, an observation, a latent cause, or a logical overlap. A group counts its edges once, at one combined score, instead of multiplying them as independent evidence.

## Shape

```json
{"id": "F1", "edges": ["O1-H1", "O2-H1"], "score": 4, "note": "Two log lines of the same failed request."}
```

- `id` — unique group id.
- `edges` — two or more edges, each named by its ends as `from-to`. All share one type (`leads_to`, `supports`, or `contradicts`) and one target.
- `score` — required, 1 to 5: the combined weight of the grouped edges, read from the same tables as an ungrouped score (`../cost-model.md`).
  - `supports` / `contradicts`: the evidence ratio of the whole group.
  - `leads_to`: the joint probability that all grouped premises hold.
- `note` — optional: why the edges depend on each other.

The edges carry the relation, the target, and the sources, so a group names none of them. A grouped edge carries no `score` of its own; the group's score is the one number.

## Example

Two log lines of one failed request support `H1`. Ungrouped, two default edges would double the odds twice. Grouped at score 4, they triple them once.

```json
{
  "edges": [
    {"from": "O1", "to": "H1", "type": "supports", "note": "A timeout at the gateway is more likely if the pool is exhausted."},
    {"from": "O2", "to": "H1", "type": "supports", "note": "The retry of that request timing out is the same signal again."}
  ],
  "factors": [
    {"id": "F1", "edges": ["O1-H1", "O2-H1"], "score": 4, "note": "One request, logged twice."}
  ]
}
```

## Changing a group

A patch adds or replaces a group by `id`: to add an edge, send the whole group again with the longer `edges` list and the score you now hold. `remove_factors` removes groups by id.

A group is never removed implicitly. Removing an edge or a node that a group still names fails validation, so remove or replace the group in the same patch.

## Validation

- `edges` lists at least two different ids, each of an existing edge.
- The edges share one type, which is `leads_to`, `supports`, or `contradicts`, and one target.
- An edge belongs to at most one group.
- A grouped edge has no `score`.
- `score` is an integer from 1 to 5.
- The removed fields `relation`, `target`, `inputs`, `aggregation`, and `reason` are rejected.
