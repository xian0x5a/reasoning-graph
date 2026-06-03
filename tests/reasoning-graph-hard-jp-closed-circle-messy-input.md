# Hard Messy Detective Test Packet — “The Nocturne at Tideglass Hall”

Inspired by the *kind* of problem structure common in Japanese detective fiction: island/closed-circle, music cue, theatrical legend, impossible room, old guilt, serial-staging pressure. This is an original test packet. Do not assume it matches any existing Conan/Kindaichi plot.

Use `reasoning-graph` if available. Strict mode recommended.

## Task

From this unstructured packet, build a reasoning graph and answer:

1. What most likely killed Director Saeki?
2. How was the music-room “locked from inside” illusion made?
3. Was the 21:12 piano/nocturne sound likely live performance, automatic playback, or irrelevant?
4. How many active offenders are needed by the best explanation?
5. Who is strongest suspect? Who is weakest obvious suspect?
6. What one next verification would most decisively confirm/refute the best theory?

Return:

- extracted fact + constraint ledger
- top candidate hypotheses with priors/path costs or other honest ranking
- compact UCS-style events if strict mode
- final answer with “strongly supported” vs “speculative” separated
- no calibrated posterior claims unless you explicitly model/test evidence

---

## Case packet — fragments copied from notes, messages, interviews, and a newspaper draft

### 0. Newspaper draft, written too fast

TIDEGLASS HALL TRAGEDY. A storm-marooned music retreat turned fatal last night when theatre director Minoru Saeki, 51, was discovered dead in the locked Blue Music Room. Witnesses report hearing a forbidden nocturne played shortly before the body was found. The case resembles an old island legend concerning the “White Pierrot,” a masked figure said to punish traitors to the arts.

Police sources say the door was locked from inside, the only window was latched, and all guests were together when the music began. A valuable packet of old composition rights may be missing. The obvious focus is Saeki’s long-running feud with actress Aoi Kirishima, who threatened him at dinner.

Editor margin note: “Too clean. Ask about transom, sound booth, doctor’s timing.”

---

### 1. Location notes, from constable with bad handwriting

Remote island hall. One ferry, stopped by storm after 18:10. Mobile reception unreliable except by east balcony. Tide high 20:40–23:00. No boat engine reported, but wind loud.

Blue Music Room:

- one heavy door from corridor
- old key lock, key found on inside after door forced
- sliding bolt on inside, about shoulder height
- narrow transom above door, hinged inward; gap maybe 18 cm high when open
- one sea-facing window, latched from inside; wet sill outside, no clear prints
- upright piano against inner wall
- old radiator, ticking loudly
- stage costumes stored in adjoining prop closet, but closet door opens only to corridor, not into music room
- ceiling beams low; dust visible on transom frame

Important? Door opens inward. Bolt has round brass knob. Transom frame had tiny crescent smear of dark wax or tape-glue? maybe old dirt.

---

### 2. Guest list, with gossip scribbles

**Minoru Saeki** — victim. Director. Controlled rights to late composer Rei Kisaragi’s last score. Many enemies. Diabetic? drank little. Hated cheap alcohol.

**Aoi Kirishima** — actress. Public quarrel with Saeki at dinner. Threatened: “I’ll expose what you did to Rei.” Strong motive. Seen crying at 20:50. Wears long red nails. Says she cannot play piano.

**Dr. Hanae Mori** — island clinic doctor. Calm. Pronounced death. Knows poisons? Treated Rei’s mother years ago. Left dining room 20:24–20:45 for “sedatives” after Aoi’s panic. Right hand bandaged from broken ampoule, maybe true.

**Kei Natsume** — sound technician. Ran mixer, generator, recordings for memorial rehearsal. Left dining room 20:27–20:48 to “check generator relay.” Carries black gaffer tape, monofilament for stage effects, portable speakers. Claims music sounded like “someone really playing, not playback.”

**Goro Ebina** — stage carpenter. Strong, knows locks/sets. Left 20:31–20:42 for candles. Has fishing line in tool roll. Says bolt trick impossible “unless door is already open.” Drinking heavily.

**Yuri Soma** — young pianist. Could play the forbidden nocturne from memory. Was in dining room from 20:55 onward, shaking. At 21:12 everyone looked at her first. She says piano in Blue Room was detuned, impossible to perform cleanly.

**Toma Riku** — critic. Profited from old scandal. In debt. Was on east balcony around 20:36 “trying to get signal.” Returned wet. Claims saw white mask near roofline.

**Mika Endo** — caretaker. Has all keys, knows house. Says transom sticks unless pushed hard. Found old reel tapes in storage last week. Lied first about entering sound booth, later said she only dusted it.

---

### 3. Dinner timeline assembled by inn server, not exact

19:40 dinner starts. Argument about Rei Kisaragi: Saeki says “dead people don’t collect royalties.” Aoi throws wine but misses.

20:05 Saeki receives small envelope. Turns pale. Says he needs air.

20:14 Saeki leaves dining room, direction unclear. Some say he went toward Blue Music Room; one says toward west stairs.

