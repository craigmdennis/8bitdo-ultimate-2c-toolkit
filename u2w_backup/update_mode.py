# SPDX-License-Identifier: GPL-3.0-or-later
"""Check, without writing anything to the flash, how the controller enters and leaves update mode.

1. By cable, through the update channel: `81 05 05` reads of the bootloader, to check it's the controller in the backup.
2. `81 05 00 51 00`: the firmware's handler (0x11504 in 1.09) sets analog register 0x3c to 0x5a and restarts; the
   bootloader sees it and stays in update mode (2dc8:3208). Nothing in the flash changes.
3. In update mode, only bootloader commands 8 (identify: 0x6012 for this controller), 5 (read) and 7 (restart, which
   clears the register) are ever sent: the bootloader and bank A are read and compared with the backup.
4. Command 7, and the controller should come back as before.
Erase (4) and write (3) are never sent; BootReadsOnly refuses them, and refuses any address below 0x5000 for them anyway.
"""
import time
from pathlib import Path

from u2c_customfw.protocol import boot

from . import core

BOOT_PID, IDENTITY = 0x3208, 0x6012
ENTER = bytes([0x81, 0x05, 0x00, 0x51, 0x00]).ljust(64, b"\0")
BANK_A_END = 0x28800          # 8BitDo's 1.09: 0x23800 bytes from 0x5000
LEAVE_HELP = ("To leave update mode, run `python3 -m u2w_backup leave-update-mode`, or hold Home for about 12 seconds "
              "with the cable unplugged (as on the Ultimate 2C). Nothing was written to the controller's memory.")


class EnterOnce(core.ReadsOnly):
    """The update channel: reads, and the one report that enters update mode."""
    def xfer(self, report: bytes, timeout: float = 0.5, accept=None):
        if report == ENTER:
            self.sent += 1
            if self.trace:
                self.trace.write(report.hex(" ") + "\n")
            return self.ch.xfer(report, timeout, accept)
        return super().xfer(report, timeout, accept)


class BootReadsOnly:
    """The bootloader channel: identify, read and restart only."""
    ALLOWED = (8, 5, 7)

    def __init__(self, ch, trace=None):
        self.ch, self.trace, self.sent = ch, trace, 0

    def xfer(self, report: bytes, timeout: float = 0.5, accept=None):
        cmd, addr = int.from_bytes(report[1:3], "little"), int.from_bytes(report[13:17], "little")
        if len(report) != 64 or report[0] != 5 or cmd not in self.ALLOWED or (cmd in (3, 4) and addr < core.BASE):
            raise core.Stop(f"Refused to send a bootloader command that isn't identify, read or restart: "
                            f"{report[:8].hex(' ')}. {LEAVE_HELP}")
        self.sent += 1
        if self.trace:
            self.trace.write(report.hex(" ") + "\n")
        return self.ch.xfer(report, timeout, accept)

    def close(self) -> None:
        self.ch.close()


def _wait(devices, want, seconds: float, step: float = 0.25):
    end = time.monotonic() + seconds
    while True:
        found = [d for d in devices() if want(d)]
        if found or time.monotonic() >= end:
            return found[0] if found else None
        time.sleep(step)


def _in_boot(d):
    return d.vendor == core.VENDOR and d.product == BOOT_PID


def _restart(open_channel, dev, trace, say) -> int:
    ch = BootReadsOnly(open_channel(dev, 0), trace)
    try:
        ch.xfer(boot.request(7), 0.5)   # it restarts at once, with no reply
    finally:
        ch.close()
    return ch.sent


def latest_backup(folder: Path) -> bytes:
    backups = sorted(folder.glob("backup-*.bin"))
    if not backups:
        raise core.Stop("Make a backup first (python3 -m u2w_backup), so this check has something to compare with.")
    return backups[-1].read_bytes()


