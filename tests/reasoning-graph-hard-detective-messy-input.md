# Messy Detective Test Packet — “Northgate Attic Case”

Use `reasoning-graph` strict mode if you want process audit. Treat this as a messy case packet, not a clean puzzle. Extract facts/constraints yourself. Some notes are rumors, hostile police theory, or witness panic. Do not assume every statement is reliable.

## Task

Build a reasoning graph and answer:

1. What is the most likely cause/mechanism of death?
2. How did the intruder(s) enter and leave if the room was locked from inside?
3. How many active offenders are most likely involved?
4. Who is the weakest/strongest suspect from the packet, and why?
5. What is the best next verification step?

Return compact answer + top competing hypotheses. If graph/HTML mode is used, include fact/constraint ledger and candidate table.

---

## Packet fragments, not in guaranteed chronological order

### Newspaper clipping, next morning, badly summarized

NORTHGATE HOUSE INCIDENT. Mr. B. Harrow, collector and amateur chemist, found dead near midnight in his upper laboratory. Local police report no ordinary signs of violence. A locked door, missing jewels, and family quarrel point to probable domestic theft. Police have taken statements from the brother, the old housekeeper, and gate porter. One source says the windows were fastened. Another says there were footprints near a window but “irrelevant because fastened.”

Handwritten margin note by unknown reader: “The reporter missed the ceiling.”

---

### Gate porter statement, terse

- Walls high. Broken glass on top. One narrow gate.
- I opened gate only for Mr. T. Harrow and his party near 11 p.m.
- I had strict orders not to admit strangers.
- Did not see anyone leave by gate after sunset except kitchen boy earlier.
- Grounds full of mounds/holes from years of digging. Bad footing. Easy to hide? maybe. Hard to cross silently? also maybe.
- I heard no ladder against wall. Wind was moving branches.

---

### Brother T. Harrow, first statement; nervous, self-protective

I told B. yesterday evening I would bring two advisers and Miss L. about the treasure claim. He was not pleased but knew we were coming. He had just found the chest in the sealed attic space above his laboratory. He said the value was absurdly high, more money than any of us should touch.

I left him around 10 p.m. in the lab. He locked the door after me. I heard the bolt. I did not return until we came with the visitors. If I meant theft, would I bring witnesses? The chest is gone. I am ruined because everyone will blame me.

More from same statement, later crossed out: “Father once feared a rough bearded man from the colonies. He saw a face at the window years ago. After father died, a paper with four marks was found on his chest. I always thought it was nonsense.”

---

### Housekeeper statement, interrupted by crying

Master often shut himself in all day. I brought breakfast; no answer. I assumed experiments. At tea time still no answer. I knocked again. Nothing. About an hour before Mr. T. arrived, I peeped at the keyhole.

The key was in the lock but not blocking all the hole. I saw his face in moonlight. I thought he was smiling at me but not humanly. I did not open the room. I could not. Door bolted.

No, I did not touch the papers. No, I do not know where the chest was hidden. Everyone knew the family dug for something, but not where.

---

### Rough sketch described by constable

Third floor corridor. Three doors left side. Lab is third door. Door: locked and bolted from inside. Key turned. Bolt visible after lamp held to gap. Door later forced.

Inside lab:

- chemical bottles along wall
- acid carboy cracked/leaking; heavy tar-like smell in room
- steps/ladder under rough hole in ceiling
- plaster and lath debris around steps
- rope coil near steps, plus wall hook above window side
- chair near table under/near ceiling opening line
- no obvious hiding place large enough for adult
- small card/paper on table with four scratched signs, maybe a number, maybe initial marks
- missing chest that was reportedly lowered from sealed attic earlier

Unsettled note: one officer says the rope was old house rope; another says end fibers looked fresh/blood-smeared.

---

### Medical note, unofficial; doctor annoyed

Body cold and stiff. Facial muscles fixed into extreme grin. Limbs contracted more than ordinary rigor. No stab wound, no blunt trauma, no strangulation mark. One tiny puncture above/behind ear with minute blood dot.

Object removed: long black thorn/splinter, sharpened, not local hedge wood, gummy residue near point. I said poison possible. Inspector said “romantic nonsense.”

If poison, likely fast-acting convulsive agent. Delivery force seems light: puncture shallow. Could be hand-placed? could be projected? Need laboratory test.

---

### Observer note from first private examiner

Do not step everywhere; floor contaminated by police boots already.

Window: fastened from inside when first examined. Yet sill has one heavy boot mark and several round muddy disc marks. Similar round marks continue from sill toward table. Heavy boot has broad heel edge. Round disc mark not a shoe.

Window is high above ground. No drainpipe. Wall face mostly sheer. No ordinary climber can reach window from outside unaided. From inside, rope on hook would make it possible for a strong adult to climb up/down even with awkward gait.

Ceiling hole: large enough for adult to pass if agile. Above: tiny sealed attic/roof void. Trapdoor to roof found openable from inside the void. Dust thick except numerous very small bare footprints, about half adult size, clear toes. Not childlike in stride? unsure. More like a small, agile adult? Do not overstate.

One tiny footprint partly in the leaking tar-smelling chemical near carboy.

---

### Inspector’s working theory, loud and maybe premature

Brother came at 10 p.m., quarreled over jewels, killed him somehow or victim died of fit, took chest, locked room deception. Housekeeper hysterical, porter negligent. We arrest the obvious people before they flee. “Window fastened, therefore marks by window are old or staged.”

Private examiner objection in margin:

- Dead man cannot bolt himself after theft if murdered before theft.
- If fit killed him, who removed chest and left four-mark paper?
- Why foreign thorn near ear?
- Why tiny roof prints?
- Why round stump-like marks from window to table?

---

### Old family rumor file, from six years earlier

Father Harrow returned from overseas with a locked jewel casket or knew where one was hidden. A military man died in the house after a dispute; official story vague. Father feared “the fourth sign” or “the four men” near death.

Night before father’s death: a hairy/bearded face reportedly appeared at his window. Ground below had one unusual footprint, not like household staff. After father died, papers were ransacked but nothing valuable taken. A note/sign with four marks was left.

Reliability warning: family myth, repeated by brother; may be superstition or guilt.

---

### Neighbor boy gossip, low reliability

Saw something on roof after dark, “like a monkey or a little man,” but boys say things. Also says he saw a sailor with a wooden leg near the lane last week. Mother says he reads penny dreadfuls.

---

### Chemical room inventory after police mess

Missing: jewel chest, contents unknown.
Present: broken acid/carboy, tar-smelling fluid, experimental glassware, rope, odd stone-headed club/stick by victim hand, thorn/splinter removed by doctor, paper with four signs.

Not found: pistol shot, normal knife, blood pool, obvious adult hiding place, exterior ladder.

---

## Solver instructions

Do not quote from any known story. Work only from this packet.

Expected output style:

- extracted fact/constraint ledger
- candidate hypotheses with priors/path costs
- UCS-style compact events if strict mode
- final answer must separate “strongly supported” from “speculative”
- do not call relative weights calibrated probabilities
