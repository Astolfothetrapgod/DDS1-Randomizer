# NOTES — Digital Devil Saga (SLUS-20974) — reverse engineering

Legend: ✅ validated (with the evidence) · 🟡 hypothesis (with a way to check it) · ❌ rejected

---

## 0. Reference dump

| | |
|---|---|
| File | `~/Jeux/PS2/SLUS-20974 (1.00).iso` (link `iso/dds1_us.iso`) |
| Size | 4,539,547,648 bytes |
| MD5 | `ae4330140ef56f9eb1c689b9bb383401` |
| SHA-1 | `f022cc27d2c333db64f1f1a46b312aafc5ce632e` |
| SYSTEM.CNF | `BOOT2=cdrom0:\SLUS_209.74;1` / `VER=1.00` / `VMODE=NTSC` |

✅ **Dump identical to Redump disc #253** (*Shin Megami Tensei: Digital Devil Saga*, USA, SLUS 20974, v1.00, Original edition): MD5, SHA-1 and size match. The offsets found here therefore hold for any clean dump of this version.

✅ PCSX2 CRC of the ELF = `D7273511` (XOR of the 32-bit words of `SLUS_209.74`, computed in Python; confirmed by the savestate names `SLUS-20974 (D7273511).NN.p2s`). PCSX2 cheats/pnach are indexed by this CRC.

---

## 1. ISO contents (ISO9660)

71 files. Full inventory: `docs/inventory.md` (sorted by LBA = 2048-byte sector on the disc).

| LBA | File | Size | Finding |
|---:|---|---:|---|
| 352–689 | `IRX/*.IRX`, `IRX/IOPRP25x.IMG` | ~500 KB | ✅ `.IRX` = ELF (IOP modules). `IOPRP*.IMG` start with `RESET` |
| 693–1314428 | `MOVIE/*.IPS` (45), `MOVIE2/*.IPS`, `MOVIE2/*.IPU` | ~2.6 GB | Videos. `.IPS`: magic `IPS0` at +8. Out of scope for the randomizer |
| 1314429+ | `SOUNDIRX/`, `USERIRX/` | | ✅ ELF (sound IOP modules) |
| 1314514 | **`DDS3.DDT`** | 191,968 bytes | ✅ index of DDS3.IMG, see §2 |
| 1314608 | **`DDS3.IMG`** | 1,509,355,520 bytes | ✅ data archive, see §2 |
| 2051598 | **`SLUS_209.74`** | 2,895,680 bytes | ✅ ELF, main executable (EE) |
| 2053012 | `SYSTEM.CNF` | 51 bytes | text |
| 2053013, 2107534 | `ZZZ100MB.DAT`, `ZZZ200MB.DAT` | 106 / 213 MB | ❌ **not** zero padding (test: not 100 % zeros). Contains `APCM` at +8. 🟡 Probably placed at the end of the disc to push the data towards the outside of the DVD (faster reads). Irrelevant for us |

**Lesson**: physical order matters. If a file grows, everything after it shifts. Rewriting the ISO with identical sizes (or appending at the end) avoids having to fix LBAs that may be hard-coded in the ELF.

---

## 2. DDS3.DDT / DDS3.IMG — ✅ VALIDATED

Format source: `AtlusFileSystemLibrary/Source/AtlusFileSystemLibrary/FileSystems/DDS3/DDS3FileSystem.cs` (TGE, GPL-2.0). Same format as Nocturne and Raidou (Amicitia wiki, *IMG* page).

DDT entry = **12 bytes, little-endian**:

| Off | Type | Field | Meaning |
|---:|---|---|---|
| 0x0 | u32 | name_offset | offset of the name in the DDT (ASCII terminated by `\0`); 0 = unnamed root |
| 0x4 | u32 | offset | **directory**: offset of the child entries in the DDT · **file**: sector number (×0x800) in the IMG |
| 0x8 | i32 | count | **< 0**: directory of `-count` children · **≥ 0**: file of `count` bytes |

Root at offset 0: `00000000 0C000000 E9FFFFFF` = unnamed, children at 0x0C, 23 children.

**Evidence** (`python scripts/ddt.py check …`):
- 604 directories, 7,661 files, all names in printable ASCII.
- No file goes past the end of the IMG, no overlap between non-empty files.
- Sum of the sizes rounded to the sector = **exactly** the size of the IMG (100.00 %). A misunderstood format would not land on the exact byte.
- The file at sector 0 (`ps2cdimg`) is the ELF visible at the start of the IMG.

