---
status: accepted
amends:
  - 0010-computed-belief-is-for-the-reader.md
---

# Exclusive sets flag rivals without normalising them

## Context

Every hypothesis starts at the 0.5 default and is updated on its own. In a wallet-drain case, five rival explanations of one leak summed to 250% before any evidence and 190% after the fix; before it, the page showed two incompatible hypotheses at 81% and 80%. The cost model said "mutually exclusive sibling hypotheses do not have to sum to anything", and nothing on the page compared hypotheses: Rivals lists only the candidates of a goal. `goal_groups[].exclusive` existed for goals, but no code read it beyond printing.

## Decision

- A state may list `exclusive_sets`: `{"id", "members", "note"}`, at least two hypothesis or candidate ids, of which at most one can be true. The list need not be complete. A patch adds or replaces sets by id and removes them with `remove_exclusive_sets`.
- A set changes no belief. The page lists each set's members side by side, and adds a note under the answer when two or more members are each above 50%.
- `audit` checks only that a set is well-formed, never its beliefs (ADR 0010).

## Consequences

- The wallet-drain state before its fix gets the note (H1 81%, H2 80%); after the fix it does not (only H2, at 80%).
- A set whose members all sit at the 0.5 default stays quiet, so declaring a set early costs nothing.
- An incoherent pair outside every set goes unflagged. The pre-claim reviewer (`docs/review.md`) checks for those.

## Considered

- Normalising members' beliefs at render time: rival lists are rarely complete, so the survivor of two rivals with one refuted at ÷5 would show 83% with nothing supporting it; downstream claims would still use raw beliefs, so the page would carry two sets of numbers; and the over-100% sum that exposes bad edges would vanish.
- A default prior of 1/n inside a set: it assumes the list is complete, and with one shared default the order inside the set barely depends on it.
- Flagging a sum over 100%: fires on every new set, since the defaults alone sum past it.
