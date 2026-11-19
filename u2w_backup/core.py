# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the whole flash of an 8BitDo Ultimate 2 Wireless by cable, twice, and make a report that can be shared.

The only report ever sent to the controller is the update channel's read, `81 05 05`. In firmware 1.09 its handler
(0x107f8, reached from 0x10bdc) reads the flash at the address asked, at most 46 bytes, and replies as the Ultimate 2C
does; it changes nothing. The channel's other commands (c1, 3, 4, 7, 8, c2, c4) are never sent.

Every report goes through ReadsOnly, which lets only those reads through and counts them.

The report holds no byte read from the controller. The bootloader (0x0-0x5000) is given by its SHA-256 only. Every other
4 KB sector is described: the same as 8BitDo's firmware 1.09, empty, or data, with where its non-empty bytes are and a
keyed hash whose key stays on this Mac.
"""
import datetime
import hashlib
import hmac
import json
import secrets
import urllib.request
import zipfile
from pathlib import Path

from . import __version__

VENDOR, PAGE = 0x2DC8, 0xFF7A                  # the update channel is the vendor page 0xff7a, as on the Ultimate 2C
PRODUCTS = {0x6012: "D-input", 0x310B: "X-input"}
BASE = 0x5000                                  # where 8BitDo's file loads the firmware; the bootloader is below
SECTOR, CHUNK = 0x1000, 46
SIZES = (0x40000, 0x80000, 0x100000, 0x200000)
SAMPLES = (0x0, 0x800, 0x2000)                 # bootloader addresses: past its end, a flash repeats them
NAME = b"8BitDo Ultimate 2 Wireless"
SERVER, TYPE = "http://dl.8bitdo.com:8080", "94"
DAT_SHA256 = "f754df15d0a3fde833f231c7d9d585490e22adfe9145a8dc1b7c85ab5515cbc1"   # 8BitDo's Ultimate 2 Wireless 1.09
READ = b"\x81\x05\x05"


class Stop(Exception):
    """A reason to stop, in words for the person using the app."""


class ReadsOnly:
    """The only way to the controller: it refuses any report that isn't a 64-byte `81 05 05` read, counts the ones it
    sends and, given a file, writes each of them there in hex."""
    def __init__(self, ch, trace=None):
        self.ch, self.trace, self.sent = ch, trace, 0

    def xfer(self, report: bytes, timeout: float = 0.5, accept=None):
        if len(report) != 64 or report[0:3] != READ:
            raise Stop(f"Refused to send a report that isn't a read: {report[:8].hex(' ')}. Nothing was saved.")
        self.sent += 1
        if self.trace:
            self.trace.write(report.hex(" ") + "\n")
        return self.ch.xfer(report, timeout, accept)

    def close(self) -> None:
        self.ch.close()


def request(addr: int, n: int) -> bytes:
    r = bytearray(64)
    r[0:3] = READ
    r[6:8] = n.to_bytes(2, "little")
    r[14:18] = addr.to_bytes(4, "little")
    return bytes(r)


def read(ch, addr: int, n: int, tries: int = 3) -> bytes | None:
    """One chunk, accepted only if the reply echoes status 0, the read command, the length and the address."""
    def answers(r):
        return (len(r) >= 18 + n and r[0:3] == b"\x02\x05\x00" and r[4] == 0x05
                and int.from_bytes(r[6:8], "little") == n and int.from_bytes(r[14:18], "little") == addr)
    for _ in range(tries):
        r = ch.xfer(request(addr, n), accept=answers)
        if r and answers(r):
            return r[18:18 + n]
    return None


def read_range(ch, start: int, n: int, progress=None) -> bytes:
    out = bytearray()
    for a in range(start, start + n, CHUNK):
        c = read(ch, a, min(CHUNK, start + n - a))
        if c is None:
            raise Stop(f"The controller stopped answering at {a:#x}. Check the cable, unplug the controller, "
                       "plug it back in and try again.")
        out += c
        if progress and len(out) % 0x2000 < CHUNK:
            progress(len(out))
    return bytes(out)


def find(devices):
    """The one Ultimate 2 Wireless connected by cable, or a Stop that says what to do."""
    ours = [d for d in devices if d.vendor == VENDOR and d.product in PRODUCTS and d.usage_page == PAGE
            and "Bluetooth" not in d.transport]
    if len(ours) > 1:
        raise Stop("More than one controller is connected by cable. Leave only the Ultimate 2 Wireless connected.")
    if ours:
        return ours[0]
    if any(d.vendor == VENDOR and "Bluetooth" in d.transport for d in devices):
        raise Stop("The controller is connected by Bluetooth. Turn it off, connect it with a USB cable and try again.")
    if any(d.vendor == VENDOR for d in devices):
        raise Stop("An 8BitDo device is connected, but not an Ultimate 2 Wireless by cable. This app only works with "
                   "that controller.")
    raise Stop("No controller found. Connect the Ultimate 2 Wireless with a USB cable and try again.")


def flash_size(ch) -> int:
    first = {a: read(ch, a, 16) for a in SAMPLES}
    if any(v is None for v in first.values()):
        raise Stop("The controller didn't answer. Unplug it, plug it back in and try again.")
    if all(v == b"\xff" * 16 for v in first.values()):
        raise Stop("The controller's memory reads as empty, so its size can't be measured. Nothing was saved.")
    for size in SIZES:
        if all(read(ch, a + size, 16) == first[a] for a in SAMPLES):
            return size
    raise Stop("The size of the controller's memory couldn't be measured. Nothing was saved.")


def take(ch, size: int, progress) -> bytes:
    """The whole flash, read twice: it counts only if both reads are the same."""
    a = read_range(ch, 0, size, lambda d: progress(d, 2 * size))
    if NAME not in a[BASE:]:   # not in the 2.4 GHz adapter's firmware (1.06), which also loads at 0x5000
        raise Stop("This doesn't look like an Ultimate 2 Wireless. If its 2.4 GHz adapter is plugged in, unplug it, "
                   "connect the controller by cable and try again. Nothing was saved.")
    b = read_range(ch, 0, size, lambda d: progress(size + d, 2 * size))
    if a != b:
        n = sum(a[i:i + SECTOR] != b[i:i + SECTOR] for i in range(0, size, SECTOR))
        raise Stop(f"The two reads of the controller's memory differ in {n} place(s), so nothing was saved. "
                   "Try again, if you can with another cable.")
    return a


def official(opener=urllib.request.urlopen) -> bytes | None:
    """8BitDo's firmware 1.09 (without its 0x1c-byte header), from its update server, or None if it can't be had."""
    try:
        req = urllib.request.Request(SERVER + "/firmware/select", data=b"", method="POST",
                                     headers={"Beta": "1", "Type": TYPE})
        with opener(req, timeout=15) as r:
            entries = json.loads(r.read()).get("list") or []
        for e in entries:
            with opener(SERVER + e["filePathName"], timeout=60) as r:
                dat = r.read()
            if hashlib.sha256(dat).hexdigest() == DAT_SHA256:
                return dat[0x1C:]
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        pass
    return None


def _ranges(block: bytes, base: int) -> list[str]:
    """Where the non-empty (not 0xff) bytes are, as address ranges; gaps under 16 bytes are joined."""
    out, start, last = [], None, None
    for i, v in enumerate(block):
        if v != 0xFF:
            if start is None:
                start = i
            elif i - last > 16:
                out.append((start, last))
                start = i
            last = i
    if start is not None:
        out.append((start, last))
    return [f"{base + s:#x}-{base + e:#x}" for s, e in out]


def sectors(data: bytes, payload: bytes | None, key: bytes) -> list[dict]:
    out = []
    for a in range(0, len(data), SECTOR):
        s = data[a:a + SECTOR]
        row = {"address": f"{a:#x}"}
        if a < BASE:
            row["kind"] = "bootloader (see bootloader_sha256)"
        elif s == b"\xff" * SECTOR:
            row["kind"] = "empty"
        elif payload and a - BASE < len(payload) and s == (payload[a - BASE:a - BASE + SECTOR] + b"\xff" * SECTOR)[:SECTOR]:
            row["kind"] = "8BitDo firmware 1.09"
        elif payload and payload.find(s) >= 0:
            row["kind"] = f"8BitDo firmware 1.09, its bytes from {payload.find(s) + BASE:#x}"
        else:
            row["kind"] = "data"
            row["non_empty_bytes"] = sum(v != 0xFF for v in s)
            row["where"] = _ranges(s, a)[:64]
            row["keyed_hash"] = hmac.new(key, s, hashlib.sha256).hexdigest()[:32]
        out.append(row)
    return out


def report(data: bytes, payload: bytes | None, dev, key: bytes) -> dict:
    bank = data[BASE:BASE + len(payload)] if payload else b""
    return {
        "tool": f"Ultimate 2 Wireless Backup {__version__}",
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "device": {"vendor": f"{dev.vendor:04x}", "product": f"{dev.product:04x}", "version": f"{dev.version:04x}",
                   "name": dev.name, "mode": PRODUCTS[dev.product]},
        "flash_size": f"{len(data):#x}",
        "firmware_version": int.from_bytes(data[BASE + 2:BASE + 4], "little") / 100,
        "same_as_8bitdo_1_09": None if payload is None else bank == payload,
        "bootloader_range": f"0x0-{BASE:#x}",
        "bootloader_sha256": hashlib.sha256(data[:BASE]).hexdigest(),
        "backup_sha256": hashlib.sha256(data).hexdigest(),
        "sectors": sectors(data, payload, key),
    }


README = """This folder holds what Ultimate 2 Wireless Backup made.

