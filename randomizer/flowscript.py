"""Enemy AI scripts: Atlus `FLW0` Flowscript (AICALC.TBL block 2).

Format (✅ checked on the data, see NOTES "AI scripts"):
- 0x20 header: +0x08 "FLW0", +0x10 u32 number of sections (+0x04 = 194 830 = start of section 4,
  not the total size 195 070: ❓ unused);
- then one 16-byte entry per section: (u32 type, u32 element size, u32 count, u32 address);
  type 0 = procedures (32 bytes: 24-byte name + u32 index of the first instruction), type 2 = code;
- instruction = u16 opcode + u16 argument; PUSHI (0) and PUSHF (1) are followed by a 4-byte constant;
- procedures are contiguous and end with END (9).

Calls found (numbers from Atlus-Script-Tools' `dds` library, confirmed in the bytes):
- `PUSHIS skill ; COMM 0x33` = AI_ACT_SKILL (cast a skill);
- `PUSHIS unit ; PUSHIS skill ; COMM 0xE2` = AI_ACT_SKILL_PARAM (summon a unit);
- `PUSHIS skill ; COMM 0x19E` = AI_CHK_MYABLESKIL (does the unit have this skill?).
Unit running a script: AICALC block 0, u16 at +0x02 of its row = procedure index (0 = none).
"""
import struct
from dataclasses import dataclass, field

PUSHI, PUSHF, COMM, END, PUSHIS = 0x00, 0x01, 0x08, 0x09, 0x1D
ACT_SKILL, ACT_SKILL_PARAM, CHK_MYABLESKIL = 0x33, 0xE2, 0x19E
SECTION_PROCS, SECTION_CODE = 0, 2


@dataclass
class Procedure:
    index: int
    name: str
    start: int                     # index of the first instruction
    end: int                       # excluded
    casts: list[int] = field(default_factory=list)      # positions of the AI_ACT_SKILL PUSHIS
    summons: list[int] = field(default_factory=list)    # positions of the summoned unit's PUSHIS
    checks: list[int] = field(default_factory=list)     # positions of the AI_CHK_MYABLESKIL PUSHIS


class FlowScript:
    """Reads a FLW0 located at `base` in `data` and rewrites the (u16) argument of a PUSHIS in place
    (same bytearray as the table: nothing to copy back, the size never changes)."""

    def __init__(self, data: bytearray, base: int = 0, length: int | None = None):
        self.data, self.base = data, base
        length = len(data) - base if length is None else length
        if self.data[base + 8:base + 12] != b"FLW0":
            raise ValueError("not a FLW0 Flowscript")
        sections = {}
        for i in range(struct.unpack_from("<I", self.data, base + 0x10)[0]):
            kind, size, count, addr = struct.unpack_from("<4I", self.data, base + 0x20 + 16 * i)
            if addr + size * count > length:
                raise ValueError(f"section {kind} outside the file")
            sections[kind] = (size, count, base + addr)
        size, count, addr = sections[SECTION_PROCS]
        heads = [(self.data[addr + i * size:addr + i * size + 24].split(b"\0")[0].decode(),
                  struct.unpack_from("<I", self.data, addr + i * size + 24)[0]) for i in range(count)]
        _, self.n_code, self.code = sections[SECTION_CODE]
        self.procedures = [Procedure(i, name, start, heads[i + 1][1] if i + 1 < count else self.n_code)
                           for i, (name, start) in enumerate(heads)]
        self._scan()

    def instr(self, k: int) -> tuple[int, int]:
        return struct.unpack_from("<HH", self.data, self.code + 4 * k)

    def arg(self, k: int) -> int:
        return self.instr(k)[1]

    def set_arg(self, k: int, value: int) -> None:
        if self.instr(k)[0] != PUSHIS:
            raise ValueError(f"instruction {k} is not a PUSHIS")
        struct.pack_into("<H", self.data, self.code + 4 * k + 2, value)

    def _scan(self) -> None:
        for p in self.procedures:
            k, prev = p.start, []                 # prev = positions of the decoded instructions
            while k < p.end:
                op, a = self.instr(k)
                if op == COMM and prev and self.instr(prev[-1])[0] == PUSHIS:
                    if a == ACT_SKILL:
                        p.casts.append(prev[-1])
                    elif a == CHK_MYABLESKIL:
                        p.checks.append(prev[-1])
                    elif a == ACT_SKILL_PARAM and len(prev) > 1 and self.instr(prev[-2])[0] == PUSHIS:
                        p.summons.append(prev[-2])
                prev.append(k)
                k += 2 if op in (PUSHI, PUSHF) else 1
            if k != p.end or self.instr(p.end - 1)[0] != END:
                raise ValueError(f"procedure {p.name} badly delimited")
