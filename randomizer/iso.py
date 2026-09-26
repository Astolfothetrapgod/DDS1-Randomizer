"""Access to the game files inside the player's ISO.

Everything is read from the ISO itself (ISO9660, then the DDS3.DDT index, then DDS3.IMG): the
randomizer needs no extracted file. Formats: NOTES.md §1 and §2.
Files at the ISO9660 root (executable `SLUS_209.74`…) are accessed by their bare name.
"""
import hashlib
import struct
from pathlib import Path

import pycdlib

SECTOR_ISO = 2048
SECTOR_IMG = 0x800
SERIAL = "SLUS_209.74"
ROOT_FILES = ("SLUS_209.74",)       # ISO9660 root files that can be read / rewritten
# Hashes of the original files the randomizer reads or rewrites (NTSC-U v1.00, Redump #253). These are
# only hashes: no game data. An already randomized ISO or another version is refused.
ORIGINAL_MD5 = {
    "SLUS_209.74": "5c357d5afe565bea62c4ca613470f678",
    "battle/UNIT.TBL": "991f5a4ff4fd31df75519aa14d609b8b",
    "battle/ENCOUNT.TBL": "805219aded091f906f6576894081889d",
    "battle/AICALC.TBL": "f35c3be07c1de2d260fa6c59fcf19f57",
    "battle/MSG.TBL": "9802f3a9d58273eae384651bb0dd2e08",
    "battle/SKILL.TBL": "e8e7e608ee5d284ca53cf37e102ea714",
    "fld/f/bin/FLDALL.TBL": "82e6c992bc665a8bbef0a47bb05a8b8a",
}
REDUMP_MD5, REDUMP_SIZE = "ae4330140ef56f9eb1c689b9bb383401", 4539547648     # whole ISO (Redump #253)


def _walk_ddt(ddt: bytes, pos: int = 0, parent: str = ""):
    """12-byte DDT entry: u32 name offset, u32 offset, i32 count (< 0: directory).
    Yields (path, sector, size, position of the entry in the DDT) for each file."""
    name_off, offset, count = struct.unpack_from("<IIi", ddt, pos)
    name = ddt[name_off:ddt.index(b"\0", name_off)].decode("ascii") if name_off else ""
    path = f"{parent}/{name}".lstrip("/")
    if count < 0:
        for i in range(-count):
            yield from _walk_ddt(ddt, offset + 12 * i, path)
    else:
        yield path, offset, count, pos


class GameISO:
    """A DDS1 NTSC-U ISO: locates, reads and rewrites the files of DDS3.IMG (and root files)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        iso = pycdlib.PyCdlib()
        iso.open(str(self.path))
        try:
            cnf = self._read_iso_file(iso, "/SYSTEM.CNF;1").decode("ascii", "replace")
            if SERIAL not in cnf:
                raise ValueError(f"{self.path} is not Digital Devil Saga NTSC-U ({SERIAL} missing from SYSTEM.CNF)")
            self.ddt = bytearray(self._read_iso_file(iso, "/DDS3.DDT;1"))
            self.ddt_offset = iso.get_record(iso_path="/DDS3.DDT;1").extent_location() * SECTOR_ISO
            self.img_offset = iso.get_record(iso_path="/DDS3.IMG;1").extent_location() * SECTOR_ISO
            root = {}
            for name in ROOT_FILES:
                rec = iso.get_record(iso_path=f"/{name};1")
                root[name] = (rec.extent_location() * SECTOR_ISO, rec.get_data_length())
        finally:
            iso.close()
        entries = list(_walk_ddt(bytes(self.ddt)))
        # path -> (absolute offset in the ISO, size); path -> position of the entry in the DDT
        self.files = {p: (self.img_offset + sector * SECTOR_IMG, size) for p, sector, size, _ in entries}
        self.files |= root
        self._entry = {p: pos for p, _, _, pos in entries}

    @staticmethod
    def _read_iso_file(iso: pycdlib.PyCdlib, iso_path: str) -> bytes:
        with iso.open_file_from_iso(iso_path=iso_path) as f:
            return f.read()

    def check_original(self) -> None:
        """Refuses an ISO whose used files are not the original ones (other version, already randomized
        ISO, modified dump). Fast: only these files are read (a few MB)."""
        bad = [name for name, md5 in ORIGINAL_MD5.items() if hashlib.md5(self.read(name)).hexdigest() != md5]
        if bad:
            raise ValueError(
                f"{self.path}: files differ from the original ({', '.join(bad)}).\n"
                "The unmodified original ISO of Digital Devil Saga NTSC-U v1.00 (SLUS-20974) is required:\n"
                "an already randomized ISO cannot be used as the source.")

    def check_full(self, progress=None) -> None:
        """Compares the whole ISO with the Redump hash (full read, ~4.5 GB)."""
        if self.path.stat().st_size != REDUMP_SIZE:
            raise ValueError(f"{self.path}: size {self.path.stat().st_size} bytes, expected {REDUMP_SIZE} (Redump #253)")
        md5 = hashlib.md5()
        with open(self.path, "rb") as f:
            while chunk := f.read(1 << 24):
                md5.update(chunk)
                if progress:
                    progress(f.tell() / REDUMP_SIZE)
        if md5.hexdigest() != REDUMP_MD5:
            raise ValueError(f"{self.path}: MD5 {md5.hexdigest()}, expected {REDUMP_MD5} (Redump #253)")

    def read(self, name: str) -> bytes:
        offset, size = self.files[name]
        with open(self.path, "rb") as f:
            f.seek(offset)
            return f.read(size)

    def alias(self, name: str, target: str) -> None:
        """Makes the DDT entry of `name` point to the data of `target` (sector and size).
        No data is moved; the DDT keeps its size. Call write_ddt() afterwards."""
        sector, size = struct.unpack_from("<Ii", self.ddt, self._entry[target] + 4)
        struct.pack_into("<Ii", self.ddt, self._entry[name] + 4, sector, size)
        self.files[name] = self.files[target]

    def write_ddt(self) -> None:
        with open(self.path, "r+b") as f:
            f.seek(self.ddt_offset)
            f.write(self.ddt)

    def write(self, name: str, data: bytes) -> None:
        """Rewrites a file in place. The size must be identical: nothing shifts."""
        offset, size = self.files[name]
        if len(data) != size:
            raise ValueError(f"{name}: {len(data)} bytes instead of {size}")
        with open(self.path, "r+b") as f:
            f.seek(offset)
            f.write(data)


def pcsx2_crc(elf: bytes) -> int:
    """Game identifier used by PCSX2 (names of savestates and .pnach cheats): XOR of every 32-bit word
    of the executable. ✅ gives D7273511 (original) and D40A3465 (mantra test 3).
    Any change to the executable therefore changes this code."""
    crc = 0
    for (word,) in struct.iter_unpack("<I", elf[:len(elf) // 4 * 4]):
        crc ^= word
    return crc

