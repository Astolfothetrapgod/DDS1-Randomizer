#!/usr/bin/env python3
"""Reading the DDS3.DDT (index) + DDS3.IMG (data) archive.

Format according to AtlusFileSystemLibrary (TGE, DDS3FileSystem.cs), verified by the `check`
command (see NOTES.md):

  DDT entry = 12 bytes, little-endian
    u32 name_offset  offset of the name (ASCII, 0-terminated) in the DDT; 0 = root
    u32 offset       directory: offset of the child entries in the DDT
                     file: sector number (0x800 bytes) in the IMG
    i32 count        < 0: directory of -count children; >= 0: file of count bytes

Usage:
  python scripts/ddt.py list    extracted/DDS3.DDT              > docs/dds3_files.tsv
  python scripts/ddt.py check   extracted/DDS3.DDT extracted/DDS3.IMG
  python scripts/ddt.py extract extracted/DDS3.DDT extracted/DDS3.IMG battle/SKILL.TBL [dest]
"""
import struct
import sys
from pathlib import Path

SECTOR = 0x800


def read_name(ddt: bytes, off: int) -> str:
    if off == 0:
        return ""
    end = ddt.index(b"\0", off)
    return ddt[off:end].decode("ascii")


def walk(ddt: bytes, pos: int = 0, parent: str = ""):
    """Yields tuples (path, is_dir, offset, count, entry_position_in_ddt)."""
    name_off, offset, count = struct.unpack_from("<IIi", ddt, pos)
    path = f"{parent}/{read_name(ddt, name_off)}".lstrip("/")
    if count < 0:
        yield path, True, offset, count, pos
        for i in range(-count):
            yield from walk(ddt, offset + 12 * i, path)
    else:
        yield path, False, offset, count, pos


def files(ddt: bytes):
    return [e for e in walk(ddt) if not e[1]]


def cmd_list(ddt_path):
    ddt = Path(ddt_path).read_bytes()
    print("path\tsector\timg_offset\tsize\tddt_entry")
    for path, _, sector, size, pos in files(ddt):
        print(f"{path}\t{sector}\t0x{sector * SECTOR:08X}\t{size}\t0x{pos:05X}")


def cmd_check(ddt_path, img_path):
    ddt = Path(ddt_path).read_bytes()
    img_size = Path(img_path).stat().st_size
    entries = list(walk(ddt))
    fs = [e for e in entries if not e[1]]
    dirs = [e for e in entries if e[1]]
    root_children = -entries[0][3]
    print(f"root: {root_children} children, {len(dirs)} directories, {len(fs)} files")

    ok = True
    # 1. Every file must fit inside the IMG
    out = [f for f in fs if f[2] * SECTOR + f[3] > img_size]
    print(f"[{'OK' if not out else 'KO'}] files outside the IMG: {len(out)}")
    ok &= not out

    # 2. No overlap between non-empty files (sorted by sector).
    #    0-byte files sometimes point inside a neighbour: harmless.
    srt = sorted((f for f in fs if f[3] > 0), key=lambda f: f[2])
    overlaps = [(a[0], b[0]) for a, b in zip(srt, srt[1:])
                if a[2] * SECTOR + a[3] > b[2] * SECTOR]
    print(f"[{'OK' if not overlaps else 'KO'}] overlaps: {len(overlaps)}")
    ok &= not overlaps

    # 3. Coverage: sum of sizes rounded to the sector vs IMG size
    used = sum(-(-f[3] // SECTOR) * SECTOR for f in fs)
    print(f"[info] bytes covered: {used} / {img_size} ({100 * used / img_size:.2f} %)")

    # 4. The file at sector 0 must start with the ELF seen at the start of the IMG
    first = srt[0]
    with open(img_path, "rb") as f:
        magic = f.read(4)
    print(f"[info] first file: {first[0]} (sector {first[2]}), IMG starts with {magic!r}")

    # 5. Every file name contains printable ASCII only
    bad = [e[0] for e in entries if not e[0].isprintable()]
    print(f"[{'OK' if not bad else 'KO'}] non-printable names: {len(bad)}")
    ok &= not bad
    print("=> consistent format" if ok else "=> HYPOTHESIS TO REVISE")


def cmd_extract(ddt_path, img_path, target, dest=None):
    ddt = Path(ddt_path).read_bytes()
    match = [f for f in files(ddt) if f[0] == target]
    if not match:
        sys.exit(f"not found: {target}")
    _, _, sector, size, _ = match[0]
    with open(img_path, "rb") as f:
        f.seek(sector * SECTOR)
        data = f.read(size)
    dest = Path(dest or Path("work/dds3") / target)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"{target}: sector {sector}, {size} bytes -> {dest}")


if __name__ == "__main__":
    cmds = {"list": cmd_list, "check": cmd_check, "extract": cmd_extract}
    if len(sys.argv) < 3 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]](*sys.argv[2:])
