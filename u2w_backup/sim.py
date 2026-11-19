# SPDX-License-Identifier: GPL-3.0-or-later
"""A simulated Ultimate 2 Wireless for trying the tool without one (U2W_SIM=<folder>): a 512 KB flash that answers reads
the way 1.09 does, with 8BitDo's firmware if its server can be reached, that restarts into update mode on
81 05 00 51 00 and back on the bootloader's command 7, and records every report it is sent."""
import random
import time

from u2c_customfw.sim import SimBoot
from u2c_customfw.transport import DeviceInfo

from . import core

SIZE = 0x80000
sent = []
state = {"mode": "app", "flash": None}
APP = DeviceInfo(core.VENDOR, 0x310B, core.PAGE, "USB", "8BitDo Ultimate 2 Wireless Controller", None, 0x0114)
BOOT = DeviceInfo(core.VENDOR, 0x3208, 0x8C, "USB", "8BitDo Boot", None, 0x0200)


def image(payload: bytes | None) -> bytes:
    rnd = random.Random(1)
    flash = bytearray(b"\xff" * SIZE)
    flash[0:0x4000] = rnd.randbytes(0x4000)                             # the bootloader
    body = payload or (b"\x0e\x80\x6d\x00" + rnd.randbytes(0x23000) + core.NAME)
    flash[core.BASE:core.BASE + len(body)] = body
    flash[0x7E000:0x7E020] = rnd.randbytes(0x20)                         # the unit's own data
    return bytes(flash)


class Channel:
    def __init__(self, flash: bytes, delay: float = 0.0):
        self.flash, self.delay = flash, delay

    def xfer(self, report: bytes, timeout: float = 0.5, accept=None):
        sent.append(bytes(report))
        if report[:5] == b"\x81\x05\x00\x51\x00":
            state["mode"] = "boot"
            return None
        if report[0:3] != b"\x81\x05\x05":
            return None
        n, addr = int.from_bytes(report[6:8], "little"), int.from_bytes(report[14:18], "little")
        time.sleep(self.delay)
        data = bytes(self.flash[(addr + i) % len(self.flash)] for i in range(min(n, 46)))
        return b"\x02\x05\x00\x00\x05\x00" + report[6:8] + bytes(6) + report[14:18] + data

    def close(self):
        pass


class Boot(SimBoot):
    def __init__(self, flash, fail_after=None):
        super().__init__(flash, fail_after=fail_after, identity=0x6012)
        self.f = flash   # one flash for both modes, so writes show up after the restart

    def xfer(self, r, timeout=0.5, accept=None):
        sent.append(bytes(r))
        if int.from_bytes(r[1:3], "little") == 7:
            state["mode"] = "app"
        return super().xfer(r, timeout, accept)


def _flash():
    if state["flash"] is None:
        state["flash"] = bytearray(image(core.official()))
    return state["flash"]


def list_devices():
    return [APP if state["mode"] == "app" else BOOT]


def open_channel(dev, report_id):
    return Boot(_flash()) if state["mode"] == "boot" else Channel(_flash(), delay=0.0004)
