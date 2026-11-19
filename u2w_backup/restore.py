# SPDX-License-Identifier: GPL-3.0-or-later
"""Put 8BitDo's firmware 1.09 back on bank A (0x5000-0x28800). Without --write it only checks and says what it would do.

Read-only first: the latest backup, 8BitDo's 1.09 from its server (checked by SHA-256), the bootloader by cable or in
update mode (it must match the backup), no update staged in the record at 0x31000, and identify 0x6012 in update mode.

At start-up the bootloader (0x1e4) sums the bytes of bank A over the length at 0x5018 (0x17a44 in 1.09) and compares the
sum with the word stored right after them (0x1ca44); if bank A fails, it checks bank B at 0x32000 and copies it back
(0xb5c). The rest of bank A, after that word, isn't covered. So the write starts by erasing the sector that holds the
word: from then on bank A fails the check until the very last write, which is that word. An interruption anywhere leaves
firmware the bootloader won't run. Then every other sector: erase 4 KB, write it in 46-byte chunks (the bootloader checks
each chunk's CRC), read it back. Sector 0x5000 holds the length the check reads, so it's skipped when it's already right
(it always is for 1.09), and otherwise written header first. Nothing outside 0x5000-0x29000 is erased or written:
BootWriter refuses it.
"""
import time

from u2c_customfw.protocol import boot

from . import core, update_mode as um

SIZE = 0x23800                       # 8BitDo's 1.09 payload
END = core.BASE + SIZE               # 0x28800
ERASE_END = 0x29000
SECTOR = 0x1000
RECORD = 0x31000
STAGED_MAGIC = (0xAEB14D6C).to_bytes(4, "little")
SECTORS = (ERASE_END - core.BASE) // SECTOR
STOPPED = ("The controller's firmware is half-written, and the controller is still in update mode. Run "
           "`python3 -m u2w_backup restore-original --write` again to finish. Until then it's best not to restart it "
           "(don't hold Home or run leave-update-mode). If it restarts anyway, its bootloader should find the firmware "
           "incomplete and copy 8BitDo's 1.09 back from the second copy at 0x32000; that's read from the bootloader's "
           "code, not yet seen happen.")


class BootWriter(um.BootReadsOnly):
    """Identify, read, restart, and erase (one aligned 4 KB sector) and write (46 bytes) only inside 0x5000-0x29000."""
    ALLOWED = (8, 5, 7, 4, 3)

    def xfer(self, report: bytes, timeout: float = 0.5, accept=None):
        cmd, addr = int.from_bytes(report[1:3], "little"), int.from_bytes(report[13:17], "little")
        n = int.from_bytes(report[5:7], "little") if cmd == 3 else int.from_bytes(report[9:13], "little")
        if cmd == 4 and not (addr % SECTOR == 0 and n == SECTOR and core.BASE <= addr < ERASE_END):
            raise core.Stop(f"Refused to erase {n:#x} bytes at {addr:#x}. " + STOPPED)
        if cmd == 3 and not (core.BASE <= addr and addr + n <= END and 0 < n <= boot.CHUNK):
            raise core.Stop(f"Refused to write {n} bytes at {addr:#x}. " + STOPPED)
        if len(report) != 64 or report[0] != 5 or cmd not in self.ALLOWED:
            raise core.Stop(f"Refused to send {report[:8].hex(' ')}. " + STOPPED)
        self.sent += 1
        if self.trace:
            self.trace.write(report.hex(" ") + "\n")
        return self.ch.xfer(report, timeout, accept)


def staged(record: bytes) -> bool:
    """The bootloader's own test (0xc0c): the magic at +0x18 and a length of 1 to 0x3efff at +0x20."""
    return record[0x18:0x1C] == STAGED_MAGIC and 1 <= int.from_bytes(record[0x20:0x24], "little") <= 0x3EFFF


