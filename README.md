# DDS1 Randomizer

Randomizer for **Shin Megami Tensei: Digital Devil Saga** (PlayStation 2, North American version NTSC-U,
SLUS-20974).

The program reads **your own copy** of the game (an ISO image you dumped from your disc) and creates a new,
randomized ISO next to it, tested on the PCSX2 emulator (not yet on real hardware). **This project contains
and distributes no game files**: without your ISO, it does nothing.

## What gets randomized

| Part | Default | Other choices |
|---|---|---|
| Enemies of random battles | shuffled, rescaled to the level of the area (HP, MP, stats, rewards) | adjustable level spread, no rescaling, disabled |
| Enemy skills | spells adapted to the new level (record, AI and scripts) | random (same type), original |
| Enemy affinities | shuffled (Analyze text rewritten) | random, original, never immune to physical |
| Bosses | the 24 single-unit bosses change places, rescaled to their new place (reinforcements included) | HP of the replaced boss (easier), disabled |
| Mantras (party skills) | redistributed between mantras of similar level; Dia and Media guaranteed early | fully random, no guarantee, original |
| Chests | contents shuffled between chests of the same type | random, original |
| Shops and Karma Temple bonuses | items replaced by items of similar value, Ration guaranteed | random, original |

Never touched: key items, the story, special event battles. Each run writes a **spoiler log** (text file)
listing every change.

## What you need

- **Your game ISO**: *Shin Megami Tensei: Digital Devil Saga*, NTSC-U, **SLUS-20974, v1.00**, unmodified.
  The program checks the files it uses and refuses any other version, or an already randomized ISO.
  Reference (Redump dump #253): 4,539,547,648 bytes, MD5 `ae4330140ef56f9eb1c689b9bb383401`,
  SHA-1 `f022cc27d2c333db64f1f1a46b312aafc5ce632e`. The `--verify-iso` option checks the whole ISO.
- **Python 3.11 or newer** (tested with Python 3.14).
- **5 GB of free disk space** for the randomized ISO.

## Installation

Download the project from <https://github.com/Astolfothetrapgod/DDS1-Randomizer> (green **Code** button >
**Download ZIP**, then extract it; or `git clone`), then open a terminal in that folder.

**Linux** (bash or zsh; with fish, replace `activate` with `activate.fish`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows** (PowerShell; first install Python from [python.org](https://www.python.org/downloads/)):

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Usage

**Linux:**

```bash
python -m randomizer path/to/DDS_original.iso DDS_randomized.iso --seed 1234
```

**Windows:**

```powershell
.venv\Scripts\python -m randomizer "C:\Games\DDS_original.iso" "C:\Games\DDS_randomized.iso" --seed 1234
```

- The original ISO is **never modified**. The program copies it, then modifies the copy (about 15 s).
- The spoiler log is written next to the new ISO: `DDS_randomized_spoiler_1234.txt`.
- **Same seed + same options = same game**: to play the same randomization as a friend, share the seed and
  the options file. Without `--seed`, a random seed is drawn and written in the spoiler log.

### Options

Every option is listed and commented in [`presets/default.toml`](presets/default.toml). To customize your
game, copy that file, edit it, then pass it to the program:

```bash
python -m randomizer original.iso randomized.iso --preset my_preset.toml
```

Command-line options override the file. `python -m randomizer --help` lists them all:
`--level-spread`, `--allow-identity`, `--no-scaling`, `--no-enemy-shuffle`,
`--enemy-skills adapt|random|original`, `--affinities shuffle|random|original`, `--protect-physical`,
`--no-bosses`, `--boss-hp curve|place`, `--mantras tiered|random|original`, `--no-heal-guarantee`, `--chests shuffle|random|original`,
`--shops tiered|random|original`, `--verify-iso`, `--version`.

## Playing

- **Start a new game**, or load a memory card save. Saves from the original game work. A mantra already
  mastered in a save keeps the skills it already taught.
- **PCSX2**: boot the randomized ISO normally. **Savestates** from the original game are not compatible:
  they contain the old data.
- PCSX2 identifies a game by a hash of its executable, which the randomizer modifies (mantras, shops). Each
  randomized ISO therefore has its own savestates, settings and cheats, separate from the original game's.

## Known limitations

- Moved bosses keep their **unique skills**: a late-game boss placed early stays tough, even rescaled. By
  default their HP also follows the level curve (Beelzebub as the first boss: 1,001 HP instead of 600). For an
  easier game, `[bosses] hp = "place"` (or `--boss-hp place`) gives each boss the HP of the boss it replaces.
- **Mantra prices** are not changed.
- Not much tested in game yet: the Karma Temple bonuses, and a full playthrough from start to finish.
  Feedback is welcome.

## For the curious and for developers

All the research (file formats, evidence, in-game tests, rejected hypotheses) is in
[`NOTES.md`](NOTES.md). Research tools, test scripts and automated tests are described in
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## License and credits

Code under the **GPL-3.0-or-later** license (see [`LICENSE`](LICENSE)).

*Shin Megami Tensei: Digital Devil Saga* © Atlus. Fan project, not affiliated with Atlus or SEGA.

Thanks to these community projects: [Atlus-Script-Tools](https://github.com/tge-was-taken/Atlus-Script-Tools)
(script decompilation), [pycdlib](https://github.com/clalancette/pycdlib) (ISO reading),
[ghidra-emotionengine-reloaded](https://github.com/chaoticgd/ghidra-emotionengine-reloaded), ImHex,
[capstone](https://www.capstone-engine.org/), and the *Nocturne* randomizers for the original ideas.