20:22 short blackout, two seconds. Generator cough. Kei says it will fail if relay not reset.

20:24 Dr. Mori leaves to fetch sedative for Aoi, who is hyperventilating.

20:27 Kei leaves with small shoulder bag. Says generator relay.

20:31 Goro leaves for candles; server sees him near prop closet, not generator.

20:36 Toma on east balcony trying phone. Rain begins harder.

20:42 Goro returns with candles and wax on sleeve. He says candle box spilled.

20:45 Dr. Mori returns with sedative. Aoi refuses injection.

20:48 Kei returns. His left cuff wet, says generator room roof leaks.

20:50 Aoi sobs in alcove. Yuri sits with her until about 21:00.

21:04 caretaker Mika says she heard radiator ticking in Blue Music Room while passing corridor. No music then. She did not try door.

21:12 nocturne heard. Not loud, but clear. Everyone in dining room freezes. Yuri says “that piano cannot sound like that.” Kei says “It is coming from Blue Room.”

21:15 group reaches Blue Music Room corridor. Door locked. Key visible inside but not fully blocking keyhole. Bolt seen engaged through crack? uncertain: server says yes, Goro says “looked shut.”

21:18 door forced. Victim seated near piano, head tilted, one hand near glass. Piano lid closed. No performer.

---

### 4. Death scene notes, mixed police/private examiner

Saeki seated in armchair angled toward piano. No major wound. Lips slightly blue. Bitter-almond-ish smell reported by one officer, denied by two others. Right hand clenched around torn sheet-music corner. Small glass on piano top with orange liqueur residue. Saeki supposedly disliked orange liqueur; but bottle came from his own locked cabinet? Cabinet key missing then later found under rug.

One tiny puncture inside left elbow, maybe old medical injection, maybe fresh. Dr. Mori says Saeki was diabetic and injection marks are normal. Server says he never saw Saeki inject at dinner.

Face calm, not grimacing. Rigor not advanced. Doctor’s first time-of-death guess: “probably 20:30 to 21:10, cannot be tighter in this damp cold.” Later she told police “after 21:00 is possible.”

A folded card under music stand: “Third movement begins when the traitor hears himself.” Ink wet? maybe from rain? maybe from spilled drink.

---

### 5. Music/piano notes, from Yuri the pianist, angry

The Blue Room piano was not tuned for concert. Two middle keys stick. Sustain pedal squeaks. The nocturne we heard at 21:12 had no pedal squeak, no stuck key, and tempo was too even. It sounded like an old master-take through a wooden box, not a human at a bad upright.

But I was far away in dining room; maybe hallway acoustics fooled me. Kei immediately said it was live, which annoyed me. A sound technician should hear compression better than me.

After door was forced, piano lid closed. Fallboard down. No sheet on stand except the torn corner in Saeki’s hand. If someone played, they cleaned too fast. If playback, where is the speaker?

Later note added: Constable found a small black rectangular mark inside piano case, as if tape had been peeled off. He did not photograph it before touching. Idiot.

---

### 6. Door/lock notes, from Goro, defensive

People think stage carpenters can do any locked-room trick. Door lock is simple. If key is inside, you can maybe turn it from outside with pliers if keyhole not blocked, but not if the bolt is also thrown. Bolt knob is round, smooth. You need a loop, line, or rod, and a way to pull from above or side. Transom above door could pass a line, not a person. If line used, line must be removed unless left hanging. No line found.

That said, old bolts slide if door is shaken. I’ve seen worse.

Also: candle wax on my sleeve is from candle box. Ask Mika; she stores candles above prop closet.

---

### 7. Sound booth / generator notes, written by junior officer

Sound booth locked? Not really. Latch broken. Mixer on standby. Laptop asleep. Recent file list included:

- `kisaragi_nocturne_archive_clean.wav`
- `rain_loop_test.wav`
- `cue_3_traitor_hears_self.wav`

No password after wake. Kei says he left laptop open for rehearsal, so anyone could use it.

Bluetooth devices list: `Hall-Main`, `K-N field monitor`, `OldPianoShell?`, `MikaPhone`, two unknown Japanese names. Kei says labels are from old equipment and meaningless.

Small spool of clear monofilament in booth drawer; nearly empty. Gaffer tape roll in Kei’s bag, edge recently cut. But stage people all use tape. One short black tape scrap found stuck under transom hinge; not bagged until morning.

Generator relay room: wet floor near west wall. Kei’s boot prints present. Also smaller prints maybe old. Reset switch dry. No one confirms relay actually needed resetting.

---

### 8. Caretaker Mika, second statement after contradiction

I first said I never entered sound booth because I feared blame. Truth: around 20:10 I went in to fetch old memorial recording list for Saeki. He wanted Rei’s original nocturne played later in ceremony, not at night. I saw Kei’s laptop there, open. I did not touch it.

I passed Blue Room around 21:04. I heard radiator ticks and maybe a chair creak. I did not hear Saeki. Door looked closed. I did not check if locked. I did see a thin pale line near top of door, like spider silk catching light, but old houses have spiders. I only remembered after Goro argued about line tricks.

