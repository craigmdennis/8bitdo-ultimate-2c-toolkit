# SPDX-License-Identifier: GPL-3.0-or-later
"""Write a bank A image from u2w_xbox.patch to the controller, with u2w_backup's writer.

python3 -m u2w_xbox.write IMAGE.bin [--write] [--trace FILE]

Without --write, the command only reads. With --write, it runs u2w_backup.restore.run unchanged, with IMAGE in place
of 8BitDo's 1.09. The writer requires a bootloader that matches the latest backup, and no staged update. BootWriter
limits erases and writes to 0x5000-0x29000. The writer writes the sector with the start-up sum last, and reads
everything back. Its messages name 1.09, because the wording of restore.run names 1.09. The bytes written come from
IMAGE.
"""
import sys
from pathlib import Path

from u2w_backup import __main__ as app, core, restore

from . import patch


def _checked(bank: bytes) -> bytes:
    """The image's firmware bytes, refused unless it is a whole bank that passes both checks."""
    if len(bank) != patch.BANK_END - patch.BANK_A or bank[8:12] != b"KNLT":
        raise core.Stop("This isn't a bank A image (0x24000 bytes with a KNLT header). Nothing was sent.")
    h, crc, total = patch.checks(bank)
    if bank[h - 4:h + 4] != crc.to_bytes(4, "little") + total.to_bytes(4, "little"):
        raise core.Stop("This image fails its CRC or start-up sum, so the bootloader wouldn't run it. Nothing was sent.")
    if bank[restore.SIZE:] != b"\xff" * (len(bank) - restore.SIZE):
        raise core.Stop("This image has data past 0x28800, which the writer doesn't write. Nothing was sent.")
    return bank[:restore.SIZE]


def main(argv: list[str]) -> None:
    trace = open(argv[argv.index("--trace") + 1], "w", buffering=1) if "--trace" in argv else None
    try:
        image = _checked(Path(argv[0]).read_bytes())
        core.official = lambda *a, **k: image
        from u2c_customfw import transport
        restore.run(transport.list_devices, transport.open_channel, app.FOLDER, app.say,
                    write="--write" in argv, trace=trace)
    except core.Stop as e:
        app.say("fail", e)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
