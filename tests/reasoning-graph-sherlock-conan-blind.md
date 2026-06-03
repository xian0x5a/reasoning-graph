# Reasoning Graph Test: The Locked Observatory

Use the `reasoning-graph` skill in **graph mode**.

## Task

Solve the mystery using a reasoning graph.

Return:

1. compact answer summary
2. facts / constraints separation
3. assumptions with numeric priors
4. UCS-style candidate ordering with path costs
5. winning proof path
6. competing candidate paths and contradicted/weakened branches
7. next verification action
8. path to generated HTML graph artifact

## Scenario

At 9:00 PM, Professor Liang is found dead inside the university observatory dome. The door is locked from the inside. Only one key exists, found in Liang’s coat pocket. The window is sealed. The dome hatch is too high to reach without a ladder.

## Goal

Identify the most likely killer, method, and next verification action.

## Facts

- F1: Victim died between 8:20–8:40 PM.
- F2: Cause of death is cyanide poisoning.
- F3: Half-finished tea cup on desk contains cyanide.
- F4: Door was locked from inside when body was found.
- F5: Only key was in victim’s coat pocket.
- F6: Window is sealed.
- F7: Dome hatch is too high to reach without a ladder.
- F8: Security camera shows nobody entering after 8:05 PM.
- F9: Three people visited before 8:05 PM:
  - Dr. Rao, rival professor, brought tea leaves at 7:50 PM.
  - Mei, graduate student, delivered telescope logs at 7:58 PM.
  - Chen, lab technician, repaired dome motor at 8:03 PM.
- F10: At 8:15 PM, victim called campus security saying: “The stars are moving wrong.”
- F11: At 8:30 PM, a loud mechanical noise came from the observatory dome.
- F12: At 8:45 PM, Mei found the door locked and called security.
- F13: Dome motor timer was set to rotate at 8:30 PM.
- F14: Tea kettle water was still hot at 8:45 PM.
- F15: Cyanide traces were found on the inside rim of the tea cup, not in the tea leaves or kettle.
- F16: A small cracked capsule shell was found under the telescope control panel.
- F17: Chen’s repair kit contains empty gelatin capsules for storing tiny screws.
- F18: Dr. Rao has motive: grant dispute.
- F19: Mei has motive: victim planned to reject her thesis.
- F20: Chen has motive: victim discovered stolen equipment.
- F21: Rao left campus at 8:00 PM on camera.
- F22: Mei was seen in the library from 8:10–8:40 PM.
- F23: Chen was in the basement workshop from 8:10–8:35 PM, but there is no camera inside.

## Constraints

- C1: Do not assume supernatural or impossible movement.
- C2: Use numeric priors and UCS-style path costs.
- C3: Produce up to 3 candidate solution paths.
- C4: Generate an HTML graph artifact.

