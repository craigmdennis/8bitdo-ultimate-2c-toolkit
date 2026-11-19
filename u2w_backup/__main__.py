# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs one backup and tells the app how it goes, one line at a time: note, status, progress, done or fail.

From source: python3 -m u2w_backup [check-update-mode | leave-update-mode | restore-original [--write]] [--trace FILE], where FILE gets every report
sent to the controller, in hex. With no command it makes a backup; check-update-mode is in update_mode.py."""
import os
import sys
from pathlib import Path

from . import core

FOLDER = Path.home() / "Documents" / "Ultimate 2 Wireless Backup"


def say(*words) -> None:
    print(*words, flush=True)


def run(devices, open_channel, folder: Path = FOLDER, opener=None, trace=None) -> None:
    found = devices()
    for d in found:   # so that a report of a failure says what macOS showed
        if d.vendor == core.VENDOR:
            say("note", f"Seen: {d.vendor:04x}:{d.product:04x}, page {d.usage_page:#06x}, {d.transport or '?'}, "
                        f"version {d.version:04x}, {d.name or 'no name'}")
    dev = core.find(found)
    say("status", f"Found {dev.name or 'the controller'} by cable ({core.PRODUCTS[dev.product]} mode).")
    ch = core.ReadsOnly(open_channel(dev, 0x81), trace)
    try:
        say("status", "Measuring the controller's memory.")
        size = core.flash_size(ch)
        say("status", f"Reading all {size // 1024} KB of it twice. Keep the cable connected.")
        data = core.take(ch, size, lambda d, t: say("progress", d, t))
    finally:
        ch.close()
    say("status", f"Sent {ch.sent} reports to the controller, all of them reads (81 05 05).")
    say("status", "Both reads are the same. Downloading 8BitDo's firmware 1.09 to compare with it.")
    payload = core.official(opener) if opener else core.official()
    if payload is None:
        say("status", "8BitDo's server couldn't be reached, so the report doesn't compare with its firmware.")
    backup, report = core.save(folder, data, payload, dev)
    say("status", f"Saved the backup as {backup.name} and the report as {report.name}.")
    say("done", report)


def main() -> None:
    from . import update_mode
    trace = open(sys.argv[sys.argv.index("--trace") + 1], "w", buffering=1) if "--trace" in sys.argv else None
    what = next((a for a in sys.argv[1:] if a in ("check-update-mode", "leave-update-mode", "restore-original")), "backup")
    try:
        if os.environ.get("U2W_SIM"):
            from . import sim
            devices, open_channel, folder = sim.list_devices, sim.open_channel, Path(os.environ["U2W_SIM"])
        else:
            from u2c_customfw import transport
            devices, open_channel, folder = transport.list_devices, transport.open_channel, FOLDER
        try:
            if what == "backup":
                run(devices, open_channel, folder, trace=trace)
            elif what == "restore-original":
                from . import restore
                restore.run(devices, open_channel, folder, say, write="--write" in sys.argv, trace=trace)
            elif what == "check-update-mode":
                update_mode.check(devices, open_channel, folder, say, trace)
            else:
                update_mode.leave(devices, open_channel, say, trace, folder)
        except Exception as e:
            if type(e).__name__ != "PermissionDenied":
                raise
            raise core.Stop(str(e)) from e
    except core.Stop as e:
        say("fail", e)
    except Exception as e:  # noqa: BLE001 - the app shows it instead of a silent stop
        say("fail", f"Something unexpected went wrong: {e!r}")
        sys.exit(1)


if __name__ == "__main__":
    main()
