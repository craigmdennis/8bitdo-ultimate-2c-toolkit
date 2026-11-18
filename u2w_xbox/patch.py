# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a bank A image (0x5000-0x29000) for the 8BitDo Ultimate 2 Wireless, firmware 1.10, from a u2w_backup backup.

python3 -m u2w_xbox.patch BACKUP.bin OUT.bin            the Xbox Elite image
python3 -m u2w_xbox.patch --stock BACKUP.bin OUT.bin    the unmodified bank, to put the original firmware back

Addresses are flash addresses. Bank A starts at 0x5000. Code above the RAM code (which ends below 0x9000) runs from
flash at its own address, so the hook, the cave and the rumble callback use the same numbers as the flash.

Bank A contains two checks over its first hsize-4 bytes (hsize is the header word at +0x18): a Telink CRC (~crc32) at
hsize-4, and at hsize the byte sum that the bootloader compares at start-up. Both are recomputed after the edits.
"""
import struct
import sys
import zlib

BANK_A, BANK_END = 0x5000, 0x29000
DATA_END = 0x28800                                   # 1.10 and 1.09 are 0x23800 bytes. The rest of the bank is 0xff.
HSIZE_AT = 0x18

# Each edit is (address, 1.10 bytes, new bytes). patch() compares every 1.10 value before it changes anything.
PNP = (0x1B54C, "12 c8 2d 12 60 01 00", "02 5e 04 05 0b 01 00")   # PnP ID: 2dc8:6012 -> 045e:0b05, Xbox Elite Series 2
STOCK_MAP = (                                                      # 113 bytes: input report 1 of 33 bytes, output 5
    "05 01 09 05 a1 01 85 01 05 01 15 00 25 07 46 3b 01 95 01 75 04 65 14 09 39 81 42"
    " 75 01 95 04 81 01 15 00 26 ff 00 09 30 09 31 09 32 09 35 95 04 75 08 81 02 05 02"
    " 15 00 26 ff 00 09 c4 09 c5 95 02 75 08 81 02 05 09 19 01 29 18 15 00 25 01 75 01"
    " 95 18 81 02 06 00 ff 09 20 75 08 95 17 81 02 05 0f 09 70 85 05 15 00 25 64 75 08"
    " 95 04 91 02 c0")
XBOX_MAP = (                                                       # 98 bytes: input report 1 of 38 bytes, output 3
    "05010905a1018501093009310933093426ffff950475108102050209c409c526ffff95027510810205"
    "010939250895017504814295017504810305091901291025019510750181020600ff09017508951781"
    "02050f092185030970750895089102c0")
MAP_ADDR = 0x1B4D8                                   # report map value. Its GATT entry is at 0x1b928, with the length at +4.
MAP_LEN_AT = 0x1B92C
HOOK = (0xE458, "40 a0 1d a1 22 ec 21 a3 0a 90 36 9a",          # notify(0x40, 0x1d, payload, 33) -> tjl cave, 4 nops
        "0e 90 12 9a c0 06 c0 06 c0 06 c0 06")
CAVE_ADDR = 0x1C880                                  # zero padding after the initialised data, with no references
CAVE = (                                             # cave.s linked at 0x1c880 with notify=0x188d0 and back=0xe464
    "8a6025ec6c06684820406040a848a040e040e848204160412849a041e041a84982f981f01103214262426849"
    "82f981f01103a142e242284808a801c400a0008001b02043e849dba108006043284a7ca10800a04300a00fa1"
    "601401b126a9fbc10ea1681c0aec08b2a01401b11aa9f8c1684ae94942f801a31a0080f004a31800020348f8"
    "02a31800020388f808a318000203224440a01da122ec26a3fb97d89f0a60f1979f9d")
RUMBLE = (0xD53E, "60 4a a1 4a", "0f 90 ff 99")     # output callback: two loads -> tjl RUMBLE_ADDR
RUMBLE_ADDR = 0x1C940                                # after the cave, in the same zero padding
RUMBLE_ROUTINE = (                                   # rumble.s linked at 0x1c940 with table=0x1c780
    "204ba24a900200c210ec614be24a910200c211ec224cebaa09c064a800c964a064a900c964a1080b181c591c"
    "7007a4a3580380f9ffa800c9ffa0590389f9ffa900c9ffa17007c04680c70100")
# The motors start to turn at strength 28 (about 29 % PWM duty). For GameController's packets only, the table maps
# every strength above 0 onto 28-255. SDL's packets keep the plain linear conversion.
MIN_STRENGTH = 28
# GameController sends Core Haptics intensity p as strength 100 * p^2. For GameController's packets (loop count 0,
# where SDL sends 0xeb), rumble.s looks the strength up here to drive the motor at 28 + 227 * p.
RUMBLE_TABLE_ADDR = 0x1C780
RUMBLE_TABLE = bytes(0 if x == 0 else MIN_STRENGTH + int((255 - MIN_STRENGTH) * (x / 100) ** 0.5 + 0.5) for x in range(101))
OUT_REF = (0x1C6F0, "05 02", "03 02")               # initial output report reference: report 3, output


class NotStock(Exception):
    """The backup does not contain a whole stock 1.10 bank A."""


def checks(bank) -> tuple[int, int, int]:
    h = struct.unpack_from("<I", bank, HSIZE_AT)[0]
    return h, (~zlib.crc32(bank[:h - 4])) & 0xFFFFFFFF, sum(bank[:h - 4]) & 0xFFFFFFFF


def stock(flash: bytes) -> bytes:
    """Bank A of the backup, after checking it's a whole 1.10 that passes both of its checks."""
    bank = bytes(flash[BANK_A:BANK_END])
    if len(bank) != BANK_END - BANK_A or bank[8:12] != b"KNLT" or struct.unpack_from("<H", bank, 2)[0] != 110:
        raise NotStock("bank A isn't firmware 1.10")
    h, crc, total = checks(bank)
    if struct.unpack_from("<II", bank, h - 4) != (crc, total):
        raise NotStock("bank A fails its CRC or start-up sum")
    if bank[DATA_END - BANK_A:] != b"\xff" * (BANK_END - DATA_END):
        raise NotStock("bank A has data past 0x28800")
    return bank