def describe(record: bytes) -> str:
    """The fields the bootloader reads (0xae8, 0xc0c, 0xb5c): version, staged-update magic, source and length."""
    v = record[0x0C]
    return (f"version {v / 100:.2f}, " if v not in (0, 0xFF) else "no version, ") + \
        f"magic {record[0x18:0x1C][::-1].hex()}, source {int.from_bytes(record[0x1C:0x20], 'little'):#x}, " \
        f"length {int.from_bytes(record[0x20:0x24], 'little'):#x}"


def checked_word(payload: bytes) -> int:
    """Where the bootloader's start-up check keeps the sum it compares with: right after the summed part, whose length is
    at 0x5018 in the header."""
    a = core.BASE + int.from_bytes(payload[0x18:0x1C], "little")
    if not (core.BASE + SECTOR <= a and a + 4 <= END and a % 4 == 0):
        raise core.Stop("8BitDo's firmware header doesn't give a check length inside the firmware, so nothing was written.")
    return a


def _write_commit(ch, word: int, payload: bytes, erase: bool) -> bool:
    """The sector with the checked sum: everything but the sum's 4 bytes, then the sum, as the very last write."""
    a = word // SECTOR * SECTOR
    want = payload[a - core.BASE:a - core.BASE + SECTOR]
    if erase:
        boot.erase(ch, a, SECTOR)
    for lo, hi in ((a, word), (word + 4, a + len(want))):
        for c in range(lo, hi, boot.CHUNK):
            blk = payload[c - core.BASE:min(c + boot.CHUNK, hi) - core.BASE]
            if blk != b"\xff" * len(blk):
                boot.write_chunk(ch, c, SIZE, blk)
    boot.write_chunk(ch, word, SIZE, payload[word - core.BASE:word - core.BASE + 4])
    return boot.read(ch, a, SECTOR) == (want + b"\xff" * SECTOR)[:SECTOR]


def _write_sector(ch, a: int, payload: bytes) -> bool:
    want = payload[a - core.BASE:a - core.BASE + SECTOR]
    boot.erase(ch, a, SECTOR)
    for c in range(a, a + len(want), boot.CHUNK):
        blk = want[c - a:c - a + boot.CHUNK]
        if blk != b"\xff" * len(blk):
            boot.write_chunk(ch, c, SIZE, blk)
    return boot.read(ch, a, SECTOR) == (want + b"\xff" * SECTOR)[:SECTOR]