**Peculiarities**:
- 4 zero-byte files (`font/ndw`, `fld/e/f802/converr.txt`, `fld/e/f802/f802_001.dbg`, `model/event/extra/low_tex/low_tex.txt`) point to the sector of a neighbouring file. To be reproduced as is if the DDT is ever rewritten.
- Children seem sorted by name (TGE's code sorts them when writing). 🟡 Not checked on the original.
- 🟡 `ps2cdimg` (ELF, ~0.4 MB): unknown role. To be opened in Ghidra.

**Check in ImHex**: open `extracted/DDS3.DDT`, load `imhex/patterns/dds3_ddt.hexpat`, Evaluate. You should see `root` with 23 `children`, including `battle`.
✅ 2026-09-23: pattern run without error (code 0, 0.75 s, 58,456 objects). `root` = 0x0–0xB (12 bytes). First child at 0x0C = `20 01 00 00 | AC 01 00 00 | F0 FF FF FF` → name at 0x120 = `battle`, children at 0x1AC, directory of 16 children (confirmed by `scripts/ddt.py`). Next ones: `bill` (35 children), `camp` (2), `conf` (1).

Full list: `docs/dds3_files.tsv` (path, sector, offset in the IMG, size, position of the entry in the DDT).

Volume per root directory: `fld` 387 MB, `event` 359 MB, `model` 302 MB, `voice` 145 MB, `sound` 142 MB, `sobed` 45 MB, … **`battle` 2.9 MB (112 files)**, `camp` 2.3 MB.

---

## 2 bis. Ghidra — executable `SLUS_209.74`

- Project `ghidra/DDS1`, imported on 2026-09-23. Language **R5900 / Emotion Engine** (plugin ghidra-emotionengine-reloaded v2.1.37). ✅ The log shows `r5900.slaspec` being compiled.
- MD5 of the ELF: `5c357d5afe565bea62c4ca613470f678`
- `_mips_gp0_value = 0x3C0CF0`: value of the `$gp` register. Accesses `lw xx, N($gp)` target `0x3C0CF0 + N`.
- Harmless messages at import: empty `.vubss` and `.mdebug.eabi64` sections ignored. Conflict on the `rom0` block (BIOS, 0x1FC00000) defined by the plugin: no effect, the BIOS is not analysed.
- Automatic analysis **not run yet**: not needed so far, the data is in the .TBL files and read with capstone (see "Mantras", "Items, chests, shops").

---

## 3. `battle/*.TBL` tables

| File | IMG sector | Size | 🟡 Assumed role (from the name only) |
|---|---:|---:|---|
| `battle/UNIT.TBL` | 811 | 67,600 | unit data (enemies?) |
| `battle/SKILL.TBL` | 560 | 34,496 | skills / mantras |
| `battle/ENCOUNT.TBL` | 389 | 135,136 | encounters (enemy groups) |
| `battle/AICALC.TBL` | 209 | 340,016 | enemy AI |
| `battle/EFFECT.TBL`, `MSG.TBL`, `SOUND.TBL`, `VISUAL.TBL` | | | effects, battle texts, sounds, visuals |

In P5, `ENCOUNT.TBL` describes the enemy groups of each battle. That is a hint, not evidence for DDS.

### .TBL container — ✅ VALIDATED on UNIT, SKILL, ENCOUNT, AICALC

Sequence of blocks: `u32 size` + `size` bytes of data, then zero padding up to the next multiple of **16**.
Evidence: chaining the sizes lands exactly on the end of the file for the 4 tables with a 16-byte alignment. With a 1-byte alignment, AICALC does not land right.

| Table | Blocks (sizes in bytes) |
|---|---|
| SKILL | 1216, 28672, 1360, 768, 320, 1536, 512 |
| UNIT | 6720, 1216, 1216, 29184, 29184 |
| ENCOUNT | 40960, 12352, 67072, 128, 12352, 2176 |
| AICALC | 133632, 2668, 195070, 8604 |

### Tables in RAM — ✅ VALIDATED (savestates of 2026-09-23)

`scripts/ramsearch.py`: **every block** of UNIT, SKILL, ENCOUNT and AICALC is present **identically** in `eeMemory.bin`, in battle (slot 1) as well as outside battle (slot 2), at the same addresses. Consequences:
- the game loads these files as is, **modifying the .TBL is enough** (unlike Nocturne, where the data is in the ELF);
- the tables stay loaded permanently and do not change in battle: they are reference data;
- ⚠️ a savestate therefore contains the **old** table: to test a patch, the game must be restarted.

EE addresses (block data, without the size header):

| Table | Block → address |
|---|---|
| UNIT (✅ stable after a restart) | 0 → 0x00F72B00 · 1 → 0x00F74580 · 2 → 0x00F74A80 · 3 → 0x00F74F80 · 4 → 0x00F7C180 |
| SKILL | 0 → 0x00F6AA80 · 1 → 0x00F6AF80 · 2 → 0x00F71F80 · 3 → 0x00446FC0 · 4 → 0x0044ADC0 · 5 → 0x00F72500 · 6 → 0x0044AFC0 |
| ENCOUNT | 0 → 0x00F83380 · 1 → 0x00F8D380 · 2 → 0x00F90400 · 3 → 0x00443BC0 · 4 → 0x00FA0A00 · 5 → 0x00FA3A80 |
| AICALC | 0 → 0x00FA4300 · 1 → 0x00FC4D00 · 2 → 0x00FC5780 · 3 → 0x00FF5180 |

All these addresses are outside the ELF (`.bss` ends at 0x0040C5F0): memory allocated at load time.

### Party records in RAM (outside battle) — ✅ VALIDATED (boss test 3 cheat: level and stats applied in game)

Array of **0x1A4-byte records**: Serph at **0x01141D60**, Heat at 0x01141F04, Argilla at 0x011420A8 (same addresses in slots 1 and 3 of 2026-09-25). Same format as bytes +0x20… of a battle unit (battle makes a copy):
+0x00 u32 0x1007 · +0x04 u16 id (1 Serph, 3 Heat, 4 Argilla) · +0x06 HP · +0x08 max HP · +0x0A MP · +0x0C max MP · +0x10 u32 **total Karma** · +0x14 u16 **level** · +0x16 **St Vi Ma Ag Lu** (5 × u8) · +0x22… **assigned** skills (column "ASSIGNED" of the Set menu: Serph Bufu, Void Ice, Hell Thrust, Devour); ❓ learned skills ("LEARNED") are stored elsewhere.
Evidence: the 5 stat bytes seen in battle are found there (and nowhere else except copies); after the victory over Usas, Serph's total Karma 446 → 646 and Heat's 490 → 690 = **+200 = Usas' Karma** in the spoiler (Argilla, KO, unchanged); level 6 → 7 with +3 stat points and +4 max HP / +4 max MP.
- ✅ **Max HP / max MP are recomputed at the start of battle** (the record value is only a copy): Atlus' formulas in AICALC block 3, `calc_MAXMG` and `calc_MAXSP` (`work/bf/AICALC_calc.flow`): **max HP = level × 4 + Vi × f + 10**, **max MP = level × 4 + Ma × f + 8** (the `+10`/`+8` only if `FUNCTION_0175()` ❓ = "player unit"?). f (`FUNCTION_0186/0187`) = **4** for Serph, Heat and Argilla: the 6 values measured in battle (levels 6 and 15) and the 3 level-7 records all match. `FUNCTION_016F(1)` = Vi, `(2)` = Ma → confirms the St, Vi, Ma order again.

### Battle units (RAM) — 🟡 partly validated

Structures of **0x380** bytes. Party at 0x00EBE200, 0x00EBE580, 0x00EBE900; enemies at 0x00EBEC80, 0x00EBF000, then ❌ **not necessarily contiguous**: with 3 enemies, the 3rd was at 0x00ECC680. Units are taken from a pool of slots, not a contiguous array.
+0x08 = global unit number in the battle (4, 5, 6 party; 7, 8, 9 enemies) · +0x1C = index within its side (0, 1, 2) · +0x18 = side? (0x0A party, 0x02 enemies).
First original battle: two enemies with id 284.

| Off | Field | Evidence |
|---:|---|---|
| +0x24 | u16 unit id (Serph 1, Heat 3, Argilla 4, enemy 284) | ✅ for 284 = index in UNIT.TBL block 3 |
| +0x26 / +0x28 | u16 current HP / max HP | ✅ 30/34/30 as on screen |
| +0x2A / +0x2C | u16 current MP / max MP | ✅ 24/20/28 as on screen |
| +0x34 | level | 🟡 1 for the party, 2 for the enemy (= UNIT.TBL) |
| +0x36..+0x3A | 5 stats | 🟡 identical to UNIT.TBL for the enemy |
| +0x42.. | u16 skills | 🟡 enemy 0x73, 0x70 = UNIT.TBL |

### UNIT.TBL block 3 = unit records — ✅ VALIDATED

**384 entries × 0x4C (76) bytes**, index = unit id (entry 284 = enemy of the first battle).
Evidence: 384 × 0x4C = block size, without remainder; HP (+0x06) == max HP (+0x08) for **384/384** entries; MP (+0x0A) == max MP (+0x0C) for 382/384; entry 284 matches the enemy seen in RAM byte for byte.

| Off | Type | Field | Status |
|---:|---|---|---|
| +0x00 | u32 | ? (0 for 284) | ❓ |
| +0x04 | u8 | **race** (index in MSG.TBL block 6) | ✅ 3 cases on screen: Demon Onmoraki, Aerial Macha, Fiend Slime |
| +0x05 | u8 | level | 🟡 (2 for 284, 63 for entry 1) |
| +0x06 / +0x08 | u16 | HP / max HP | ✅ |
| +0x0A / +0x0C | u16 | MP / max MP | ✅ |
| +0x0E | u16 | ? (= own id for 283 and 285, but 90 for 284) | ❓ 3D model / appearance? |
| +0x10..+0x14 | 5 × u8 | stats **St, Vi, Ma, Ag, Lu** | ✅ order seen on screen (Heat) |
| +0x15 | u8 | ? (1) | ❓ |
| +0x16 | u8 | 0xFF = special unit (bosses, story units) | 🟡 |
| +0x18.. | u16[] | skills (0x73 Venom Claw, 0x70 Body Rush for 284) | ✅ via MSG.TBL block 7 |
| +0x28 | u32 ? | **base Macca** (Onmoraki 40, Preta 55, Slime 50…); the game gives ×1.5 (rounded down) | ✅ 1 Slime → 75 Macca (50 × 1.5); 1 Preta → 82 (55 × 1.5) |
| +0x2C | u16 | **Karma** (= DDS experience) | ✅ 1 Slime → 9 Karma; 1 Preta → 10 |
| +0x2E | u16 | Onmoraki 18, Preta 21, Ghoul 66, Decarabia 1000 | 🟡 Atma points? (shown "???" at the start of the game) |
| +0x30 | u16 | often 2 × +0x2E (36, 42, 132, 2000) | 🟡 reward? |
| rest | | +0x32 = 1, +0x36 = 16, +0x3E = 256 almost everywhere | ❓ |

Result screen (savestates of 2026-09-24): totals in RAM at 0x00D3DB44 and 0x00F09C68 (u32 Macca, u32 Karma, then a constant 7). 🟡 The ×1.5 on Macca: unknown cause (moon phase? fixed rule?).

**Stats**: order ✅ **St, Vi, Ma, Ag, Lu** (Heat's level-up screen: 5 5 2 3 3 at level 1 = bytes `05 05 02 03 03` in RAM).

Raw entry 284: `00000000 07 02 1F00 1F00 2C00 2C00 5A00 04 01 02 02 04 01 FF00 7300 7000 …`

### UNIT.TBL block 4 = affinities — ✅ VALIDATED (in game + Analyze texts)

384 × 0x4C = **19 × u32** per unit (columns 16–18 always 0). 🟡 u32 = **flags (high 16 bits) + percentage (low 16 bits)**: `00000064` 100 %; `00000032` 50 % (resists); `80000096` / `800000C8` weak 150 / 200 % (bit 0x8000); `00010000` null (0x0001); `00020000` repel (0x0002); `00040064` drain (0x0004); `0x0010` ❓.
🟡 **Column = SKILL.TBL element**: 0 physical, 1 gun, 2 fire, 3 ice, 4 elec, 5 force, 6 earth, 7 almighty (100 % for 170/186 named units), 8 light/expel, 9 dark/death (often "null"), 10 charm, 11 poison, 12 mute, 13 panic, 14 nerve, 15 ❓.
- ❌ Validation through the texts of MSG.TBL block 0 impossible: descriptions 1–6 are the **party characters'** (1 Serph "Strong:ice_Weak:fire", 3 Heat "Strong:fire_Weak:ice" = status screen, 4 Argilla earth, 5 Gale force, 6 Cielo elec); only 15/179 enemy units have a line equal to a description (chance). Descriptions 94+ = "Reserve".
- Predictions (first dungeon): Onmoraki fire 50 %, weak to ice; Preta physical 130 %, weak to fire and earth; Ghoul (and the tutorial Ghoul, same row) weak to fire and earth; Slime physical 50 %, weak to fire/ice/earth, light 200 %, darkness null…

**Test** (`scripts/test_affinity.py`): Preta (102): physical → null (`00010000`), ice → weak (`80000096`); zone 2 → encounter 518 (2 Preta). Control: Analyze on the tutorial Ghoul (predicted: weak to fire and earth).
Result: ✅ **in battle, the modified Preta is immune to physical and weak to ice (extra turn)**. ⚠️ But Analyze shows "Weak: fire/earth" (original affinities) → the Analyze text is stored separately. Ghoul: all "?" (Analyze only reveals a species after defeating it once).

**Analyze text = MSG.TBL block 2**: 384 × 3 lines of **63 bytes** (72,576 = 384 × 189), line 1 = affinity summary, Atlus format "Strong: fire_Weak: ice_Null: death…" (categories Strong / Weak / Null / Repel / Drain, elements separated by "/", groupings "ailments", "all magic").
- Text ↔ block 4 comparison on named units: **82/99 consistent** (tolerating Atlus' typos: missing separator, "Strng", text cut at 63 characters). The 17 others: incomplete summaries (Atlus often omits "Strong", e.g. Tan-Ki resists elec and ice), special wordings ("all except"), Mitama (excluded).
- Examples: Onmoraki "Strong: fire_Weak: ice" = fire 50 %, weak to ice; Slime "Strong: phys_Weak: fire/ice/earth/expel_Null: death" = block 4 exactly.
- The "Skills" list of Analyze = record UNIT +0x18 (Preta: Zio, Zan, Body Rush) ✅; the spells actually cast = AI (AICALC).
→ Randomizing affinities requires **also rewriting line 1 of the Analyze text** (≤ 62 characters + `\0`).

### Blocks 1 and 2 (1216 bytes): ❓ 1216 = 304 × 4 or 608 × 2; does not match the 384 units. To be studied.

### Modification test

`scripts/patch_unit.py work/dds1_test.iso 284 999`: HP of enemy 284 from 31 → 999 in a copy of the ISO.
`cmp`: only 4 bytes differ (0xA093504A–0xA093504D), `1F 00` → `E7 03` twice. Original ISO intact (MD5 unchanged).
In-game result: ✅ **VALIDATED** (2026-09-23). Cold boot on `dds1_test.iso`, first battle: the enemy takes 6 hits (1 critical) without falling. Savestate read back: unit 3 = id 284, **HP 939/999** (60 damage taken), unit 4 = **999/999**. The patched record is in RAM at 0x00F7A3D4 (= 0x00F74F80 + 284×0x4C + 4), the old one is gone.
→ **The game reads enemy stats from UNIT.TBL.** The table load addresses stay the same after a full restart.

### Copying a record into a free slot — ✅ works (model through a DDT alias), not used by the randomizer

Free slots of UNIT.TBL block 3 (unnamed and entirely zero): **344 to 383** (40 slots). 103 other unnamed slots contain data (level-99 placeholders?). Placeholder names are their index in hex (slot 344 = `0x158`).
Need: 50 of the 90 shuffled species also appear outside random battles; rewriting them would modify those battles → copies needed for those only.

Test (`scripts/test_clone.py`, 80 bytes modified): Macha (24) copied into slot 344 (block 3, block 4, MSG.TBL name), encounter 14 = [344], zone 2 = encounter 14 only.
Expected: a named Macha that acts and gives 50 Karma and 210 Macca (140 × 1.5).
Result of test 1: ❌ the game shows "**Aerial Macha**" (name read from slot 344 ✅; race Aerial = #3 = Macha's +0x04 ✅, 2nd confirmation), but **no model**, and the attack never plays: **game stuck**.
→ Other tables depend on the unit number.

**Tables indexed by unit** (384-row blocks of battle/*.TBL):
| Block | Row | Evidence | Role |
|---|---:|---|---|
| UNIT block 3 | 76 | empty rows = exactly slots 344–383 | record ✅ |
| UNIT block 4 | 76 | row 284 = row 90 (Atlus' copy) | affinities 🟡 |
| **VISUAL block 1** | 624 | empty rows = slots 344–383; 284 ≠ 90 on 3 bytes only: float at +0x10 = 1.5 (Ghoul) / 1.6 (tutorial Ghoul) / 1.3 (Macha) | model, **scale** 🟡 |
| **EFFECT block 2** | 24 | empty rows = slots 344–383; 284 = 90 | effects 🟡 |
| **SOUND block 1** | 116 | empty rows = slots 344–383; 284 = 90 | sounds 🟡 |
| **AICALC block 0** | 348 | slots 344–383 = "default" row (199 identical rows); Macha has its own row | AI ✅ |
| VISUAL block 0, SKILL blocks 3 and 5 | | no hint | untouched |

Test 2 (same script, copy of the 6 rows + name, 359 bytes modified): 🟡 **partial**. Macha's skills ✅ (AI copied), **50 Karma** ✅, no freeze ✅, but **wrong model** (small purple creature) and actions in slow motion. Macca 140 (×1.0, see below).

**Models**: ❌ correction of a mistake of mine: I had written "160 models, 000 to 159"; my search only kept decimal names. In fact: **`model/devil/%03X.PB`** (+ `%03X_ms.LB`, `%03X_ms.ls`), **name = unit number in hexadecimal** (string `%s%03X_ms.LB` and `/model/devil/` in the ELF). 305 files: 018 = Macha (24), 05A = Ghoul (90), 11C = 284, 158 = 344…
- **162 files are identical** to the placeholder model (`dammy.PB`, md5 78a69098; purple creature): 11C (284), 158 (344), the "Reserve" ones, etc.
- Atlus' copies (284 Ghoul → 90, 286 Cockatrice → 40, 291 Macha → 24, 295 Apis → 100, 336 Titania → 43…) all have the placeholder file **and** +0x0E = the original → ✅ **+0x0E = model used** (at least up to 343).
- Our copy in 344 (+0x0E = 24) showed the placeholder. 🟡 Hypothesis: the game only honours +0x0E for units 0–343 (344 = number of real units; last named one: Omoikane 343). To check one day in Ghidra (constant 0x158).
- **"Reserve" slots 112–166** (55 slots, name "Reserve"/"(Reserve)", +0x0E = 0, placeholder model, no encounter): unused reserved slots below the 344 limit → candidates for copies.

Test 3: copy of Macha into slot **112** (Reserve), 154 bytes modified: 🟡 Macha's skills ✅, **normal speed** ✅ (placeholder animations consistent with its model), but **still the placeholder model**.
- ❌ Hypothesis "+0x0E ignored beyond 343" rejected: even in slot 112, +0x0E = 24 is not followed.
- ❌ `_ms.LB` = **sound** archive (labels `SMG`, `MIDI`; 05A and 11C only differ by the MIDI sequence numbers 0x15A0 / 0x21C0), `_ms.ls` = text list of the sounds. Not models.
- ❌ Hypothesis "+0x16 = 0xFF → use +0x0E" rejected: 0xFF is present on every boss and story unit (which have their real model). +0x16 = 0xFF 🟡 = special / story unit.
- ❌ No (unit, model) table in RAM or in the ELF; no field of the battle structure equals 24 / 90 (Macha / tutorial Ghoul): the model is probably referenced through a pointer.
- ❓ How the tutorial Ghoul (284, placeholder file) gets the model of Ghoul 90 remains unexplained → to study one day in Ghidra (code using `/model/devil/`, VA ≈ 0x3A6940).

**Workaround**: the game loads `model/devil/%03X.*` from the unit number. The **DDT entries** of `070.PB`, `070_ms.LB`, `070_ms.ls` are made to point to the data of `018.*` (sector + size; no byte of DDS3.IMG moved, DDT of the same size). `GameISO.alias()` + `write_ddt()`. Checked by reading the ISO back: `070.PB` = bytes of `018.PB`, 3 DDT entries modified.
Test 4 (copy + DDT alias, 166 bytes modified): ✅ **right model (Macha)**, Macha's skills, no freeze. ⚠️ Slow loading when the enemy acts.

Other files named after the unit number (hex):
- `sobed/%03X.BED` (629 files, 000 to 1FF, + variants `_01`…): one per unit; the tutorial Ghoul (11C) has its own (168,640 bytes), different from 05A (82,864 bytes). 🟡 animations / action scripts of the unit (in `battle/`, .BED files are named after skills: AGI.BED, ATTACK.BED…). Macha: 018.BED 57,760 bytes; slot 112: 070.BED 25,168 bytes → 🟡 likely cause of the slowness.
- `model/on/%03X_on.PB`: 24 units only; 018_on = 123_on (identical): generic? ❓
- `soundat3/mp%03X.at3`: sound (Macha: mp018.at3); no equivalent for 070. ❓

Test 5 (+ alias `sobed/070.BED` → `018.BED`; 4 DDT entries modified): ⚠️ still slow on the copied Macha's turn.
- Files specific to the tutorial Ghoul (11C): model/devil 11C.PB, _ms.LB, _ms.ls, sobed/11C.BED (+ sound me11c.at3 listed in the .ls) → slot 112 now has the equivalent of each. Nothing is missing compared to an Atlus copy.
- `soundat3/mp%03X.at3`: 28 units only (optional). `soundat3/me%03X.at3`: 188 units, listed by the `_ms.ls`.

Test 6 = **control test**: same zone 2 → encounter 14, but with the **original Macha (id 24)**. Only ENCOUNT.TBL modified. If it is also slow, the slowness comes from Macha itself, not from the copy. Result: ✅ **the real Macha has no loading time**, and **it plays a sound on every action**, missing on the copy (the tester's observation).
→ ✅ The copy waits for a **sound loaded from the unit number**, which does not exist: very probably `soundat3/me%03x.at3` (188 units have it, including Atlus' copies 11C and 123; `me070.at3` does not exist). The game waits, then continues without sound. Aliasing the `.ls` (which lists me018) is not enough.

**Limit**: only an existing DDT entry can be redirected. Unused slots having all 5 files (PB, _ms.LB, _ms.ls, sobed, me): **only 35 and 60**. No Reserve slot has an `me` file. Adding entries would require rebuilding the DDT (544-byte margin before DDS3.IMG on the disc, i.e. ~20 entries).

**Outcome for rescaling** (shuffled species that appear outside active random battles):
| Where | Species | Rewrite the record in place? |
|---|---:|---|
| nowhere else | 40 | ✅ |
| only in random encounters that no active zone uses | 27 | ✅ (dead data) |
| special encounters 768+ | 7 (+1 mixed) | ❓ role of 768+ to check |
| scripted battles 256–383 | 15 (Ghoul, Onmoraki, Preta, Yaka, Gyu-Ki, Fuu-Ki, Sui-Ki, Kin-Ki…) | ❌ copy needed, or no rescaling |
→ **67 species out of 90 can be rescaled in place**, without a copy.

**Macca**: ×1.5 (1 Slime, moon 5/8, 3 characters alive); ×1.0 (1 copied Macha, moon HALF, only 1 character alive). ❓ Two variables change: cause not determined.
**Race**: ✅ 3 cases checked on screen: Onmoraki "Demon", Macha "Aerial", Slime "Fiend" = MSG.TBL block 6 [+0x04].
---

## 4. ENCOUNT.TBL block 0 = encounters — ✅ VALIDATED (enemy slots)

**1024 entries × 0x28 (40) bytes**, index = encounter number. 754 non-empty entries.
Evidence: period 0x28 = 95.5 % identical bytes (best score), 1024 × 0x28 = exact block size; encounter 257 contains `284, 284`, the enemy of the first battle.

| Off | Type | Field | Status |
|---:|---|---|---|
| +0x00 | u16 | 0 = random battle? 1 = scripted battle / boss? | 🟡 entries 0–255 → 0, 256+ → 1 |
| +0x04 | u16 | **next encounter** (waves, reinforcements) | ✅ data: 47 encounters, targets never empty, no loop; chains 289→290→291→292 (Kelpie), 293→…→297 (Nue), 260→284→283 (Ikusa), 276→326→327, 314→313 (Jatayu→Garuda); also in random battles: 581–603 → 575/577 (reinforcements?) |
| **+0x06..+0x12** | **7 × u16** | **enemy ids** (index in UNIT.TBL block 3), 0 = empty, not always filled from the start (bosses in slot 1: see "Boss shuffle") | ✅ |
| +0x14..+0x1B | | always 0 | — |
| +0x1C | u16 | 222, 223, 224… | ❓ scenery / arena? |
| +0x1E, +0x20, +0x22, +0x24 | u16 | 2–6; 0x050D / 0x050B; …; 3–6 | ❓ |
| +0x26 | u16 | **boss battle number** 901–920 | ✅ data: 19 unique values (913 missing), only in 256–383, always with a +0x16 = 0xFF unit; story order. The story continues from it (boss test 2) |

Slot filling: +0x06 in 556 entries, +0x08 in 440, +0x0A in 320, +0x0C in 62, +0x0E in 19, +0x10 in 2, +0x12 in 1.

**In-game test ✅ (2026-09-23)**: `scripts/patch_encounter.py work/dds1_test.iso 257 --expect 284,284 --set 99,99,99` (5 bytes modified). On a cold boot, the first battle has **3 bulb creatures** instead of 2 green humanoids. In RAM, 3 units with id 99, HP 30/30, MP 34/34, stats `02 03 05 04 02` = record 99 of UNIT.TBL. The tutorial did not crash with 3 enemies instead of 2.

Notable encounters:
- 14, 15, 16, 21, 22: 1 to 5 × unit 99 (level 1), first random battles?
- 255: units 94, 95, 96, 97 (level 1, 300–600 HP, 999 MP) ❓
- 256+: scripted battles. 258, 259, 261, 262…: a single enemy with id 257–264, level 8 → 38, the story bosses.

### UNIT.TBL: +0x0E = appearance — ✅ (model used by Atlus' copies, see "Copying a record")
Unit 284 (tutorial) is a weakened copy of unit 90: same +0x04 (7), same skills (0x73, 0x70), and **+0x0E = 90**. Almost every other unit has +0x0E = its own id.

### ENCOUNT.TBL block 2 = encounters per zone — ✅ VALIDATED (data + in-game test)

**128 records × 0x20C (524) bytes** (period score 94 %, 128 × 0x20C = exact block size).

| Off (in the record) | Content | Status |
|---:|---|---|
| +0x00..+0x13 | ? (record 0: `c9 00 01 00 05 00 …`, others: `00 00 00 00 05 00 …`) | ❓ |
| +0x14..+0x1B | 8 bytes, `08` or `01`. `01` only in the zones that have a 2nd list (4, 5, 8, 9, 10, 11) | ❓ list chosen by a condition (moon phase?) |
| +0x1C + l×0x7C | **list l (0 to 3)**: u32 (0, 150, 170, 200, 300…) + **20 u16 triplets (encounter, weight, x)** | ✅ data |

Evidence: 4 lists × (4 + 20 × 6) = 0x1F0, and 0x1C + 0x1F0 = 0x20C. **82 non-empty lists out of 86 add up to exactly 1000** (weight in ‰); the 4 others total 820–900 (❓). **No triplet points to an empty encounter** (411 encounters referenced).
- Encounters **0–254 and 512–767** are mixed in the same lists: they are all ordinary random battles. Also referenced: 255 (units 94–97) and 777–788.
- `x`: 0, 1, 2, 3, 255, 253, but also 768, 2560… 🟡 Maybe two separate bytes. ❓
- List u32: ❓ encounter rate?
- 83 non-empty zones. Sorted by mean level, they give the game's progression: zones 1, 2, 4, 5, 8 (levels 1–8: Preta, Onmoraki, Alp, Mou-Ryo, Slime) … zone 59 (Horus, 64). Probable duplicates (same zone visited again): 45/74, 46/75, 54/81, 55/60/76/77. **Zones 47–53 and 72 = Omoikane alone (level 99): excluded.**
- ❌ Rejected hypothesis: "a pointer in RAM to the current zone's record". The pointer to record 4, list 1 also appears in late-game savestates (Harihara battle). Fixed pointer to the start of the table: 0x003BAA3C (.sdata).
- ⚠️ My RAM unit scanner detects a "Pazuzu" (id 8) in every savestate: false positive (template structure), to be filtered.

**In-game test (2026-09-24)**: `scripts/patch_zones.py iso/dds1_us.iso work/dds1_test.iso 1=10 2=12 4=96 5=7 8=53`. Each zone of the first dungeon only contains one encounter:
zone 1 → 1 Cockatrice · zone 2 → 1 Empusa · zone 4 → 1 Slime · zone 5 → 1 Ghoul · zone 8 → 1 Nozuchi. 401 bytes modified, all in block 2.
Result: ✅ **26 random battles, all with a single enemy among the 5 imposed ones**; the 5 zones appeared (the tester's notes, section 8). Scripted battles (2 Empusa with the NPCs, Cockatrice) unchanged, as expected.
- ✅ triplet = (encounter, weight) confirmed; a list with a single triplet of weight 1000 = 100 % of that encounter.
- ✅ **A zone is not a floor**: it depends on the place **and on the story progress**. E.g. 1F rooms after the save point = zone 4 (Slime), then zone 5 (Ghoul) after the scripted battle of the 2 NPCs.
- Order of the zones in the first dungeon: zone 2 (1F after the tutorial, 2F) → 4 (1F save room, B1) → 5 (1F and 2F after the NPC battle) → 8 (2F before the boss) → 1 (1F near the entrance, at the end of the dungeon). Zones 4, 5, 8: only list 0 or 1 was observed, impossible to tell which (both were modified).

### Catalogue of scripted battles (256–383) — for the boss shuffle

84 non-empty encounters. "Special" units (+0x16 = 0xFF) in almost all of them.
- **Story bosses (+0x26)**: 901 Hayagriva (8) · 902 Camazotz (15) · 903 Usas (20) · 904 Camazotz (21) · 905 Agni (30) · 906 Rahu head + body (30) · 907 Camazotz (38) · 908 Cerberus ×3 parts · 909 Ravana ×6 · 910 Ravana · 911 Harihara (68) · 912 Harihara + 6 Cores (72) · 914 Agni (27) · 915 Vasuki (51) · 916 Temple Guard ×2 · 917 Huang Long (85) · 918 Metatron (80) · 919 Beelzebub (75) · 920 Girimehkala + Cu Chulainn + **Demi-fiend** (99).
- **Single-unit bosses** (candidates for a first shuffle): Hayagriva, Camazotz ×3, Usas, Agni ×2, Harihara (911), Vasuki, Huang Long, Metatron, Beelzebub, Ravana (910), and the bosses without a 901+ number: Garuda, Jatayu, Catoblepas, Isis, Ananta, King Frost, Feng Huang, Baihu, Long, Gui Xian, Orochi, Beelzebub (55), Titania…
- **Multi-part bosses** (risky): Rahu (head/body), Cerberus (3), Harihara + Cores, Ravana ×6, Temple Guard ×2.
- **Waves** (+0x04): Ikusa, Kelpie, Nue, Onkot, Yaka → Gyu-Ki, Jatayu → Garuda.
- "Ordinary" scripted battles: 257 (tutorial: 2 Ghoul 284), 271 Cockatrice, 272 2 Empusa (NPCs), 275, 277, 339…
- ⚠️ Risks to test: event scripts that would refer to a boss id (in-battle dialogues, end conditions), scripted "meant to be lost" battles, special AI actions (0x10xx = summons?).

**Boss shuffle (v3, `randomizer/bosses.py`, option `[bosses] shuffle`, on by default, `--no-bosses` to disable)** — criteria checkable on the data: scripted encounter (+0x00 = 1) with **a single enemy**, unit **found only in this encounter**, special (+0x16 = 0xFF), with a boss number (+0x26) **or** ≥ 1000 HP, unshared script, summons that are reserved or shuffled species → **24 places**: Hayagriva, Camazotz ×3, Usas, Agni 914, Ravana 910, Atavaka (m2), Garuda, Jatayu, Catoblepas, Isis, Ananta, Metatron, Vasuki, King Frost, Feng Huang, Baihu, Long, Gui Xian, Orochi, Beelzebub ×2, Huang Long. Excluded: Agni 905 (32767 HP = placeholder), Harihara 911 (999 HP, first phase of 912), Jinn 338 (shared script). Permutation without fixed point (stream `{seed}-boss`); boss B in A's place: A's level, Karma and Macca; HP/MP/stats on the level curve (**The tester's choice**: a sturdy boss stays sturdy, e.g. Beelzebub in Isis' place = 10,081 HP instead of 1,440); damage and percentage spells adapted (record, lists, script); unique skills kept (the tester's choice); +0x26 unchanged. The new boss takes the **exact slot** of the old one (Camazotz 259/262, Usas 261, Isis 316 and King Frost 320 are in slot 1).

**Boss HP option (v7, `[bosses] hp`, `--boss-hp`)** — the tester's screenshot run (seed 155): Beelzebub in Hayagriva's place (level 8, 1,001 HP on the curve, unique skills) is not beatable with the starting party without grinding. `hp = "curve"` (default, unchanged) or `"place"`: the new boss takes the **HP of the boss it replaces** (Beelzebub 600, Huang Long in Camazotz 2's place 666 instead of 6,142); level, MP, stats, skills, rewards and reinforcements stay those of the curve. No random draw: the rest of the seed is identical (checked: seed 155, only the boss HP lines of the spoiler change; test `test_hp_of_the_place` on 20 seeds). ✅ Validated in game (section 8, "Boss HP test"): Beelzebub 600/600 HP in battle.

**Unique boss skills option (v8, `[bosses] unique_skills = "keep" | "power"`, `--boss-unique-skills`)** — the tester's choice (2026-09-27): "power" = the unique skill keeps its name and animation, its **power** (SKILL.TBL block 1 +0x18, ✅ validated in game) follows the level of the new place. Default "keep" (the earlier decision).
- Inventory of the 24 places: most boss spells are in adaptable families and were already adapted (Beelzebub at level 8: Mazionga → Mazio, Megidolaon → Megido, Mahamaon → Mahama, Mind Scream → Death Blow; what made him hard is **Mamudoon**, instant death, nature 0, not adapted: no power to rank ❓ accuracy field). **Eligible = 14 skills** cast by one boss only and in no mantra: Skewer, Fire Storm (Hayagriva), Whirlwind, Seraph Lore (Usas), Trisagion, Fimbulvet, Narukami, Vayaviya, Titan (Isis 268), Fire of Sinai (Metatron), Hima Alaya (Vasuki), Cocytus, Frost Rush (King Frost), Celestial Ray (Huang Long). Excluded: Spiral Edge (the 3 Camazotz, different places), Shock Wave, Raving Slash, Mad Rush, Avalanche, Foul Breath (in mantras = party skills). The mantra shuffle only permutes the mantras' skills (both modes): the protected set does not change.
- Names exist twice: Celestial Ray 89 (200) / **424** (250, Huang Long), Fire of Sinai 95 (100) / **374** (90, Metatron); 89 and 95 are cast by no enemy (party or event versions ❓): never touched.
- ❌ Rejected rule: rank of the reference family (like the enemies' adaptation). Too coarse for a power: Celestial Ray at level 8 stayed at 146 (> Megidolaon 120, the almighty family starts high: Megido 70), Trisagion jumped 256 → 419 between levels 45 and 55 (slice change), Seraph Lore never moved (2-member family).
- ✅ Chosen rule: continuous curve **power × (new level / old level)^k**, k measured by log-log fit on the (species level, power) pairs of the 90 ordinary species' AI: magic on all targets 0.71 (R² 0.52, 70 pairs), on one target 0.39 (R² 0.49, 65), percentage 0.24 (R² 0.50, 15), physical 0.21 (R² 0.11: weak). A percentage never goes up. Examples: Celestial Ray at level 8 = **47** (Fire Storm, designed by Atlus for level 8: 45), Seraph Lore at level 8 = **64 %**, Fire of Sinai at level 15 = 27, Fire Storm at level 55 = 177. No random draw: the rest of the seed is identical (test).
- ✅ **Instant death adapted (v9)**: families now include instant-death spells (nature 0, darkness, mask 0x4000), ranked by the **chance** +0x25 (they have no power: 1 everywhere): Mudo 40 < Mudoon 60 (one target), Mamudo 20 < Mamudoon 30 (all). Same "rank from level" rule and replacement mechanism (record, AI lists, script) as the damage spells. Beelzebub at level 8 (seed 155): Mamudoon → Mamudo. Curse and Stone Gaze stay (single-member families).
- ❌→✅ **Bug fixed (v9)**: `read_skills` read the mask on 1 byte (+0x26 only): every "death-type" effect (high byte) looked like "no effect", and 3 families were wrongly merged: Mind Scream / Xeros-Beat (nerve 0x0100) with **Death Blow** (curse 0x0400); Power Wave / Bloodbath (none) with **Chi Blast** (charm 0x0200); Vaikunta (stone 0x0800) with Death Flies (death 0x4000). Adaptations crossed ailments (seed 155: Nue's Death Blow → Xeros-Beat, Valkyrie's Power Wave → Chi Blast). Random streams unchanged, but seeds give a different ISO than 1.2.0 where these skills are involved.
- ✅ **Special versions (v10)** — byte comparison of the 34 special versions (element 256 + base element) with the normal skill of the same name: they are **boosted copies**: cost +0x04 always lower (Maragidyne 32 → 20 MP, Megidolaon 60 → 25), accuracy +0x11 higher (99 → 100; Mahama 40 → 60), effect chance +0x25 doubled (freeze/shock 10 → 20 %, Mamudo 20 → 40 %, Mamudoon 30 → 60 %), sometimes more power (Xanadu 110 → 120, Genocide 21 → 26, Media 45 → 60); +0x34 ❓ differs (20 → 10 for fire/force/earth). Cast by ordinary species (Isis, Queen Mab, Cai-Zhi, Kin-Ki, Sui-Ki, Fuu-Ki, Ongyo-Ki) and bosses: never adapted until now (families only took elements < 255), e.g. Queen Mab at level 6 kept Maziodyne*.
  Rule (`skills.Families.special`): 22 special versions attached to the family of their normal version (same name, element − 256, same nature and target); they take its rank; rank change → the **normal** member of the new rank (all cast by ordinary enemies in the original game: animation guaranteed, tested), only if the direction holds against the special's own strength (Mamudo* 40 % moving up stays: Mamudoon is 30 %); same rank → special kept. Seed 14: Queen Mab (Empusa's place, level 6) Maziodyne*/Mazandyne*/Materadyne* → Mazio/Mazan/Matera. Not attached (no normal family): Vile Blade*, Genocide*, Xanadu*, healing and support versions.
- (Former note) Found on the way: the "special versions" of Isis' -dyne spells (element 256 + x: Maragidyne 258, Mabufudyne 259…) are also cast by ordinary species (Isis 2, Queen Mab 44, Sui-Ki 81…) and are **adapted nowhere** (families only take elements < 255): a rescaled Isis placed early keeps a 90-power Maragidyne. To study: can they join the family of their base element?

**Boss test 1** (`scripts/test_boss.py`): encounter 258 (Hayagriva, level 8, 600 HP, boss battle 901) → **Usas** (261, level 20, 2000 HP) rescaled to level 8: 854 HP, stats 8/11/9/8/3; Hell Thrust → Body Rush (record and AI); keeps Whirlwind, Hama, Hamaon, Marin Karin, Closdi/Patra. +0x26 = 901 unchanged. Questions: Usas' model and name? normal battle? **cutscene and story continuing after the victory without freezing**? Result: see section 8.

---

## 5. MSG.TBL — names (ASCII) — ✅ VALIDATED

`battle/MSG.TBL` (214,256 bytes) follows the .TBL container (14 blocks). **The text is ASCII**. `grep` on DDS3.IMG: "Bufu", "Void Ice", "light phys", "Attack" are all in this file. The ELF only contains debug labels (`Gun(Serph)`).

Blocks 0 to 9 = name lists, **fixed-size slots** (ASCII terminated by `\0`, padded with zeros; empty slots = `Reserved` or `0x000`). Slot size found by score: for each candidate size, % of "ASCII + zeros" slots → 100 % for the right one.

| Block | Slots × size | Content | Evidence |
|---|---|---|---|
| 0 | 256 × 45 | affinity descriptions (`Strong:ice_Weak:fire`) of the party characters | ✅ see UNIT block 4 |
| **1** | **98 × 19** | **mantra names** (1 Devourer, 2 Demon Beast… 88 Earth Temple, 89–97 Reserve) | ✅ see "Mantras" |
| **2** | **384 × 3 × 63** | **Analyze text** (line 1 = affinity summary) | ✅ see UNIT block 4 |
| **3** | **384 × 17** | **unit names**, index = UNIT.TBL id | ✅ 41 = Decarabia (starfish with an eye, seen in game); 284 and 90 = Ghoul (copy + borrowed model) |
| **4** | **192 × 25** | **items** (Ration, Chakra Drop, Soma…) | ✅ see "Items, chests, shops" |
| **5** | 32 × 17 | **characters**: 1 Serph, 2 Sera, 3 Heat, 4 Argilla, 5 Gale, 6 Cielo; 17+ = Atma (Varna, Agni…) | ✅ = party ids in RAM (1, 3, 4) |
| 6 | 16 × 7 | races (Deity, Evil, Aerial…) | ✅ (UNIT +0x04) |
| **7** | **624 × 17** | **skills**, index = skill id (512–601 = party passives) | ✅ Serph 0x0A = Bufu, 0x152 = Void Ice; Heat 0x73 = Venom Claw, 0x77 = Mad Rush: identical to the menus on screen |
| 8, 9 | 64 × 17, 256 × 17 | empty | — |
| 10–13 | — | messages in Atlus' `MSG1` format (BMD); block 11 = skill descriptions (`skill_<hex id>`) | see "Boss test 2" |

Consequences:
- ✅ **UNIT.TBL +0x18 = skill list** (u16, 0 = empty): Ghoul = Venom Claw, Body Rush.
- The party ids in battle (1, 3, 4) index block 5, not UNIT.TBL (UNIT 1 = Laksmi).
- UNIT 101 and 256: unnamed, level 99, 32767 HP: placeholder records, excluded.
- ✅ **In-game check (2026-09-24)**: targeting the enemy, the game shows Macha (test 2, slot 1, id 24), Decarabia (slot 2, id 41), Yaka (slot 3, id 89). Original ISO, first random battle: "**Demon Onmoraki**" above the bulb creatures, RAM = 3 × id 99. ❌ My doubt ("Onmoraki = a bird" from the series) was wrong: the game data wins over outside knowledge.

`scripts/names.py` generates `work/units.tsv` (id, name, level, HP, MP, stats, appearance, skills), `work/skills.tsv` and `work/items.tsv`. They stay in `work/` (not versioned): they are game data. **The patcher always reads the names from the player's ISO.**

### AICALC.TBL block 0 = unit AI — ✅ structure validated on the data

One **348-byte row per unit** (index = unit id, validated by the Macha copy). Row = 0x40 header (`08`/`01` bytes like in the zones: ❓ list chosen by the situation) + **7 lists of 0x28 bytes** = 5 entries of 8 bytes **(u16 probability, u16 action, u16, u16)**; 4 remaining bytes.
- action = **skill id**, **0x8000 = normal attack**, 0x8001 / 0x10xx = special actions (❓ guard, reinforcements…).
- Evidence: **586 lists add up to exactly 100**, 1 totals 105 (Atlus mistake?), the others are empty; actions: 1591 named skills, 366 attacks, 92 special. Record and AI share at least one skill for 135/152 named units.
- Kikuri-Hime: list 0 = 40 % Maragidyne, 50 % Magic Repel, 10 % attack; list 3 = 80 % Maragidyne, 20 % attack…
- ✅ **+0x02 (u16) = number of the script procedure** (AICALC block 2) run by the unit; 0 = no script (the unit follows its lists). Evidence: the 82 units with a non-zero value all have the procedure named after them (261 Usas → 9 `AI_Ushasu`, 258/259/260 Camazotz → `AI_Kamasosso_No1/2/3`, 266/302/303 Cerberus R/C/L → `AI_Keruberosu_Right/Center/Left`, 48 Jinn → `AI_Zin`…), and the decompiler writes `// Procedure Index: 9` above `AI_Ushasu`.

### AICALC.TBL block 2 = AI scripts (`FLW0` Flowscript) — ✅ format checked on the data

Reader: `randomizer/flowscript.py` (rewrites the u16 argument of a PUSHIS in place, size unchanged).
- 0x20 header: +0x08 `FLW0`, +0x10 u32 number of sections (5). +0x04 = 194,830 = **start of section 4**, not the block size (195,070) ❓ unused.
- Section table at +0x20, 16 bytes each: (u32 type, u32 element size, u32 count, u32 address). Type 0 = **72 procedures** (32 bytes: 24-byte name + u32 index of the first instruction), 1 = 2175 jump labels, 2 = **26,940 instructions** of 4 bytes, 3 = messages, 4 = strings.
- Instruction = u16 opcode + u16 argument. ✅ **PUSHI (0) and PUSHF (1) are followed by a 4-byte constant**: with this rule the whole code decodes (opcodes 0–32 only, exact end); without it, "opcodes" 52429, 13107… appear (= float constants).
- ✅ Procedures are contiguous, in order, each ending with END (9).
- Calls (numbers of Atlus-Script-Tools' `dds` library, confirmed in the bytes; counts identical to the decompilation):
  - `PUSHIS skill ; COMM 0x33` = `AI_ACT_SKILL`: **811** skills cast directly;
  - `PUSHIS unit ; PUSHIS skill ; COMM 0xE2` = `AI_ACT_SKILL_PARAM`: **23** summons (the day before I counted 22: King Frost's Celestial Gift → Jack Frost 323 was missing);
  - `PUSHIS skill ; COMM 0x19E` = `AI_CHK_MYABLESKIL`: **31** "do I have this skill?" checks (e.g. Usas checks Seraph Lore before casting it) → to be replaced like the checked spell, otherwise the check would fail.
  - All have a constant argument (none computed) ✅.
- `FUNCTION_003D()` at the end of a script = 🟡 "act according to the AICALC block 0 lists" (hypothesis: every script falls back on it when no condition is met). To check in game: a detached Jinn (see below) must act normally.

**Shuffled species that have a script** (19): 10 cast spells from their script (Isis 2, Ganesha 9, Hanuman 13, Rakshasa 16, Garuda 26, Jatayu 31, Nidhoggr 34, Jinn 48, Thoth 63, Girimehkala 77), 8 have `AllEscape_MeriBeru` (flee, no spell), Ghoul 90 `AI_GOOL2` (no spell). ⚠️ Up to v2.5, **a Garuda (level 63) brought down to level 5 still cast Mabufudyne from its script**: fixed in v2.6.
**Summons in the scripts of shuffled species**: Hanuman → Sati 4 (level 45), Purski 78 (42); Girimehkala 77 → High Pixie 53 (38); Isis 2 → itself.
**Boss summons**: Usas → Unicorn 301 (reserved); Apis → Bicorn 71, Shiisaa 70 (ordinary species); Camazotz 2 → Baphomet 324 (which summons itself); King Frost → Jack Frost 323 (reserved); Nidhoggr 269/285 → 285; Isis 268 → itself; Demi-fiend → its guards 330–335 (level 70).
**Shared scripts**: `AI_Zin` = Jinn 48 (shuffled) **and Jinn 338** (encounter 334, scripted); `AI_RAFU1` = Rahu 263 and 292; `hito_goei(2)` = the Demi-fiend's guards.

v2.6 rules (`randomizer/enemies.py`):
1. A skill replacement applies **to the record, the lists and the script** (casts + checks) of the unit.
2. Script shared with a unit outside the shuffle (Jinn 48) → **detached** (+0x02 = 0) rather than modified: the Jinn 338 of the scripted battle keeps its own. 🟡 to check in game.
3. Summon of a shuffled species → replaced by a shuffled species of level `summoner_level × summoned_level / original_summoner_level` (among the closest, stream `{seed}-invocations`). 🟡 does the game load the model of an unexpected summon? (Apis already summons units absent from its encounter, so probably yes.)
4. Summoned unit **reserved to a boss** (in no encounter, summoned by it alone) → rescaled with it, same level ratio, same id (model and sounds unchanged).

---

## 5 bis. SKILL.TBL — skills — 🟡 structure found, partly validated

.TBL container, 7 blocks: 1216, 28672, 1360, 768, 320, 1536, 512 bytes. Index = skill id (names: MSG.TBL block 7, 624 slots, 424 named; some names exist twice, e.g. Maragi 4 and 432).

### Block 1 = skill records: **512 × 56 (0x38) bytes** (period 94 %, best score)

| Off | Field | Examples | Status |
|---:|---|---|---|
| +0x02 | 1 = magic, 0 = physical? | Agi 1, Venom Claw 0 | 🟡 |
| +0x03 | cost type: 2 = MP, 1 = HP | Agi 2, Venom Claw 1 | ✅ through the costs |
| +0x04 | **cost** (MP, or % of max HP) | Agi 3, Agilao 6, Agidyne 12, Maragidyne 32 | ✅ Bufu 3 MP, Void Ice 3 MP on screen; Venom Claw 12 % and Mad Rush 15 % of 42 HP → 5 and 6 HP on screen |
| +0x08 | target: 0 = one, 1 = all | Maragi, Mabufu, Mahama 1 | 🟡 |
| +0x11 | accuracy (%) | Agi 99, Hama 65, Mahama 40 | 🟡 |
| +0x14 / +0x15 | min / max hits | Breath, Mad Rush: 2 / 4 | 🟡 |
| +0x16 | nature: 1 = damage, 8 = removes a **percentage of the current HP**, rounded down (Hama family), 0 = ailment only (Mudo) | | ✅ nature 8 (unique skills test) |
| +0x18 | **power** (for nature 8: the percentage) | Agi 30, Agilao 60, Agidyne 100; Maragi 25, Maragidyne 90; Bufu 25, Bufula 55, Bufudyne 95; Hama 50, Hamaon 66 | ✅ read by the game (unique skills test: Seraph Lore 80 → 64 applied exactly) |
| +0x24 / +0x25 / +0x26 | side effect: active (u8) / **chance %** (u8) / **mask (u16)** | Bufu 1/15/0x0004 (freeze), Zio 1/15/0x0002 (shock), Venom Claw 1/35/0x0080 (poison), Mudo 1/40/**0x4000** (death), Stone Gaze 0x0800, Curse 0x0400, Stun Needle 0x0100, Marin Karin 0x0200 | ✅ mask on 16 bits: each cure spell has the bit of the ailment it cures (Recarm 0x4000, Petradi 0x0800, Cursedi 0x0400, Paraladi 0x0100). ❌ Earlier reading "Mudo mask 0x40 at +0x26": 0x40 is the byte +0x27 |

### Block 0 = **element / category**: 608 × u16 — ✅ consistent groups over the 424 named skills

0 physical · 2 fire · 3 ice · 4 electricity · 5 force · 6 earth · 7 almighty · 8 light (Hama) · 9 darkness (Mudo) · 10 charm · 11 poison · 12 mute · 13 panic · 14 sleep/paralysis · 16 healing · 17 buffs/debuffs · 18 special (Analyze, Summon…) · 255 items · 256 + element: special versions (combos, shots) · 527 Devour · 1023 resistance passives (Void, Drain) · 1042 bonus passives (Life Bonus, Boost) · 1281 ammo.

### Block 5 = items — ✅ see "Items, chests, shops"

### "Normal" level of a skill
Measured on the 90 species of random battles (UNIT +0x18): Agi 1–13 → Agilao 13–32 → Agidyne 38–62; Zio 3–16 → Ziodyne 35–62; Dia 3 → Diarama 24–54 → Diarahan 54–64. 139 different skills among these species; some never appear there.

**Adaptation rule chosen** (`randomizer/skills.py`): family = (element, cost type, target, hits, nature, effect); only families of damage (nature 1) or percentage (nature 8) spells with ≥ 2 powers are adapted (e.g. Agi < Agilao < Agidyne, Body Rush < Hell Thrust < Hell Fang < Executioner, Hama < Hamaon). Rank = slice of the level range 1–69 (n members → n slices). Measured on the 146 damage spells of the original species: finds Atlus' choice in **53 %** of cases, against 29 % for "typical power ≈ c × level^k". A test showed that Atlus sometimes gives a spell below the level's rank (Body Rush at level 30) → monotonic rule: an enemy moving down never moves up in rank, and conversely.

**Design choice** (discussed with the tester): **never** modify a spell's power (it is shared by enemies, bosses and party members); **replace** the skill of a rescaled enemy with a member of **the same family** (element, target, nature, hits, cost type) of a rank suited to its new level.

### Mantras (party skills) — ✅ table found (ELF), shuffle validated in game

- Messages of the mantra terminal: `facility/msg/mantra/mes_data.bmd` ("Download … Mantra?", "Not enough Macca", "Prerequisites must be met first", "Already mastered") → a mantra has a **Macca price**, **prerequisites** (grid) and a **mastered** state.
- Skill names: **only in MSG.TBL block 7** ("Media" appears in no other file nor in the ELF). Slots **512–601 = the party's passive skills** (Life Bonus, Critical, Counter, Null Phys, Human Form…), with no record in SKILL.TBL block 1 (512 records); slots 608–620 = "-nda Skill", "Hunt Skill"… ❓ (categories?). Media exists at 163 and at 503 (❓ enemy / party versions).
- ❌ Rejected lead: ELF 0x222000 (503 and 504 8 bytes apart) = area that looks like bytecode (0x8000, 0x033C repeated, unaligned entries), not a table.
- ✅ **Mantra names = MSG.TBL block 1**: 98 slots of **19 bytes** (1 Devourer, 2 Demon Beast… 25 Ice Spirit, 26 Ice Demon… 88 Earth Temple, 89–97 Reserve).
- ❌ Price alone (4000 / 2500 24 entries apart): too many coincidences (increasing u32 curves at 0x2705E4, textures…).
- ✅ **Mantra table = executable `SLUS_209.74` at 0x2917B4** (RAM **0x3907B4**, segment loaded as is, present only once in the 3 savestates), **98 entries of 28 bytes** in the order of the names. Found through the signature "ids of the skills of one mantra side by side" (the tester's notes): Devourer `e0 00 79 00` (Devour 224, Hell Thrust 121), Demon Beast (Feed Frenzy, Venom Fang, Ingest Mana 553), Ice Spirit (Bufu 10, Void Ice 338), Ice Demon (Mabufu 13, Ice Boost 526), Ice Spirit exactly 24 entries after Devourer.
  | Off | Type | Field | Status |
  |---:|---|---|---|
  | +0x00 | u8 | ✅ **difficulty** (stars): Demon Beast 2 → 5 = 5 stars on screen (mantra test 2) | equal to +0x01 except King (5 / 9) |
  | +0x01 | u8 | ❓ | |
  | +0x02 | u16 | 🟡 **required level**: code 0x2CDE68 = "available if character+0x14 (level, see party records) ≥ +0x02"; Demon Beast (15) shown "N/A" for Serph at level 7; Ice Demon 5 → 15: disappears from the grid | strong |
  | +0x04 | u32 | ✅ **AP to earn to master it** (test 4: 1 AP → mastered in 1 battle); ❌ not the price (test 1); code 0x268950: divisor of a progress bar | ✅ |
  | +0x08 | 10 × u16 | **skills** (ids of MSG block 7; passives 512–601) | ✅ 4 mantras |
  Consistency: elemental lines Agi → Maragi → Maragion → Agidyne → Maragidyne (AP 600 → 55,000), late mantras at 200,000, empty Reserve entries. `randomizer/mantras.py` (reading/writing); `GameISO` now also reads and rewrites the executable (ISO9660 root).
- **Reading the code** (capstone, MIPS disassembler installed in the venv): 8 accesses to 0x3907B4 = small reader functions: +0x00 at 0x2CDD38, +0x01 at 0x2CDD88, +0x02 at 0x2CDD60, +0x04 at 0x2CD2A8 (28 callers), skills at 0x2CDE48 (u16 at +0x08 + 2 × k). 0x253100 fills the menu record of a mantra (0x58 bytes: id, +0x02, +0x01, skills, +0x04, state 1/2/3 = mastered / equipped / N/A?). 0x2CDE68 compares the character's level with +0x02. 0x268950 divides by +0x04 (AP bar).
- ❓ **The price comes from another table** (displayed prices = +0x04 × 5/3 for the 5 known cases, but test 1 rules +0x04 out as the price) — not needed by the randomizer.
- ⚠️ PCSX2 CRC: each modified ELF has its own savestate name (D5243A8F test 1, D52E34EC test 2).

**Mantra shuffle (v4, `randomizer/mantras.py`, section `[mantras]`)** — the tester's choice: both modes and both guarantees are options.
- `mode = "tiered"` (default): the 231 skills of mantras 1–88 are redistributed by a noisy sort on the required level (±5, like the enemies); `"random"`: anywhere; `"original"`. Each mantra keeps its number of skills, difficulty, required level, AP, price and place. No duplicate within a mantra (Agi is originally in Fire Spirit **and** Earth Temple). Godly Spirit (78) is left in place (special case in the code: 0x253100 tests id 0x4E).
- `guarantee_heal`: Dia in a level-1 mantra; `guarantee_group_heal`: Media at level ≤ 15 (bug found by the tests, seed 17: the 2nd guarantee swapped Media with Dia → guaranteed skills are locked).

### Items, chests, shops — ✅ found and shuffled (2026-09-26)

- ✅ **Item names: MSG.TBL block 4, 192 slots of 25 bytes.** Families: 1–28 healing (Ration, Chakra, Soma, Revival, Dis-…), 32–68 battle items (Molotov, mirrors, walls), 80–86 "Noise" (permanent stat boosts), 97–108 "Cells" (treasures to sell), **128–150 key items** (keys, orbs, Tyrant Skull, Oxygen Tank…), 161–177 ammo (Bullet…, Magatama 177).
- **Chests = data, not scripts.** Field script (`fld/f/f001/f001.bf`, decompiled: procedure `itembox_label`, "takara" = treasure): `FLD_GET_TAKARA_TBL(0…4)` reads the current chest; type 0 chest / 1 gem box ("hoseki", different messages) / 3 Macca (`MAKA_PLUS`); item + quantity → `ITEM_PLUS(item, qty)`; trap 1 = battle (`CALL_BATTLE2`), 2–6 = damage / poison / ache / close; items 96–127 → message `TAKARA_GET2`.
- ✅ **Engine script function table: ELF RAM 0x39E288**, 537 entries (u32 pointer, u32 argument count); **362/362** argument counts identical to Atlus-Script-Tools' `dds` library. `FLD_GET_TAKARA_TBL` (0x114) = code **0x14ED20**.
- ✅ **Chest table**: the code reads `0x34C8F0 + 16 × chest number` (number given by 0x13BE90 from the touched object): **+0x0 u32 type, +0x4 s16 item, +0x6 s16 quantity, +0x8 u32 trap, +0xC u32 battle / Macca**. Zero in the ELF (buffer); filled at boot, **identical in every savestate** (different places) → global table of **256 chests**, copied from **`fld/f/bin/FLDALL.TBL` at 0xDAD8** (4096 identical bytes).
  Contents: type 0 = 116 (71 healing, 28 Noise, 17 battle); type 1 = 74 (46 Cells, 8 ammo, 2 battle, 12 empty, **6 key items**: Tyrant Skull, L/R Statue Key, Yellow Key, Red Key, Golden Orb); type 3 = 66 Macca (often 300: unused places? ❓). 9 "battle" traps → encounters **790–799** (special range 768+).
- `FLDALL.TBL` (79,184 bytes) = several concatenated tables, copied into different areas (place names at the start, 24 bytes per name: Muladhara, Svadhisthana, Karma Temple…; chests at 0xDAD8). No .TBL container.
- Shops (`facility/msg/shop/mes_data.bmd`): the vendor's stock grows by tiers ("Cell bonus earned. New items added to the Vendor's inventory", `msg_privilege01…`) when Cells are sold to the Karma Temple.
- ✅ **Item table: SKILL.TBL block 5, 192 entries of 8 bytes** (id order): +0x00 u8 **usage** (0 Cells / Light Ball, 1 ammo / Noise / sprays, 2 battle, 3 healing, 4 keys), +0x01 u8 ❓ (4; keys 0x0B; 0 for a few battle items), +0x02 u16 **skill triggered** (Molotov 4 = Maragi, Ice Blast 13 = Mabufu, Ration 272), +0x04 u32 **value**. Displayed buying price = value × 2 for the 15 items noted by the tester (Ration 50 → 100, Revival Bead 250 → 500, Charge Shot 750 → 1500…). RAM 0x00F72500 (heap), global pointer at **0x3BAA68** (`lw -0x6288($gp)`, 17 reads in the code).
- ✅ **Shop prices** (code 0x244C00 and 0x244D10): `value × percentage / 100 × float coefficient` (float table at 0x36A234 via 0x2447D8 ❓ moon / Karma Temple?).
- ✅ **Shops: ELF RAM 0x368CF0** (file 0x269CF0), **9 shops of 386 bytes** = u16 default percentage (200) + 64 entries of 6 bytes (u16 item, u16 tab: 0 "Buy item" / 2 "Buy ammo", u16 own percentage, 0 = default). **Shop 2 = list seen by the tester** (Ration, Revival Bead, Dis-Poison, Dis-Ache, Dis-Mute, Dis-Stun, Dis-Curse, Panacea, Molotov, Ice Blast, Thunder Rod, Sonic Stone, Land Mine; ammo Shot Shell, Charge Shot), in order. Shops 1–8 = stock growing along the story; shop 0 = Ration + every ammo (debug?).
- ✅ **Karma Temple bonuses: ELF RAM 0x369A88** (file 0x26AA88), **5 tiers of 260 bytes** = header (u16 **0x0970 + tier** ❓ unlock flag, u16 percentage 200) + 32 entries of 8 bytes (u16 item, u8 marker 0 / 2 ammo / 3 ❓, u8 percentage, u8 **1 = new at this tier**, 3 ❓). Cumulative tiers: Muscle Drink, Spyglass → … → Revival Orb, Megido Fire, Dead End. After tier 4: another table (values 1000) ❓, untouched. Code: 0x244D10 (entry index × 8 + tier × 0x104).

**Chest shuffle (v5, `randomizer/chests.py`, section `[chests]`)**: `mode = "shuffle"` (default) redistributes the contents within 3 groups — 116 item chests, 54 item gem boxes, 66 Macca chests (amounts); `"random"`: item drawn among those the group contains in the game (quantity kept); `"original"`. Never touched: type and trap of each chest, key items 128–150, items 172–178 (Reserve, Dead End, Magatama), trapped chests.

**Shop shuffle (v6, `randomizer/shops.py`, section `[shops]`)** — the tester's choice: both modes as options, Ration guaranteed by default. Item → item mapping (bijection per tab over the buyable items: usage 2 / 3 of SKILL block 5, no key items, Noise or Cells; ammo 161–171, 173, 174) applied to shops 1–8 **and to the 5 Karma Temple tiers** (v6.1): the progression (growing stock) is kept, no duplicate. `tiered`: noisy sort on the value rank (±4); `random`: free permutation; `original`. Price = value of the new item × 200 %. Shop 0 (debug?) untouched. Magic Reed, Estoma Spray (usage 1) and Dead End stay (outside the shuffle).

---

## 6. Existing tools and projects

| Project | Game | What we take from it | License |
|---|---|---|---|
| [nmarkro/Nocturne-Randomizer](https://github.com/nmarkro/Nocturne-Randomizer) | Nocturne | Python architecture (read ISO → modify → write), tiered shuffle, progression logic. **Its data (demons 0x3C bytes, skills, battles 0x26 bytes) is read from the ELF `SLUS_209.11` at fixed addresses**, not from the IMG. Also uses a HostFS patch | not specified |
| [tge-was-taken/AtlusFileSystemLibrary](https://github.com/tge-was-taken/AtlusFileSystemLibrary) | Nocturne, DDS1/2, Raidou | DDT/IMG format (reading **and** rewriting), `DDS3Pack` tool | GPL-2.0 |
| [tge-was-taken/Atlus-Script-Tools](https://github.com/tge-was-taken/Atlus-Script-Tools) | explicitly supports DDS1 and DDS2 | Decompiles/recompiles `.bf` (flowscript) and `.bmd` (message) scripts. Used for the AI scripts and to understand chests | GPL-3.0 |
| [Amicitia wiki — DDS](https://amicitia.miraheze.org/wiki/Digital_Devil_Saga:_Avatar_Tuner) | DDS | List of extensions (PB, TMX, SMG, ADB, BF, BMD, PM1/2…), few binary details | — |
| [chenetulipe/DDS1-FR-PS2](https://github.com/chenetulipe/DDS1-FR-PS2) | DDS1 | "Very provisional" French translation, DDT/IMG parser in Python. Not mature | CC BY-NC-SA 4.0 (do not copy code) |
| FearLess CT "SMT DDS 1 & 2 (PCSX2)" (fearlessrevolution.com, t=3088) | DDS1/2 | RAM addresses of cheats: possible shortcut for step 1 | — |
| romhacking.net #7937 (Less Grinding), #7935 (Terminology) | DDS1 | Necessarily modify EXP/skill tables. Page blocked by Cloudflare for my tools: **to be read in a browser** | — |

No public DDS1/DDS2 randomizer found (Sept. 2026).

**Key question for step 1** (answered: UNIT.TBL): in Nocturne the stats are in the ELF. In DDS, `battle/*.TBL` exists in the IMG. Does the game read its enemy stats from UNIT.TBL, from the ELF, or both?

---

## 7. Log

- **2026-09-27** — Windows version without Python: `generate.py` (generation shared by the command line and the window), `gui.py` (tkinter window; `python -m randomizer` without arguments), `packaging/launcher.py` + GitHub Actions workflow building `DDS1-Randomizer.exe` on each release (PyInstaller 6.22.3). Checked: same ISO byte for byte after the refactor and with the PyInstaller binary (Linux build, seed 14). 1011 tests.
- **2026-09-28** — Windows version checked: the window (Tk, Linux) matches the Options in both directions and a generation through it gives the same ISO byte for byte (seed 14); `DDS1-Randomizer.exe` built with the CI command under Wine (dedicated prefix `~/.wine-dds1`, Windows Python 3.13.15, installer's GPG signature checked: Steve Dower, key FC624643487034E5) gives the same ISO byte for byte. ✅ Window of the .exe tried by the tester in Bottles: ISO created (seed 1198579634, mantras / chests / shops random), identical byte for byte to the command line with the same options; spoiler identical apart from Windows line endings (CRLF, written by Python on Windows). The window displays correctly and "Open spoiler log" works in Bottles (the tester).
- **2026-09-27** — Spoiler: AI-only skill changes (lists, script) shown after the record changes ("AI: …"), for enemies and bosses; * marks special versions. 1009 tests.
- **2026-09-27** — v10 (in 1.3.0): special versions of spells (element 256 + x, boosted copies) attached to the family of their normal version and adapted. 1008 tests. ✅ Loaded in game (RAM, seed 14 Queen Mab).
- **2026-09-27** — v9 (1.3.0): instant-death spells adapted (families ranked by chance +0x25); effect mask read on 16 bits (+0x26), which fixes 3 wrongly merged families (Death Blow, Chi Blast, Vaikunta). 1007 tests. ✅ Validated in game (Beelzebub casts Mamudo).
- **2026-09-27** — v8 (1.2.0): option `[bosses] unique_skills = "keep" | "power"` (`--boss-unique-skills`): power of the 14 unique boss skills on a continuous level curve (k measured on the ordinary species); writes SKILL.TBL (power only). 1005 tests. ✅ Validated in game (seed 35, Seraph Lore 64 % applied exactly).
- **2026-09-27** — v7 (1.1.0): option `[bosses] hp = "curve" | "place"` (`--boss-hp`); spoiler: Atlus line breaks (`_`) of affinity texts shown as " · ". Showcase seed 155 found by scanning 5,000 seeds in memory (Garuda and Nidhoggr in the first zone, Beelzebub as the first boss). 983 tests.
- **2026-09-26** — Project translated to English (options, command line, messages, spoiler, code, tests, scripts, docs, NOTES). Option names in English (`[enemies]`, `[enemy_skills]`, `[affinities]`, `[bosses]`, `[mantras]`, `[chests]`, `[shops]`; modes `shuffle` / `random` / `original`, `adapt`, `tiered`); `presets/default.toml`; random stream names kept, so a seed gives the same ISO as before (checked byte for byte on seed 2523). `eval_balance.py` and `test_boss.py` fixed.
- **2026-09-26** — Public export: `scripts/export_public.py` (new repository without history, without CLAUDE.md nor raw notes, first name replaced, leak check); export checked (install from scratch, same ISO byte for byte for a given seed, tests skipped without an ISO).
- **2026-09-26** — Release preparation (1.0.0): check of the original ISO (MD5 of the 7 files used, option `--verify-iso` = whole ISO against Redump), clear error messages, disk space check, `--version`, GPL-3.0-or-later license, README for players (Linux + Windows), `docs/DEVELOPMENT.md`, dependencies reduced to pycdlib.
- **2026-09-26** — v6.1: Karma Temple bonuses included in the shop shuffle. 961 tests.
- **2026-09-26** — Shop test 1: ✅ v6 validated in game (list and prices = spoiler, purchase OK). The whole original plan is covered.
- **2026-09-26** — v6: shop shuffle (tiered / random, Ration guaranteed); 900 tests; shop test 1 ready.
- **2026-09-26** — Chests validated in game; item table (SKILL block 5, price = value × 2), shops (ELF 0x368CF0, 9 × 386 bytes) and Karma Temple bonuses (0x369A88) found by reading the code.
- **2026-09-26** — v5: chest shuffle (shuffle / random / original); chest test 1 ready.
- **2026-09-26** — Chests: table of 256 chests found (FLDALL.TBL 0xDAD8), through the engine's script function table (0x39E288); item names (MSG block 4).
- **2026-09-25** — Mantra test 4: ✅ shuffled mantras bought, mastered in 1 battle, skills learned (Dia, Raving Slash); +0x04 = AP ✅.
- **2026-09-25** — Mantra test 3: skills are given on mastery; Macca at 0x0114133C; PCSX2 CRC computable (XOR of the ELF).
- **2026-09-25** — v4: mantra shuffle (tiered / random, Dia / Media guarantees as options). 686 tests.
- **2026-09-25** — Mantras: +0x00 difficulty ✅, +0x02 required level 🟡 and +0x04 AP 🟡 (reading the MIPS code with capstone); price in another table ❓.
- **2026-09-25** — Mantra table found in the executable (0x2917B4, 98 × 28 bytes, names in MSG block 1); `GameISO` also writes the ELF; mantra test 1 ready. Boss shuffle enabled by default.
- **2026-09-25** — Boss test 3: Metatron level 15 matches the spoiler, difficulty judged good; cheat validated; Atlus' max HP/MP formulas found (calc_MAXMG / calc_MAXSP).
- **2026-09-25** — Permanent party records found in RAM (0x01141D60); PCSX2 cheat putting the party at level 15 for boss test 3; "two bosses" bug (slot 1) fixed.
- **2026-09-25** — v3: shuffle of the 24 single-unit bosses (option disabled by default until validated). 534 tests.
- **2026-09-25** — Boss test 2: Usas level 8 + Unicorns level 8 beaten, story OK after the victory. Nature 8 = % of HP (game texts), Hama/Mahama families adapted; unique boss spells kept (the tester's choice).
- **2026-09-25** — v2.6: AI scripts taken into account (cast skills and checks adapted like the record, Jinn detached from `AI_Zin`, summons of Hanuman and Girimehkala replaced by species at their level). AICALC +0x02 = procedure number ✅. `test_boss.py`: Unicorn 301 rescaled with Usas. 450 tests.
- **2026-09-24** (night) — Atlus-Script-Tools installed (dotnet-runtime-8.0, official repositories); AI and formula scripts decompiled to readable code (`AI_Ushasu`: Unicorn1 reinforcements through Support at 40 %).
- **2026-09-24** (night) — Boss test 1: swap Hayagriva → Usas OK, but reinforcements (Unicorn 301) too strong. AICALC blocks 2 and 3 = Flowscripts (named boss AI; battle formulas); summon = PUSHIS unit, PUSHIS 203, COMM 226.
- **2026-09-24** (night) — Bosses: catalogue of the 84 scripted battles; ENCOUNT +0x04 = next encounter (waves/reinforcements), +0x26 = boss battle number 901–920. Project CLAUDE.md added.
- **2026-09-24** (night) — v2.5 validated in game: no more turns wasted on "Insufficient MP".
- **2026-09-24** (night) — v2.5: cost type kept in the draw, MP budget (8 × the most expensive spell, rule measured on the game). 370 tests.
- **2026-09-24** (night) — v2.4: random enemy skills. Drawn among the **166 skills already used by the AI of ordinary enemies** (enemy-side animation guaranteed), same type (damage / death / ailment / heal / support × target one / all; 112 drawable), usage level (median level of the enemies using it) within ±10 of the enemy's in-game level (window doubled if empty), no duplicate; same replacement in the record and the AI; separate random stream ("seed-competences"). Seed 2509: 744 AI actions replaced. 330 tests.
- **2026-09-24** — v2.3 validated in game: Analyze = spoiler (Preta, Onmoraki, Cockatrice), affinities effective in battle.
- **2026-09-24** — v2.3: affinity option (shuffle by default / random / original, physical protection disabled by the tester's choice). Shuffle within 3 groups (damage 0–6, instant death 8–9, ailments 10–14); almighty and column 15 untouched; draw independent from the enemies' (seed "seed-affinites"). Analyze text regenerated in Atlus' format (identical to Atlus for 68/99 units; the differences = Atlus' omissions and typos), split between two elements beyond 62 characters. 309 tests.
- **2026-09-24** — Affinities validated: UNIT block 4 (column = element, weak/null/repel/drain flags) confirmed in game (modified Preta) and by the Analyze texts (MSG block 2, 82/99 consistent). Analyze shows a text stored separately.
- **2026-09-24** — v2.2 validated in game: Kikuri-Hime casts Maragi, the MP rescaling limits its expensive spells (Magic Repel 30 MP).
- **2026-09-24** — v2.2: spells also adapted in the AI (AICALC: 7 lists × 5 entries (probability, action)); seed 2509: 119 AI actions adapted, Kikuri-Hime casts Maragi / Mabufu. 186 tests.
- **2026-09-24** — v2.1: enemy skill mode "adapt" (default); seed 2509 regenerated identically except for the skills (Kikuri-Hime: Maragidyne → Maragi, Mabufudyne → Mabufu). 166 tests.
- **2026-09-24** — SKILL.TBL: block 1 = 512 records × 0x38 (cost, target, accuracy, hits, nature, power, effect), block 0 = element/category; costs checked on 4 skills on screen.
- **2026-09-24** — In-game test of v2: rescaling and rewards validated; high-level skills (Maragidyne) stay deadly at level 6 → SKILL.TBL first.
- **2026-09-24** — Randomizer v2: options (TOML preset + command line), in-place rescaling of 67/90 species. Measured model (90 species): value ≈ c × level^k, log R² 0.59–0.96; k: HP 0.93, MP 1.07, St 0.93, Vi 0.75, Ma 0.87, Ag 0.70, Lu 0.63, Karma 1.56, Macca 2.04 (the linear model explains less: R² 0.23–0.94). Measured on 200 seeds: 54 % new enemies in the first dungeon (v1: 9 %), mean level 3.7 (original 3.4), max 10. 145 tests. ⚠️ Skills not rescaled (e.g. Virtue level 5 keeps Mahama/Hamaon).
- **2026-09-24** — Unit copy: works (6 table rows + name + DDT alias of the model and sobed) except the sound `me%03x.at3` (DDT entry missing → wait). 67/90 species can be rescaled in place without a copy.
- **2026-09-24** — Rewards: UNIT +0x2C = Karma, +0x28 = base Macca (×1.5 in game), checked on 2 battles; stat order St, Vi, Ma, Ag, Lu.
- **2026-09-24** — Balance: measured over 200 seeds (`scripts/eval_balance.py`). Widening the spread brings variety at the start of the game but raises the difficulty (±10: 28 % new enemies, mean level 3.4 → 6.2). Solution chosen: **rescaling**, because 50/90 species also appear outside random battles. "No identity" option enabled by default.
- **2026-09-24** — Randomizer v1 validated in game (seed 2409): 25 matching battles, no crash.
- **2026-09-24** — Randomizer v1 (`python -m randomizer`): "noisy sort" shuffle (±5 levels), 398 random battles, 90 species, justified exclusions; 83 tests OK. Known flaw: at the start of the game, many species land on themselves (tight levels) → tuned in step 4.
- **2026-09-24** — ENCOUNT.TBL block 2 = 128 zones × 4 lists of (encounter, weight ‰); validated in game (26 battles); zone = place + story progress.
- **2026-09-24** — MSG.TBL: names in ASCII (units, skills, items, characters, races), validated by the menus on screen.
- **2026-09-23** — Prototype v0 tested in game: test 1 (tiers of 5) and test 2 (total shuffle) without crash; enemies loaded per battle.
- **2026-09-23** — Step 2 started: ENCOUNT.TBL block 0 = 1024 × 0x28, enemy slots +0x06..+0x12, encounter 257 → 3 × unit 99 checked in game.
- **2026-09-23** — Step 1 done: tables found in RAM, battle unit array (0x00EBE200, 0x380), UNIT.TBL block 3 = 384 × 0x4C, HP patch 31 → 999 checked in game.
- **2026-09-23** — Step 0: tools installed, ISO checked against Redump, extraction, inventory, DDT/IMG format validated, TBL container validated, search for existing projects.

---

## 8. In-game tests

### Test 1 — seed 42, tiers of 5 species (2026-09-23), the tester's notes
Cold boot on `dds1_test.iso`, loading a memory card save just before the tutorial.

**Analysis (Claude)**:
- ✅ 10 random battles + 2 scripted battles without crash, fair difficulty.
- ⚠️ The test proves little about "any enemy anywhere". With tiers of 5, the first tier (units 99, 56, 74, 102, 88, levels 1–5) was shuffled **with itself**: these are the first dungeon's enemies, moved around (99 → 102, 88 → 99, 102 → 88). The change is therefore barely visible.
- ✅ Tutorial: **2** green monsters (the tester's correction, "3" was a typo). Consistent with encounter 257 left intact (`[284, 284]`).
- Lesson: an in-game test must include a **savestate** for each notable battle, to link what is seen to the ids.

### Test 2 — seed 7, `--palier 999` (total shuffle): stress test
Goal: check that enemies from other zones (levels 12 to 49) **load** in the first dungeon. Unwinnable battles are not the point.
Examples: 99 (level 1) → 24 (level 12); 88 (level 5) → 41 (level 38); 90 (level 10) → 17 (level 35). Encounter 257 intact.

**Analysis (Claude)**, savestates read in RAM and compared with `work/spoiler_v0_7_p999.txt`:

| Savestate | Enemies in RAM | Replaces | On screen |
|---|---|---|---|
| 1 | 3 × unit 24 (level 12, 96 HP) | 99 (level 1) | 3 red birds (the screenshot shows 3, not 2) |
| 2 | unit 41 (level 38, 268 HP) | 88 (level 5) | starfish with an eye |
| 3 | unit 89 (level 13, 100 HP) | 74 (level 3) | pink creature with a golden mask |

- ✅ **Stress test passed**: enemies of level 12 to 38, from other zones, load, show, act and die normally in the first dungeon (6 battles, no crash). Models are loaded **per battle**, not per zone: no zone constraint for the randomizer.
- ✅ The stats in RAM (level, HP) are those of the replacement species' UNIT.TBL record: rewards and difficulty follow the species.
- ⚠️ Not tested yet: groups of 5 big enemies, the 59 other species, encounters 512–767.
- Lesson confirmed: the savestate is the reference trace (3 birds in RAM, 2 written from memory).

### Name check test (MSG.TBL block 3)

**Analysis (Claude)**: see section 5 (in-game check of 2026-09-24): the names shown when targeting match MSG.TBL block 3.

### Zone test (ENCOUNT.TBL block 2)

**Analysis (Claude)**: see section 4, "ENCOUNT.TBL block 2" (in-game test of 2026-09-24).

### Randomizer v1 test — seed 2409

**Analysis (Claude)**: ✅ **randomizer v1 validated in game** (seed 2409, spread ±5).
- The 25 noted battles **all** match an encounter of the randomized file, in zones consistent with the map from the zone test (start = zones 1–2, save room = 4, after the NPC flees = 5–8). Checked by script: observed composition = composition of an encounter of the zone lists.
- Replacements matching the spoiler: Onmoraki → Preta, Preta → Alp, Alp → Slime, Slime → Onmoraki, Cockatrice → Apis; Mou-Ryo and Empusa drew themselves.
- Tutorial, scripted battles (Cockatrice, the NPCs' 2 Empusa) and boss unchanged. Boss savestate: Hayagriva (id 257).
- No crash.
- ⚠️ Confirmed flaw: the first dungeon keeps the same 5 species, rearranged (+ Apis). For the player, the change is barely visible → tuned in step 4.

### Randomizer v2 test — seed 2509

**Analysis (Claude)**: ✅ **v2 validated in game** (seed 2509): 24 battles, no technical problem, normal difficulty except Kikuri-Hime.
- ✅ Rewards = those of the replaced species: 1 Cockatrice (replaces Alp) → 7 Karma; 1 Virtue (replaces Mou-Ryo) → 11; 2 Nozuchi (replace Slime) → 18; Alp at level 8 (replaces Cockatrice) → 22.
- 🟡 **Reward multiplier**: Macca = base × 1.2 / 1.5 / 1.8 depending on the battle; when ×1.8, Karma × 1.5 (battles 9, 17, 20: 21, 33, 27 Karma). Applied by the game on top of the record. Unknown cause (moon phase? battle speed?). No effect on the randomizer.
- ⚠️ **Skills not rescaled = real problem**: Virtue level 5 cast Mahama and Hamaon (no serious damage); **Kikuri-Hime level 6 killed the party with 2 Maragidyne**, worsened by Serph's weakness to fire (hitting a weakness gives an extra turn). → Next priority: decode SKILL.TBL and replace skills with skills of a rank matching the level.

### Randomizer v2.1 test — skills adapted in the record only

**Analysis (Claude)**: ❌ adapting the **record** is not enough. The tested ISO did contain Maragi / Mabufu in Kikuri-Hime's record (UNIT +0x18), but its **AI** row (AICALC block 0, row 92) still contained Maragidyne (6) and Mabufudyne (15). → The record list = what Analyze shows; **the spells actually cast come from the AI** (the Nocturne randomizer also rewrote the AI). Fixed: the same replacement is applied to the AI actions (see "AICALC").

### Randomizer v2.2 test — skills adapted in the record and the AI

**Analysis (Claude)**: ✅ **spell adaptation validated in game** (record + AI). Kikuri-Hime casts Maragi (and Magic Repel), never a "-dyne" spell anymore; battle won.
- ✅ the tester's hypothesis about MP confirmed: Magic Repel costs **30 MP**; Kikuri-Hime goes from 700 MP (level 49) to **75 MP** (level 6) → 2 Magic Repel + 1 Maragi, then not enough MP.
- Unplanned balancing effect: rescaling MP limits the expensive spells the adaptation rule does not touch (support, reflection). ⚠️ To watch: a powerful and cheap support spell would slip through.

### Affinity test (Preta) and randomizer v2.3 test — shuffled affinities

**Analysis (Claude)**: ✅ **randomized affinities validated in game** (v2.3, seed 2509, shuffle mode). Analyze screens identical to the spoiler, word for word: Preta "Weak: gun/fire"; Onmoraki "Strong: fire / Weak: force"; rescaled Cockatrice "Strong: gun / Weak: phys/fire", LV 3, 48 HP, 14 MP (= spoiler). In battle, weaknesses and resistances work (the tester's notes). ✅ The `_` separator of Atlus' texts is shown as a line break.

### Randomizer v2.4 test — random enemy skills

**Analysis (Claude)**: ✅ no freeze (filter "skills already used by an enemy" validated); ✅ Analyze and battle show the spoiler's skills. ⚠️ Enemies waste their turns on "Insufficient MP": **Atlus' AI does not check MP** (it draws an action from its probabilities); in the original game it does not show because MP pools are large. Two causes on our side: MP reduced by the rescaling, and HP-cost techniques replaced by MP spells (Cockatrice: Body Rush → Bufu with 14 MP).
Fixes (v2.5): (1) the draw keeps the **cost type** (HP ↔ HP, MP ↔ MP); (2) **MP budget**: every rewritten record gets at least **8 × the cost of its most expensive spell** (measured rule: 90 % of the original ordinary enemies have ≥ 8 ×, median 19 ×; the tightest: Blob 0.8 ×, Pixie 0.8 ×). Seed 2509: Kikuri-Hime 75 → 240 MP, Virtue 37 → 120, Cockatrice stays physical (Needle Rush, Mind Scream).

### Randomizer v2.5 test — cost type and MP budget

**Analysis (Claude)**: ✅ **v2.5 validated in game**: the Cockatrice uses Needle Rush (HP-cost technique, cost type kept); Kikuri-Hime chains Mazan and Magic Repel without "Insufficient MP" (240 MP).

### Boss test 1 — Hayagriva → Usas (level 8)

**Analysis (Claude)**: ✅ the boss swap works (Usas' model, name and skills; Whirlwind at the level of a first boss). ⚠️ **Reinforcements**: Usas summons **Unicorn id 301 (level 20)** — a version reserved to reinforcements (there is also Unicorn 66, level 24) — at their original level → impossible battle. Victory not reached: the story after the victory remains to be tested.
- The summon skills (Reinforcements 195, Support 203, Backup 204, Summon 205) have **identical** records, with no unit number.
- ✅ **AICALC block 2 = `FLW0` Flowscript file** (Atlus `.bf` format) with **named procedures**: `ai_0`, `ai_test_*`, `AI_Ushasu` (Usas), `AI_Kamasosso_No1` (Camazotz), `AI_Apisu` (Apis), `AllEscape_MeriBeru`… = boss behaviour scripts. 4-byte instructions (u16 opcode, u16 argument), Flowscript instruction set: 0x1D PUSHIS, 0x08 COMM (engine function), 0x1C IF, 0x0D GOTO, 0x07 PROC, 0x09 END…
- Summon: `PUSHIS <unit> ; PUSHIS <203 Support> ; COMM 226` (Usas: unit 301). **22 summons** of this form in the whole script (all COMM 226) — 23 in fact, see section 5: Baphomet ×3, Bicorn ×2, Nidhoggr ×2, Isis ×2, Unicorn 301, Shiisaa, Sati, Purski, High Pixie, Pixie/Arahabaki/Titania/Parvati/Cu Chulainn/Girimehkala (70)…
- **AICALC block 3 = 2nd Flowscript**: `calc_MAGIC_DAMAGE`, `calc_BUTURI_DAMAGE`, `calc_CRITICAL_RATIO`… = **battle formulas** ("butsuri" = physical). AICALC block 1 = table of floats (4.0…) ❓.
- ✅ **Decompiled** with Atlus-Script-Tools (`dds` library, .NET 8 runtime): `work/bf/AICALC_ai.flow` (324 KB), `AICALC_calc.flow` (11 KB). Excerpt of `AI_Ushasu`: Hamaon while its HP ≥ 75 %; then a 3-turn rotation (bits 3041–3043), **`AI_ACT_SKILL_PARAM(BattleSkill.Support, BattleUnit.Unicorn1)` at 40 % on turns 1–2** (= the reinforcements seen in game), Seraph Lore, Whirlwind. `COMM 226` = `AI_ACT_SKILL_PARAM`.
- ⚠️ **Scripts cast skills directly** (`AI_ACT_SKILL(BattleSkill.Hamaon)`…), outside the action lists of AICALC block 0: spell adaptation must also handle the scripts (bosses and every scripted unit) → done in v2.6.
- Next step (done in v2.6): for each moved boss, rescale the summoned units reserved to that boss (e.g. Unicorn 301), or replace the summons of ordinary species (2 bytes, same size) with species of the right level.

### Boss test 2 — Hayagriva → Usas, Unicorn 301 reinforcements rescaled (level 8)

**Analysis (Claude)**: ✅ **boss swap validated until after the victory**: slot 3 = Svadhisthana, the story continues (the unmodified boss battle number +0x26 = 901 is enough for the story to go on).
- ✅ RAM slot 1: Usas id 261 **level 8, 352/854 HP, 1130 MP**; Unicorn id 301 **level 8, 171/171 HP, 114 MP** (= spoiler). Slot 2: two Unicorns (#8 and #9), level 8. The rescaled reserved reinforcements work (same id: original model and sounds).
- Why it is still hard: **Seraph Lore** (428, reserved to Usas). Game texts (MSG.TBL block 11, messages `skill_<hex id>`, the text **follows** the name): Hama "Reduce HP by half", Hamaon "Reduce HP greatly", Seraph Lore "Greatly reduces HP ~All". → 🟡 **nature 8 (SKILL +0x16) = removes a percentage of the current HP, power (+0x18) = that percentage** (Hama 50, Hamaon 66, Seraph Lore 80, target all, accuracy 99, cost 0). A percentage does not depend on the level: rescaling cannot change it. It does not kill on its own, but the script chains **Whirlwind on the next turn** (bit 3044): that combo finishes the party.
- The tester's decision: **the bosses' unique skills stay as they are** (80 %); to be reassessed on a real playthrough if a boss becomes impossible.
- Fixed: Hama/Hamaon and Mahama/Mahamaon form "percentage" families (nature 8), now adapted like damage spells (the old comment "same power" was wrong). Usas at level 8: Hamaon → Hama in the record, the lists and the script. Mudo & co (nature 0) not concerned.

### Boss test 3 — full v3, seed 2523: Metatron (level 80 → 15) in Camazotz 1's place

Setup (without travelling): `scripts/test_boss3.py` modifies `work/dds1_test.iso` (seed 2523, bosses shuffled): random encounter 1 = Metatron alone (level 15, 3634 HP, 5036 MP, stats 15/25/21/16/17), 78 zone lists redirected to it; cheat `SLUS-20974_D7273511.pnach` (in `~/.config/PCSX2/cheats/`): party at an **approximate** level 15 (+3 points/level distributed like the current build, +4 max HP/MP per level; HP/MP continuously restored outside battle) — Serph HP 86 MP 80 St 36, Heat HP 106 MP 88, Argilla HP 94 MP 104 Ma 16.
- ❌→✅ Bug found while preparing this test: **the boss is not always in slot 0** (Camazotz 259/262, Usas 261, Isis 316, King Frost 320 are in slot 1: `[0, 258, 0…]`). v3 put the new boss in slot 0 and left the old one in slot 1 → two bosses. Fixed: the new boss takes the exact slot of the old one (test updated).

**Analysis (Claude)**: ✅ **v3 validated on the worst case** (a level-80 boss brought down to level 15).
- RAM slot 1: Metatron id 265 **level 15, 3533/3634 HP, 5036 MP, stats 15/25/21/16/17** (= spoiler); model and name "Aerial Metatron" correct (screenshot). Spells: Mahama, Maragi (adapted), Revelation (unique) "consistent though high damage".
- ✅ Cheat: party records at level 15 with the intended stats (Serph 36/7/5/7/5…) → format of the party records in RAM validated. In battle, max HP/MP higher than the cheat's (Serph 98 instead of 86): recomputed by the game, formula above (section "Party records in RAM"). My "+4 per level" estimate forgot the +4 per point of Vi / Ma.
- Defeat caused by the test setup (no Media: mantras not learned); the tester's opinion: **"hard but totally doable", the intended difficulty for a randomized SMT**.
- Not tested here: the arena and music of the real boss battle (random battle), the story continuing at this place (same mechanism as boss test 2 ✅).

### Mantra notes (values seen in game, used to find the table)

**Analysis (Claude)**: these skills, side by side in the executable, led to the mantra table (section "Mantras").

### Mantra test 1 — Ice Demon: Media + Mabufu, base price 3000

**Analysis (Claude)**: ✅ **mantra skills can be modified**: Media + Mabufu shown in Ice Demon's "Mantra Status" (savestate screenshot). ❌ **+0x04 is not the price**: set to 3000, the displayed price stays 2500 → 🟡 AP needed to master it (the AP bar shows no number). The grid shows "Difficulty: ★" (Devourer, +0x00 = 1) and "Price".
- ⚠️ Savestate renamed `SLUS-20974 (D5243A8F)`: PCSX2 computes the CRC **on the executable**, modified here → for PCSX2 it is another game (the `D7273511.pnach` cheat no longer applies with a modified ELF).

### Mantra test 2 — Ice Demon +0x02: 5 → 15; Demon Beast +0x00: 2 → 5

Expected: Ice Demon shows **4000** if the price depends on +0x02 (Demon Beast, +0x02 = 15, costs 4000); Demon Beast shows **5 stars** if +0x00 = difficulty, and keeps its price (4000). Ice Demon keeps Media + Mabufu, +0x04 back to 1500.

**Analysis (Claude)**: ✅ +0x00 = difficulty (5 stars). Ice Demon disappeared: +0x02 is not the price (it is the required level, see "Mantras"). Prices noted: Shura, Fire Spirit, Bolt Spirit 1000 (+0x04 = 600), Ice Demon 2500 (1500), Demon Beast 4000 (2400) → always +0x04 × 5/3, but test 1 rules +0x04 out → ❓ **the price comes from another table** (probably the grid's: positions, links, prices), to be looked for later; not blocking for the randomizer.

### Mantra test 3 — seed 2523, shuffled mantras, Devourer at 1 AP

ISO: `python -m randomizer iso/dds1_us.iso work/dds1_test.iso --seed 2523` then `python scripts/test_mantra.py work/dds1_test.iso` (Devourer +0x04: 600 → 1). Devourer (equipped by Serph) now gives **Mad Rush + Void Earth**. Expected: Devourer mastered after 1 battle (validates +0x04 = AP) and Serph learns Mad Rush and Void Earth. Grid (seed 2523): Ice Demon = Devour + Raving Slash, Demon Beast = Avalanche, Death Spray, Feed Frenzy, Fire Spirit = Void Elec + Dia, Fallen Hero = Media, Frost Breath, Earth Repel.

**Analysis (Claude)**: ✅ the grid shows the shuffled skills (Devourer = Mad Rush + Void Earth, Fire Spirit = Void Elec + Dia, Ice Demon = Devour + Raving Slash). ❌ badly designed test: **Devourer was already mastered** in the save. Serph's record in RAM: u16 from **+0x22** = Bufu, Void Ice, Hell Thrust, Devour (= **assigned** skills, see test 4).
- 🟡 **Skills are copied to the character when it masters the mantra**, not read from the table afterwards. A mantra already mastered before the randomizer gives nothing new (irrelevant for a new game).
- ✅ **Macca**: u32 at **0x0114133C** (9 in the 10:24 savestates, 17 in the 11:30 ones; the only address outside the battle area). Battle copy at 0x00EBDC3C.
- ✅ **PCSX2 CRC = XOR of the 32-bit words of the executable**: gives D7273511 (original) and D40A3465 (test 3) → `randomizer.iso.pcsx2_crc`, to name cheats in advance.

### Mantra test 4 — buying and mastering a shuffled mantra (Fire Spirit, Ice Demon at 1 AP, 50,000 Macca cheat)

ISO: seed 2523 + `python scripts/test_mantra.py work/dds1_test.iso work/` (Devourer, Fire Spirit, Ice Demon at 1 AP); cheat `SLUS-20974_D40A33E1.pnach` (Macca locked at 50,000). Expected: Fire Spirit mastered after 1 battle → Serph learns **Void Elec + Dia**; Ice Demon → **Devour** (already known) **+ Raving Slash**.

**Analysis (Claude)**: ✅ **mantra shuffle validated end to end**. Macca cheat OK (50,000 in RAM, enabled through `gamesettings/SLUS-20974_D40A33E1.ini` because the Game Properties menu would not open: `[EmuCore] EnableCheats = true` + `[Cheats] Enable = <name of the .pnach section>`). End of battle: "Fire Spirit MASTER" (Serph and Heat). Serph's Set menu: **Dia** learned (Magic tab, marked "!") and **Raving Slash** (Physical) = the seed 2523 spoiler's skills for Fire Spirit and Ice Demon, not the original ones (Agi, Ice Boost…).
- Correction: the list at +0x22 of the record is the **ASSIGNED** column (unchanged: Bufu, Void Ice, Hell Thrust, Devour); **LEARNED** skills are elsewhere ❓. The explanation of test 3 holds: Devourer was already mastered, mastery (hence learning) only happens once, at the end of a battle.
- ✅ +0x04 = **AP to earn**: at 1 AP, Fire Spirit and Ice Demon are mastered after the first battle.

### Chest test 1 — does the game read the table? (every chest marked)

ISO: `python -m randomizer iso/dds1_us.iso work/dds1_test.iso --seed 2523` then `python scripts/test_chests.py work/dds1_test.iso`: normal chests → **Soma ×9**, gem boxes → **Megido Fire**, Macca → **7777**. PCSX2 CRC: D40A363C. Expected: any chest not opened yet gives one of these contents.

**Analysis (Claude)**: ✅ **chests validated**: 3 normal chests opened → 3 × Soma ×9 (the FLDALL.TBL table is indeed read by the game). Shop noted by the tester (569 Macca) = shop 2 of the ELF table (see "Items, chests, shops"), price = value × 200 %.

### Shop test 1 — seed 2523 (full randomizer)

ISO: `python -m randomizer iso/dds1_us.iso work/dds1_test.iso --seed 2523` (CRC D46F365A). Expected at the vendor (shop 2): Buy item = Ration 100, Molotov 500, Dis-Ache 150, Fire Wall 200, Rancid Gravy 40, Dis-Mute 150, Ice Wall 200, Panacea 150, Thunder Rod 500, Revival Bead 500, Ice Blast 500, Sonic Stone 500, Holy Arrow 2000; Buy ammo = Bullet 1000, Metal Jacket 5000.

**Analysis (Claude)**: ✅ **shops validated in game**: Vendor screenshots = spoiler, order and prices included (Buy item: Ration 100, Molotov 500, Dis-Ache 150, Fire Wall 200, Rancid Gravy 40, Dis-Mute 150, Ice Wall 200, Panacea 150…; Buy ammo: Bullet 1000, Metal Jacket 5000). Fire Wall (absent from the original shop) bought and received. Descriptions ("Restore 50 HP~1 ally") follow the item.

**Karma Temple bonuses shuffled (v6.1)**: the shops' item → item mapping also applies to the 5 tiers (only the item u16s change; markers, percentages and headers intact). Bijection → no new duplicate between shop and bonus (tested). Magic Reed, Estoma Spray (usage 1) and Dead End stay (outside the shuffle, like in the shops). Seed 2523: tier 1 = Muscle Drink, Revival Gem; tier 5 = … Revival Orb, Graven Image, Dead End. 961 tests. In-game test: only once the tester has unlocked a tier (selling Cells to the Karma Temple).

### Boss HP test — seed 155, Beelzebub in Hayagriva's place, `--boss-hp place`

ISO: `python -m randomizer iso/dds1_us.iso work/dds1_showcase.iso --seed 155 --boss-hp place` (CRC D787359B, same executable as the "curve" run: same PCSX2 game). Cold boot, memory card save before the boss. Expected: Beelzebub (id 272) level 8 with **600 HP** (Hayagriva's) instead of 1,001.

**Analysis (Claude)**: ✅ **boss HP option validated in game**. Analyze screen: "Fiend Beelzebub", every field "?" (Analyze only shows what the player already knows: a boss not defeated yet shows nothing, so Analyze cannot be used for boss checks). Savestate 4 read back (`eeMemory.bin` is compressed with zstd, method 93: `unzip` skips it silently, Python's `zipfile` reads it): battle unit at 0x00EBE980 = **id 272, HP 600/600**, MP 564/564, level 8, stats 10/12/18/6/8 = record 272 of the ISO; the UNIT.TBL record in RAM (0x00F74F80 + 272 × 0x4C + 4) also holds 0x0258 = 600.
- The battle unit was at 0x00EBE980, not at the enemy addresses seen in the first battle (0x00EBEC80…): confirms the pool of slots (section "Battle units").
- Context (the tester's screenshot run, "curve" mode): with the starting party and skills, Beelzebub at 1,001 HP was not beatable without grinding first; this is why the option exists.

### Unique skills test — seed 35, Usas in Hayagriva's place, Seraph Lore 80 % → 64 %

ISO: `python -m randomizer iso/dds1_us.iso work/dds1_test.iso --seed 35 --boss-hp place --boss-unique-skills power` (CRC D6083442). Usas level 8, 600 HP, Unicorn 301 reinforcements level 8; SKILL.TBL power of Seraph Lore (428) = 64 instead of 80. Cold boot, memory card save before the first boss (any seed: a memory card save holds no table).
Expected: in phase 2, Seraph Lore removes **64 %** of each character's current HP (🟡 "percentage of the current HP") instead of 80 %. Savestate just before Usas casts it and just after: HP read back in RAM (battle units +0x26).

**Analysis (Claude)**: ✅ **unique skills option validated in game, and the game reads the power in SKILL.TBL**. Savestates read back (battle units, +0x26 current HP): Serph 38 → 14, Heat 54 → 20, Argilla 58 → 21, i.e. 24, 34 and 37 HP removed = **floor(current HP × 0.64)** for all three (38 × 0.64 = 24.3, 54 × 0.64 = 34.6, 58 × 0.64 = 37.1); the original 80 % would have left 8, 11 and 12 HP. Usas (303/600) and the Unicorn (171/171) unchanged between the two savestates: nothing else happened. Seraph Lore's record is in RAM at 0x00F70D20 with power 64 (SKILL.TBL loaded as is, like the other tables).
- ✅ SKILL.TBL +0x18 = power **read by the game** (was 🟡 "consistent progression").
- ✅ Nature 8 = percentage of the **current** HP, rounded down (the max HP would give 50 × 0.64 = 32 for Serph, not 24).
- Party battle units at 0x00EBDF00 / 0x00EBE280 / 0x00EBE600, Usas 0x00EBE980, Unicorn 0x00EBED00 (stride 0x380, +0x08 = 4…8): other addresses than in the first battle, consistent with the pool of slots.

### Instant death test — seed 155, Beelzebub casts Mamudo

ISO: `python -m randomizer iso/dds1_us.iso work/dds1_test.iso --seed 155 --boss-hp place` (same executable as the showcase ISO: CRC D787359B). Beelzebub (272) level 8, 600 HP; in his AI lists and script, Mamudoon (30 %) → **Mamudo (20 %)** (checked on the data by a test). Cold boot, memory card save before the first boss.
Expected: the name shown when he casts it is "Mamudo", never "Mamudoon". Savestate right after (AICALC in RAM: the replaced skill ids).

**Analysis (Claude)**: ✅ **instant-death adaptation validated in game**: the name shown is "Mamudo". Savestate 5 read back: Beelzebub's AI lists (row 272, 0x00FBB4C0 in RAM) are identical in both ISOs, his Mamudoon was in his **script** (`AI_` procedure, instruction 12329: PUSHIS skill + COMM cast); the test ISO's bytes around that instruction (with **Mamudo**, 67) are in RAM at 0x00FE315C, the original's (Mamudoon, 68) nowhere. Screenshot: Serph at 0 HP (Heat 12, Argilla 7), consistent with a successful Mamudo.
- The script block (AICALC block 2) is not in RAM as one piece (only parts of it found): ❓ loaded per procedure or relocated; searching a window around an instruction works.

### Special versions test — seed 14, Queen Mab in Empusa's place (level 6)

ISO: `python -m randomizer iso/dds1_us.iso work/dds1_test.iso --seed 14 --boss-hp place`. Queen Mab (44) replaces Empusa (zones 5 and 8 of the first dungeon, frequent on 2F before the boss), level 6. AI: Maziodyne* 442 / Mazandyne* 446 / Materadyne* 450 → **Mazio 22 / Mazan 31 / Matera 40**; record: Agidyne → Agi, Bufudyne → Bufu, Ziodyne → Zio, Zandyne → Zan, Teradyne → Tera. Cold boot, memory card save before the boss, random battles on 2F.
Expected: Queen Mab only casts level-1 spells (Mazio, Mazan, Matera, Agi, Zio…), never a -dyne. Savestate during the battle.

**Analysis (Claude)**: ✅ **special versions adapted: loaded in game** (cast itself not observed). Savestate 1 read back: Queen Mab's AI row of the test ISO (row 44, with Mazio 22 / Mazan 31 / Matera 40 instead of Maziodyne* / Mazandyne* / Materadyne*) is in RAM at 0x00FA7ED0, the original row nowhere; battle unit level 6, 59/59 HP (= spoiler). Analyze screenshot: Agi, Bufu, Zio, Zan, Tera, Vanity, Magic Repel, Makakaja (record adapted), MP 84/240.
- Why no Mazio: her 7 AI lists (test ISO): list 0 = Makakaja 25 %, Vanity 25 %, Magic Repel* 25 %, Attack 25 %; list 1 = Agi, Bufu, Zio, Tera, Zan; **list 5** = Agi, Mabufu, Matera, Mazio, Mazan; lists 2, 3, 4, 6 = Vanity / Magic Repel* / Makakaja / Attack. The tester only saw Makakaja, Vanity, Magic Repel and Attack = exactly **list 0**: the game picked that list during this battle (list choice ❓ "by the situation", AICALC header). Replacing an id in a list is the mechanism already validated in game (v2.2, Kikuri-Hime casting Maragi / Mabufu); here only the replaced ids are new. Accepted as validated; a cast of Mazio/Mazan/Matera by a rescaled Queen Mab or Oni stays to be seen during a real playthrough.
- Vanity (almighty, all targets, effect mask 0x02B8 = several ailments) is not adapted (no family): at level 6 she keeps it. ❓ To look at if it proves too strong.