def edit(bank: bytearray, addr: int, old: str, new: str) -> None:
    old_b, new_b = bytes.fromhex(old), bytes.fromhex(new)
    o = addr - BANK_A
    if bytes(bank[o:o + len(old_b)]) != old_b:
        raise NotStock(f"{addr:#x} does not contain the 1.10 bytes {old_b.hex(' ')}")
    bank[o:o + len(new_b)] = new_b


def patch(flash: bytes) -> bytes:
    bank = bytearray(stock(flash))
    xmap, cave = bytes.fromhex(XBOX_MAP), bytes.fromhex(CAVE)
    edit(bank, *PNP)
    edit(bank, MAP_ADDR, STOCK_MAP, (xmap + bytes(113 - len(xmap))).hex())
    edit(bank, MAP_LEN_AT, "71 00 00 00", struct.pack("<I", len(xmap)).hex())
    edit(bank, *HOOK)
    edit(bank, CAVE_ADDR, bytes(len(cave)).hex(), cave.hex())
    edit(bank, *RUMBLE)
    routine = bytes.fromhex("".join(RUMBLE_ROUTINE))
    edit(bank, RUMBLE_ADDR, bytes(len(routine)).hex(), routine.hex())
    edit(bank, RUMBLE_TABLE_ADDR, bytes(len(RUMBLE_TABLE)).hex(), RUMBLE_TABLE.hex())
    edit(bank, *OUT_REF)
    h, crc, total = checks(bank)
    struct.pack_into("<II", bank, h - 4, crc, total)
    return bytes(bank)


def edited_ranges(h: int) -> list[tuple[int, int]]:
    return [(PNP[0], 7), (MAP_ADDR, 113), (MAP_LEN_AT, 4), (HOOK[0], 12), (CAVE_ADDR, len(CAVE) // 2),
            (RUMBLE[0], 4), (RUMBLE_ADDR, len("".join(RUMBLE_ROUTINE)) // 2), (RUMBLE_TABLE_ADDR, len(RUMBLE_TABLE)), (OUT_REF[0], 2), (BANK_A + h - 4, 8)]


def verify(original: bytes, patched: bytes) -> None:
    """Both checks pass, and every changed byte is inside an edit."""
    h, crc, total = checks(patched)
    if struct.unpack_from("<II", patched, h - 4) != (crc, total):
        raise AssertionError("the patched bank fails its own checks")
    ranges = edited_ranges(h)
    for i, (a, b) in enumerate(zip(original, patched)):
        if a != b and not any(s <= BANK_A + i < s + n for s, n in ranges):
            raise AssertionError(f"unexpected change at {BANK_A + i:#x}")


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--stock"]
    if len(args) != 2:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    flash = open(args[0], "rb").read()
    try:
        out = stock(flash) if "--stock" in argv else patch(flash)
    except NotStock as e:
        print(f"Nothing written: {e}.", file=sys.stderr)
        return 1
    if "--stock" not in argv:
        verify(flash[BANK_A:BANK_END], out)
    open(args[1], "wb").write(out)
    h, crc, total = checks(out)
    print(f"Wrote {args[1]}: {len(out):#x} bytes, CRC {crc:#010x}, start-up sum {total:#x}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