def run(devices, open_channel, folder, say, write=False, trace=None, opener=None, wait: float = 30.0) -> None:
    backup = um.latest_backup(folder)
    payload = core.official(opener) if opener else core.official()
    if payload is None or len(payload) != SIZE:
        raise core.Stop("8BitDo's firmware 1.09 couldn't be downloaded from its server and checked, so nothing was done.")
    same_now = backup[core.BASE:END] == payload
    say("status", "Downloaded 8BitDo's firmware 1.09 and checked its SHA-256. Your backup's firmware "
                  + ("is the same one." if same_now else "is NOT the same, so this puts 1.09 back."))
    bdev = next((d for d in devices() if um._in_boot(d)), None)
    if bdev is None:
        dev = core.find(devices())
        ch = um.EnterOnce(open_channel(dev, 0x81), trace)
        try:
            if core.read_range(ch, 0, core.BASE) != backup[:core.BASE]:
                raise core.Stop("This controller's bootloader isn't the one in your latest backup, so nothing was sent.")
            record = core.read_range(ch, RECORD, 0x34)
            say("status", "Update record at 0x31000: " + describe(record))
            if staged(record):
                raise core.Stop("A firmware update is staged on this controller, and its bootloader would install it over "
                                "this at the next start. Nothing was written.")
            if not write:
                word = checked_word(payload)
                say("status", f"Check passed: it would rewrite bank A ({SECTORS} sectors, 0x5000-0x29000) in update mode, "
                              f"erasing sector {word // SECTOR * SECTOR:#x} first and writing the start-up check's sum at "
                              f"{word:#x} last. Nothing was sent but reads.")
                say("done", "checked")
                return
            say("status", "Restarting into update mode (81 05 00 51 00).")
            ch.xfer(um.ENTER, 0.3)
        finally:
            ch.close()
        bdev = um._wait(devices, um._in_boot, wait)
        if bdev is None:
            raise core.Stop("The controller didn't show up in update mode within 30 seconds. If macOS asked whether to "
                            "allow the accessory, allow it and run this again. " + um.LEAVE_HELP)
    else:
        say("status", "The controller is already in update mode.")
    bch = BootWriter(open_channel(bdev, 0), trace)
    try:
        who = boot.identify(bch)
        if who != um.IDENTITY:
            raise core.Stop(f"The device in update mode identifies as {who if who is None else hex(who)}, not 0x6012, "
                            "so nothing else was sent to it.")
        if boot.read(bch, 0, core.BASE) != backup[:core.BASE]:
            raise core.Stop("The bootloader read in update mode isn't the one in your latest backup. Nothing was written. "
                            + um.LEAVE_HELP)
        if staged(boot.read(bch, RECORD, 0x24)):
            raise core.Stop("A firmware update is staged on this controller. Nothing was written. " + um.LEAVE_HELP)
        word = checked_word(payload)
        commit = word // SECTOR * SECTOR
        if not write:
            say("status", f"Check passed in update mode: it would rewrite bank A ({SECTORS} sectors). Nothing was written.")
            say("done", "checked")
            return
        say("status", f"Rewriting bank A one 4 KB sector at a time ({SECTORS} sectors). First, sector {commit:#x}, which "
                      f"holds the sum the bootloader checks at start-up ({word:#x}), is erased, so an interruption leaves "
                      "firmware it won't run; that sum is the last thing written. Keep the cable connected.")
        t0 = time.monotonic()
        boot.erase(bch, commit, SECTOR)
        done = 0
        for a in range(core.BASE, ERASE_END, SECTOR):
            if a == commit:
                continue
            if a == core.BASE and boot.read(bch, a, SECTOR) == payload[:SECTOR]:
                say("status", "Sector 0x5000, with the header the check reads, is already 8BitDo's, so it's left as it is.")
            elif not _write_sector(bch, a, payload) and not _write_sector(bch, a, payload):
                raise core.Stop(f"Sector {a:#x} didn't read back as written, twice. " + STOPPED)
            done += 1
            say("progress", done, SECTORS)
        if not _write_commit(bch, word, payload, erase=False) and not _write_commit(bch, word, payload, erase=True):
            raise core.Stop(f"Sector {commit:#x} didn't read back as written, twice. " + STOPPED)
        say("progress", SECTORS, SECTORS)
        if boot.read(bch, core.BASE, SIZE) != payload:
            raise core.Stop("Bank A doesn't read back as 8BitDo's 1.09. " + STOPPED)
        say("status", f"Written and read back in {time.monotonic() - t0:.0f} s. Restarting (bootloader command 7).")
        bch.xfer(boot.request(7), 0.5)
    except core.Stop:
        raise
    except Exception as e:  # noqa: BLE001 - say how to finish
        raise core.Stop(f"{e}. " + STOPPED) from e
    finally:
        bch.close()
    t1 = time.monotonic()
    back = um._wait(devices, lambda d: d.vendor == core.VENDOR and d.product in core.PRODUCTS and d.usage_page == core.PAGE, wait)
    if back is None:
        raise core.Stop("The controller didn't come back within 30 seconds. Hold LB + RB while plugging it in to put it "
                        "in update mode, then run this again.")
    ch = core.ReadsOnly(open_channel(back, 0x81), trace)
    try:
        ok = core.read_range(ch, core.BASE, SIZE) == payload
    finally:
        ch.close()
    say("status", f"Back after {time.monotonic() - t1:.1f} s as {back.vendor:04x}:{back.product:04x}; by cable its "
                  f"firmware {'reads as' if ok else 'does NOT read as'} 8BitDo's 1.09. Sent {bch.sent} reports in update mode.")
    if not ok:
        raise core.Stop("Please paste this output in the issue.")
    say("done", "8BitDo's firmware 1.09 restored")
