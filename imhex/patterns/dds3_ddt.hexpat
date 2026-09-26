// DDS3.DDT — index of the DDS3.IMG archive (Digital Devil Saga, SLUS-20974)
// Format described and validated in NOTES.md, section "DDS3.DDT / DDS3.IMG".
//
// Usage: open extracted/DDS3.DDT in ImHex, "Pattern editor" tab, paste this file
// (or File > Import > Pattern File), then Evaluate (F5).
// In "Pattern Data", expand root > children: each entry shows its name.
#pragma endian little
#pragma pattern_limit 2000000
#pragma array_limit 100000

import std.string;

struct Entry {
    u32 name_offset [[comment("Offset of the name in the DDT, 0 = root")]];
    u32 offset      [[comment("Directory: offset of the children in the DDT. File: sector (x 0x800) in the IMG")]];
    s32 count       [[comment("< 0: directory of -count children. >= 0: file size in bytes")]];
    if (name_offset != 0)
        std::string::NullString name @ name_offset;
    if (count < 0)
        Entry children[-count] @ offset;
};

Entry root @ 0x00;