No, I did not kill him. I owed Saeki money, yes, but he also paid for my son’s medicine.

---

### 9. Old scandal file, mostly hearsay

Twelve years ago, composer Rei Kisaragi died in a fire after being accused of plagiarizing the “Nocturne at Tideglass.” Saeki, Toma, and an unnamed technician testified against Rei. Rights moved to Saeki’s company. Rei’s final score vanished. Some say Rei left a child; records sealed.

A white pierrot mask was found outside the burned studio. Fans made a revenge legend. Every anniversary someone leaves sheet music at the pier.

Police at the time: accidental fire. Local rumor: locked room from outside; oil heater; insurance fraud; false testimony; cover-up. No proof in packet.

---

### 10. Aoi’s private message draft, unsent

“Rei did not steal anything. Saeki made us lie. Toma wrote the review, Kei’s predecessor doctored the recording, and I stayed silent. I was twenty. I want to tell the press but Saeki says he’ll release my old letters and destroy me. If something happens tonight, it is not because I hate him. It is because he has held us all hostage for years.”

Draft timestamp says 20:58, but phone clock may be wrong; island router time drifted earlier that day.

---

### 11. Toma’s balcony claim

At 20:36 I saw a pale mask near the roof edge above the Blue Room wing. It turned away. Too tall for a child, too quick for old Mika. Rain distorted everything. I admit I had two whiskies. I went outside for signal because Saeki threatened to leak my debts.

My shoes are wet because balcony. I did not enter Blue Room. I cannot play a note. I did not know about any laptop cue.

Private note: Toma’s umbrella was dry inside but wet outside, normal. Mud on right trouser knee. Claims slipped.

---

### 12. White Pierrot sighting, from server

At 20:49, while carrying plates, I saw a white sleeve disappear near prop closet. Maybe costume. Maybe tablecloth. Goro came back with candles a few minutes before or after? I was busy.

At 21:13, when music started, Aoi screamed “Rei!” before anyone said what piece it was.

---

### 13. Physical bits collected poorly

- black tape scrap under transom hinge, adhesive similar? not tested
- transparent monofilament fragment caught on splinter above door frame, 4 cm only
- orange liqueur glass; fingerprints smudged, Saeki partial, maybe gloved wipe
- bottle from Saeki cabinet, stopper touched by at least Saeki/Mika/unknown
- small Bluetooth speaker shell found next afternoon inside piano lower cavity? Officer says “maybe old practice metronome speaker”; battery at 6%; paired name `OldPianoShell?`
- raincoat in laundry with faint orange smell; tag torn; size fits Kei or Goro, too large for Yuri/Aoi, maybe anyone could borrow
- old white pierrot costume damp at hem; no blood; prop closet accessible from corridor
- Kei’s left cuff damp at 20:48; Goro’s sleeve waxy; Mori’s bandage real cut? unknown
- Dr. Mori’s medical bag contains sedatives, insulin, syringes, no obvious cyanide; clinic stores toxic reagents for pest control, key held by clinic nurse not present

---

### 14. Argument after discovery, near-transcript

Inspector: “The actress threatened him. She knew the music. She screamed before the title.”

Yuri: “Everyone from the old scandal knew that piece.”

Kei: “Playback theory is nonsense. You all heard the resonance.”

Goro: “Resonance can be faked if speaker is in the piano. You know that better than us.”

Mori: “Death time cannot clear anyone. Poison, heart, shock — test first.”

Mika: “The bolt was shut. I saw it when they broke the door.”

Toma: “Then explain the mask on roof.”

Aoi: “The mask is theater trash. Saeki’s guilt killed him, not me.”

---

### 15. Deliberately confusing clue list from notebook

- “traitor hears himself” maybe means playback of old confession?
- Saeki disliked orange liqueur BUT owned bottle
- Kei says live when expert Yuri says playback-like
- Mori could poison but why music trick?
- Goro could bolt door but why sound files?
- Aoi motive loud; too loud?
- Toma lies about roof? wet knee; debts
- Mika saw line at 21:04 = before music, after likely death?
- If Saeki alive at 21:04, he might have removed line? unless line outside only
- if line visible at 21:04, killer had already set lock trick and left room
- if music at 21:12 playback, everyone’s alibi at 21:12 weak
- if death before 20:48, Kei/Mori/Goro/Toma all had windows
- if poison in drink, killer needed private access to Saeki or cabinet/glass
- if injection, doctor rises; but puncture may be diabetic/medical noise
- Bluetooth speaker at 6% battery suggests recent use? maybe old battery drains
- transom cannot pass adult, but can pass line

---

## Output request

Do not solve by recognizing any source case. This is original. Treat every clue as potentially noisy.

Preferred answer format:

```md
## Facts / constraints ledger
F1 ...
C1 ...

## Candidate paths
CS1 ... path_cost ... relative_weight if computed
CS2 ...

## Strict events
...

## Final
Strongly supported:
- ...

Speculative:
- ...

Best next test:
- ...
```
