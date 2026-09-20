# SPOILER Validator — The Locked Observatory

Do not include this validator file in blind solver prompts.

## Hidden Clue Coverage Targets

A strong answer should explain:

- T1: locked door / key in victim’s pocket
- T2: delayed poisoning after all visitors left
- T3: “The stars are moving wrong”
- T4: 8:30 PM dome motor noise
- T5: cyanide on cup rim, not tea leaves or kettle
- T6: cracked capsule shell under telescope control panel

## Expected Strong Solution Shape

Most likely culprit: Chen.

Likely method:

- Chen used access during dome motor repair to set up a delayed poison mechanism.
- A cyanide capsule was hidden near the telescope/control-panel/dome mechanism.
- The 8:30 PM timed dome movement cracked/released the capsule or otherwise transferred poison to the cup rim area.
- Victim noticed the telescope/dome misalignment before death and called security: “The stars are moving wrong.”
- Locked-room illusion works because poison was delivered after visitors left and no one needed to enter after 8:05 PM.

Expected competing candidates:

1. Chen mechanical delayed poisoning — strongest.
2. Rao poisoned tea leaves — weakened/contradicted by no cyanide in tea leaves or kettle, plus timing.
3. Mei directly poisoned cup/logs — weakened by library alibi and inability to explain delayed mechanism/capsule/motor clues.

## Pass Criteria

- Separates facts and constraints.
- Uses multiple assumptions with priors.
- Orders candidates by belief and search cost (best-first), not by accumulated path cost.
- Does not jump to first suspect solely based on motive.
- Identifies Chen branch as best, or gives a very strong alternative with explicit uncertainty.
- Explains locked-room condition and delayed poisoning.
- Explains “stars are moving wrong,” 8:30 motor noise, cup-rim poison, and cracked capsule.
- Produces HTML graph artifact with winning path highlighted and weaker/dead branches dimmed or marked.

## Fail Criteria

- Treats motive as enough.
- Ignores physical clues.
- Claims Rao poisoned tea leaves despite F15.
- Claims Mei entered after 8:05 despite F8 unless explaining camera bypass with evidence.
- Gives final certainty without verification action.
- Does not produce graph artifact in graph mode.

## Suggested Next Verification Action

A strong answer should propose one or more of:

- Forensically inspect dome motor/control panel/cup position for cyanide transfer path and gelatin residue.
- Compare capsule shell material to Chen’s repair-kit capsules.
- Audit dome timer and repair logs for Chen’s access/manipulation.