- backup-*.bin is the whole memory of your controller. Keep it to yourself: it holds your controller's own data,
  such as its Bluetooth pairings. It's what can put your controller back as it is today.
- report-*.zip is what to send to the developer. It holds report.json and no byte read from your controller: which
  parts of the memory are 8BitDo's firmware, which are empty and where there is data, without the data itself, and
  the SHA-256 of the bootloader and of the whole backup, which you can check with shasum.
- .report-key makes the report's hashes impossible to reverse. Leave it here, so that later reports can be compared.
"""


def save(folder: Path, data: bytes, payload: bytes | None, dev) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "README.txt").write_text(README)
    keyfile = folder / ".report-key"
    if not keyfile.exists():
        keyfile.write_text(secrets.token_hex(32))
    key = bytes.fromhex(keyfile.read_text().strip())
    stamp = f"{datetime.datetime.now():%Y%m%d-%H%M%S}"
    backup = folder / f"backup-{stamp}.bin"
    backup.write_bytes(data)
    if backup.read_bytes() != data:
        raise Stop(f"{backup} didn't read back the same, so the backup can't be trusted. Check the disk and try again.")
    with open(folder / "SHA256SUMS", "a") as f:
        f.write(f"{hashlib.sha256(data).hexdigest()}  {backup.name}\n")
    zpath = folder / f"report-{stamp}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.json", json.dumps(report(data, payload, dev, key), indent=1))
    return backup, zpath
