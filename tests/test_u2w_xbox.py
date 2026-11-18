# SPDX-License-Identifier: GPL-3.0-or-later
import struct
import unittest

from u2w_xbox import patch


def bank_with_originals() -> bytearray:
    """A stand-in bank A: 1.10's header fields, its original bytes at every edit site, and both checks valid."""
    bank = bytearray(patch.BANK_END - patch.BANK_A)
    bank[patch.DATA_END - patch.BANK_A:] = b"\xff" * (patch.BANK_END - patch.DATA_END)
    struct.pack_into("<H", bank, 2, 110)
    bank[8:12] = b"KNLT"
    struct.pack_into("<I", bank, patch.HSIZE_AT, 0x17A64)
    for addr, old, _ in (patch.PNP, patch.HOOK, patch.RUMBLE, patch.OUT_REF,
                         (patch.MAP_ADDR, patch.STOCK_MAP, ""), (patch.MAP_LEN_AT, "71 00 00 00", "")):
        b = bytes.fromhex(old)
        bank[addr - patch.BANK_A:addr - patch.BANK_A + len(b)] = b
    h, crc, total = patch.checks(bank)
    struct.pack_into("<II", bank, h - 4, crc, total)
    return bank


def flash(bank: bytes) -> bytes:
    return b"\xff" * patch.BANK_A + bytes(bank)


class Patch(unittest.TestCase):
    def test_patched_bank_passes_both_checks_and_changes_only_the_edits(self):
        original = bank_with_originals()
        out = patch.patch(flash(original))
        patch.verify(bytes(original), out)
        o = patch.PNP[0] - patch.BANK_A
        self.assertEqual(out[o:o + 7], bytes.fromhex(patch.PNP[2]))
        self.assertEqual(struct.unpack_from("<I", out, patch.MAP_LEN_AT - patch.BANK_A)[0], 98)
        r = patch.RUMBLE_ADDR - patch.BANK_A
        routine = bytes.fromhex("".join(patch.RUMBLE_ROUTINE))
        self.assertEqual(out[r:r + len(routine)], routine)
        q = patch.RUMBLE_TABLE_ADDR - patch.BANK_A
        self.assertEqual(out[q:q + 101], patch.RUMBLE_TABLE)

    def test_input_report_1_is_38_bytes(self):
        # XboxOneHIDServicePlugin reads the paddles from byte 17 only in a 39-byte report (38 bytes and the ID).
        m = bytes.fromhex(patch.XBOX_MAP)
        bits, size, count, report = 0, 0, 0, None
        i = 0
        while i < len(m):
            tag, n = m[i], m[i] & 3
            val = int.from_bytes(m[i + 1:i + 1 + n], "little")
            if tag & 0xFC == 0x84:
                report = val
            elif tag & 0xFC == 0x74:
                size = val
            elif tag & 0xFC == 0x94:
                count = val
            elif tag & 0xFC == 0x80 and report == 1:
                bits += size * count
            i += 1 + n
        self.assertEqual(bits, 38 * 8)
        self.assertEqual(patch.PNP[2], "02 5e 04 05 0b 01 00")

    def test_layout_leaves_no_overlap(self):
        cave = len("".join(patch.CAVE)) // 2
        routine = len("".join(patch.RUMBLE_ROUTINE)) // 2
        self.assertLessEqual(patch.RUMBLE_TABLE_ADDR + len(patch.RUMBLE_TABLE), patch.CAVE_ADDR)
        self.assertLessEqual(patch.CAVE_ADDR + cave, patch.RUMBLE_ADDR)
        self.assertLessEqual(patch.RUMBLE_ADDR + routine, 0x1CA5C)

    def test_core_haptics_table_undoes_the_square(self):
        # GameController sends intensity p as 100 * p^2. The table must give 28 + 227 * p, and 0 for 0.
        for p in (0.1, 0.3, 0.5, 0.7, 1.0):
            sent = round(100 * p * p)
            self.assertAlmostEqual(patch.RUMBLE_TABLE[sent], patch.MIN_STRENGTH + 227 * p, delta=4)
        self.assertEqual((patch.RUMBLE_TABLE[0], patch.RUMBLE_TABLE[100]), (0, 255))

    def test_rumble_strength_from_sdl(self):
        # rumble.s for SDL's packets: v * 164 >> 6, capped at 255, with no minimum.
        strength = lambda v: min(v * 164 >> 6, 255)
        self.assertEqual([strength(v) for v in (0, 1, 50, 100, 255)], [0, 2, 128, 255, 255])

    def test_refuses_a_bank_that_differs_at_an_edit_site(self):
        bank = bank_with_originals()
        bank[patch.HOOK[0] - patch.BANK_A] ^= 1
        h, crc, total = patch.checks(bank)
        struct.pack_into("<II", bank, h - 4, crc, total)
        with self.assertRaises(patch.NotStock):
            patch.patch(flash(bank))

    def test_refuses_a_bank_that_fails_its_checks(self):
        bank = bank_with_originals()
        bank[0x100] ^= 1
        with self.assertRaises(patch.NotStock):
            patch.stock(flash(bank))


if __name__ == "__main__":
    unittest.main()
