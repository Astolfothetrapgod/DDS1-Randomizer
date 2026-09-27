# Development and research

Guide for anyone who wants to understand, check or extend the randomizer. The source of truth on the
formats (offsets, evidence, in-game tests, rejected hypotheses) is [`NOTES.md`](../NOTES.md).

## Layout

```
randomizer/          randomizer code (python -m randomizer)
  iso.py             reading / writing inside the ISO (ISO9660, DDS3.DDT index, DDS3.IMG archive), checks
  tables.py          battle tables (UNIT, SKILL, ENCOUNT, AICALC, MSG)
  flowscript.py      AI scripts (FLW0 Flowscript)
  enemies.py, scaling.py, skills.py, affinities.py, bosses.py
  mantras.py, chests.py, shops.py
  options.py         options (TOML presets)
presets/default.toml default preset, every option commented
tests/               automated tests (pytest)
scripts/             analysis scripts and in-game test preparation
imhex/patterns/      ImHex pattern of the DDS3.DDT format
docs/                ISO inventories (names, sizes, offsets: no game data)
NOTES.md             research log
```

Local folders ignored by git (never published): `iso/` (link to your dump), `extracted/`, `work/`,
`ghidra/`, `tools/`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The tests read the reference ISO `iso/dds1_us.iso` (symbolic link to your dump). Without it, they are
skipped: no game file is needed to run them, nor included in the repository.

## Preparing an in-game test

Protocol: generate a test ISO, start PCSX2 **cold** (no savestate), load a memory card save, write down the
observations in NOTES.md, then read the savestates back (`.p2s` = zip archive containing `eeMemory.bin`,
the 32 MB RAM, and `Screenshot.png`) to compare with the spoiler log.

Test scripts (they all read the original ISO or modify a copy, never the original):
`scripts/test_boss.py`, `test_boss3.py` (boss + level cheat), `test_mantra.py` (1 AP + Macca cheat),
`test_chests.py` (marked chests), `test_affinity.py`, `test_clone.py`.

Test helpers (NOTES.md, "Party records in RAM"): party records in RAM at `0x01141D60` (0x1A4 bytes per
character), Macca at `0x0114133C`. The name of PCSX2 savestates and cheats depends on the hash of the
executable (`randomizer.iso.pcsx2_crc`); a cheat can also be enabled in
`~/.config/PCSX2/gamesettings/SLUS-20974_<CRC>.ini` (`[EmuCore] EnableCheats = true` and
`[Cheats] Enable = <name of the .pnach section>`).

## Standalone Windows version

- `randomizer/generate.py` does the whole generation; `__main__.py` (command line) and `gui.py` (tkinter window)
  only build an `Options` object and call it. `python -m randomizer` without arguments opens the window.
- `packaging/launcher.py` is the PyInstaller entry point. `.github/workflows/windows.yml` builds
  `DDS1-Randomizer.exe` on GitHub's Windows machines (PyInstaller cannot build a Windows executable from
  Linux) and attaches `DDS1-Randomizer-<version>-windows.zip` (exe, README, LICENSE, presets) to each published
  release; "Run workflow" in the Actions tab builds it without a release (artifact).
- Local check (same PyInstaller, Linux binary): `pip install -r requirements-build.txt`, then
  `pyinstaller --onefile --windowed --name DDS1-Randomizer --paths . packaging/launcher.py`; the binary must
  produce the same ISO byte for byte as `python -m randomizer` for the same seed and options.

## Analysis scripts

```bash
python scripts/inventory.py iso/dds1_us.iso                         # ISO inventory
python scripts/ddt.py check   extracted/DDS3.DDT extracted/DDS3.IMG  # validates the DDT format
python scripts/ddt.py list    extracted/DDS3.DDT > docs/dds3_files.tsv
python scripts/ddt.py extract extracted/DDS3.DDT extracted/DDS3.IMG battle/SKILL.TBL
```

## Decompiling scripts (Flowscript)

```bash
dotnet tools/atlus-script-tools/AtlusScriptCompiler.dll work/bf/AICALC_ai.bf -Decompile -Library dds -Out AICALC_ai.flow
```

`AICALC_ai.bf` / `AICALC_calc.bf` = blocks 2 and 3 of `battle/AICALC.TBL`; field scripts:
`fld/f/fXXX/fXXX.bf`. Short name of the DDS1 library: `dds`.

## Reading the game code

The executable `SLUS_209.74` (MIPS R5900) can be read with Ghidra + ghidra-emotionengine-reloaded, or in
Python with `capstone` (`pip install capstone`). Useful landmark: the engine's script function table is in
RAM at `0x39E288` (pointer + argument count), which lets you go from a script function
(`FLD_GET_TAKARA_TBL`…) to its code, then to the data it reads.

## Tools used

| Tool | Version | Purpose |
|---|---|---|
| PCSX2 | 2.8.2 (AppImage) | in-game tests, savestates |
| ImHex | 1.38.1 | reading formats |
| Ghidra + ghidra-emotionengine-reloaded | 12.1.2 / v2.1.37 | disassembling the executable |
| Atlus-Script-Tools | release of 2026-05-17 (needs .NET 8) | Flowscript decompilation |
| capstone | 5.0.7 | MIPS disassembly in Python |
| 7-Zip | 26.03 | ISO extraction |
| Python | 3.11+ (developed with 3.14) + pycdlib 1.20.0 | randomizer |