def check(devices, open_channel, folder: Path, say, trace=None, wait: float = 30.0) -> None:
    backup = latest_backup(folder)
    dev = core.find(devices())
    say("status", f"Found {dev.name or 'the controller'} by cable. Checking that it's the controller in your backup.")
    ch = EnterOnce(open_channel(dev, 0x81), trace)
    try:
        if core.read_range(ch, 0, core.BASE) != backup[:core.BASE]:
            raise core.Stop("This controller's bootloader isn't the one in your latest backup, so nothing was sent. "
                            "Connect the controller you backed up.")
        say("status", "It matches. Asking the firmware to restart into update mode (81 05 00 51 00).")
        ch.xfer(ENTER, 0.3)
    finally:
        ch.close()
    sent_app = ch.sent
    t0 = time.monotonic()
    bdev = _wait(devices, _in_boot, wait)
    if bdev is None:
        raise core.Stop("The controller didn't show up in update mode within 30 seconds. If macOS asked whether to allow "
                        "the accessory, allow it and run this again. " + LEAVE_HELP)
    say("status", f"In update mode after {time.monotonic() - t0:.1f} s, as {bdev.vendor:04x}:{bdev.product:04x} "
                  f"version {bdev.version:04x}, {bdev.name or 'no name'}.")
    bch = BootReadsOnly(open_channel(bdev, 0), trace)
    try:
        who = boot.identify(bch)
        if who != IDENTITY:
            raise core.Stop(f"The device in update mode identifies as {who if who is None else hex(who)}, not 0x6012, "
                            "so nothing else was sent to it. " + LEAVE_HELP)
        say("status", "It identifies as 0x6012. Reading the bootloader and the firmware in update mode.")
        same_boot = boot.read(bch, 0, core.BASE) == backup[:core.BASE]
        same_fw = boot.read(bch, core.BASE, BANK_A_END - core.BASE,
                            lambda d, t: say("progress", d, t)) == backup[core.BASE:BANK_A_END]
    except core.Stop:
        raise
    except Exception as e:  # noqa: BLE001 - say how to get out
        raise core.Stop(f"Reading in update mode failed ({e}). {LEAVE_HELP}") from e
    finally:
        bch.close()
    say("status", f"Bootloader read in update mode {'matches' if same_boot else 'DOES NOT match'} the backup; "
                  f"firmware {'matches' if same_fw else 'DOES NOT match'}.")
    say("status", "Leaving update mode (bootloader command 7).")
    sent_boot = bch.sent + _restart(open_channel, bdev, trace, say)
    t1 = time.monotonic()
    back = _wait(devices, lambda d: d.vendor == core.VENDOR and d.product in core.PRODUCTS and d.usage_page == core.PAGE, wait)
    if back is None:
        raise core.Stop("The controller didn't come back from update mode within 30 seconds. " + LEAVE_HELP)
    say("status", f"Back after {time.monotonic() - t1:.1f} s as {back.vendor:04x}:{back.product:04x}.")
    say("status", f"Sent {sent_app} reports to the firmware (81 05 05 reads and one 81 05 00 51 00) and {sent_boot} to "
                  "the bootloader (identify, read and one restart). Nothing was erased or written.")
    if not (same_boot and same_fw):
        raise core.Stop("The reads in update mode didn't match the backup. Please paste this output in the issue.")
    say("done", "update mode checked")


def leave(devices, open_channel, say, trace=None, folder: Path | None = None, opener=None) -> None:
    """Restart out of update mode, but only with a whole firmware in bank A: the backup's, or 8BitDo's 1.09."""
    bdev = next((d for d in devices() if _in_boot(d)), None)
    if bdev is None:
        raise core.Stop("No controller in update mode was found.")
    bch = BootReadsOnly(open_channel(bdev, 0), trace)
    try:
        who = boot.identify(bch)
        bank = boot.read(bch, core.BASE, BANK_A_END - core.BASE) if who == IDENTITY else None
    finally:
        bch.close()
    if who != IDENTITY:
        raise core.Stop(f"The device in update mode identifies as {who if who is None else hex(who)}, not as this "
                        "controller, so nothing else was sent to it.")
    backups = sorted(Path(folder).glob("backup-*.bin")) if folder else []
    whole = bool(backups) and bank == backups[-1].read_bytes()[core.BASE:BANK_A_END]
    if not whole:
        payload = core.official(opener) if opener else core.official()
        whole = payload is not None and bank == payload[:BANK_A_END - core.BASE]
    if not whole:
        raise core.Stop("The firmware on the controller isn't whole (it matches neither your backup nor 8BitDo's 1.09), "
                        "so it was left in update mode. Run `python3 -m u2w_backup restore-original --write` to finish.")
    _restart(open_channel, bdev, trace, say)
    say("done", "restart sent; the controller should come back within a few seconds")
