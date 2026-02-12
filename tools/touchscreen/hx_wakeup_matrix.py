#!/usr/bin/env python3
"""HX83121A wakeup sequence matrix runner.

Run controlled write sequences and measure whether the touch event plane
(cmd 0x30) leaves the all-zero state.
"""

import argparse
import array
import ctypes
import fcntl
import hashlib
import os
import struct
import time
from dataclasses import dataclass


SPI_IOC_WR_MODE = 0x40016B01
SPI_IOC_WR_BITS_PER_WORD = 0x40016B03
SPI_IOC_WR_MAX_SPEED_HZ = 0x40046B04


def spi_ioc_message(n: int) -> int:
    return 0x40006B00 | (n * 32 << 16)


class SpiIocTransfer(ctypes.Structure):
    _fields_ = [
        ("tx_buf", ctypes.c_uint64),
        ("rx_buf", ctypes.c_uint64),
        ("len", ctypes.c_uint32),
        ("speed_hz", ctypes.c_uint32),
        ("delay_usecs", ctypes.c_uint16),
        ("bits_per_word", ctypes.c_uint8),
        ("cs_change", ctypes.c_uint8),
        ("tx_nbits", ctypes.c_uint8),
        ("rx_nbits", ctypes.c_uint8),
        ("word_delay_usecs", ctypes.c_uint8),
        ("pad", ctypes.c_uint8),
    ]


class SpiBus:
    def __init__(self, dev: str, mode: int, speed: int):
        self.fd = os.open(dev, os.O_RDWR)
        self.speed = speed
        fcntl.ioctl(self.fd, SPI_IOC_WR_MODE, array.array("B", [mode]))
        fcntl.ioctl(self.fd, SPI_IOC_WR_BITS_PER_WORD, array.array("B", [8]))
        fcntl.ioctl(self.fd, SPI_IOC_WR_MAX_SPEED_HZ, array.array("I", [speed]))

    def close(self) -> None:
        os.close(self.fd)

    def xfer(self, tx: bytes | bytearray | list[int], total_len: int | None = None) -> bytes:
        tx_buf = bytearray(tx)
        if total_len is None:
            total_len = len(tx_buf)
        tx_buf.extend(b"\x00" * max(0, total_len - len(tx_buf)))
        n = total_len
        tb = (ctypes.c_uint8 * n)(*tx_buf[:n])
        rb = (ctypes.c_uint8 * n)()
        x = SpiIocTransfer()
        x.tx_buf = ctypes.addressof(tb)
        x.rx_buf = ctypes.addressof(rb)
        x.len = n
        x.speed_hz = self.speed
        x.bits_per_word = 8
        fcntl.ioctl(self.fd, spi_ioc_message(1), x)
        return bytes(rb)

    def hw(self, cmd: int, payload: bytes = b"") -> None:
        self.xfer([0xF2, cmd] + list(payload))

    def hr(self, cmd: int, n: int) -> bytes:
        out = self.xfer([0xF3, cmd, 0x00] + [0] * n)
        return out[3 : 3 + n]

    def burst(self) -> None:
        self.hw(0x13, b"\x31")
        self.hw(0x0D, b"\x12")

    def ar(self, addr: int) -> int:
        self.burst()
        self.hw(0x00, struct.pack("<I", addr))
        self.hw(0x0C, b"\x00")
        return struct.unpack("<I", self.hr(0x08, 4))[0]

    def aw(self, addr: int, value: int) -> None:
        self.burst()
        self.hw(0x00, struct.pack("<I", addr) + struct.pack("<I", value))


@dataclass
class Snapshot:
    icid: int
    status: int
    handshake: int
    fw_status: int
    sram0: int
    reload0: int
    flash_reload: int
    reload2: int
    sorting: int
    cmd30_nz: int
    cmd30_sha: str


def snap(bus: SpiBus, frame_len: int) -> Snapshot:
    p = bus.hr(0x30, frame_len)
    return Snapshot(
        icid=bus.ar(0x900000D0),
        status=bus.ar(0x900000A8),
        handshake=bus.ar(0x900000AC),
        fw_status=bus.ar(0x9000005C),
        sram0=bus.ar(0x08000000),
        reload0=bus.ar(0x80050000),
        flash_reload=bus.ar(0x10007F00),
        reload2=bus.ar(0x100072C0),
        sorting=bus.ar(0x10007F04),
        cmd30_nz=sum(1 for b in p if b),
        cmd30_sha=hashlib.sha1(p).hexdigest()[:12],
    )


def fmt(v: int) -> str:
    return f"0x{v:08x}"


def print_snap(tag: str, s: Snapshot) -> None:
    print(
        f"{tag}: "
        f"icid={fmt(s.icid)} status={fmt(s.status)} hs={fmt(s.handshake)} "
        f"fw={fmt(s.fw_status)} sram0={fmt(s.sram0)} r0={fmt(s.reload0)} "
        f"fr={fmt(s.flash_reload)} r2={fmt(s.reload2)} sort={fmt(s.sorting)} "
        f"cmd30_nz={s.cmd30_nz} cmd30_sha={s.cmd30_sha}"
    )


def safe_enter(bus: SpiBus) -> None:
    bus.hw(0x31, b"\x27")
    bus.hw(0x32, b"\x95")


def safe_exit(bus: SpiBus) -> None:
    bus.hw(0x31, b"\x00")
    bus.hw(0x32, b"\x00")


def run_scenario(bus: SpiBus, name: str) -> None:
    if name == "baseline":
        return
    if name == "system_reset":
        bus.aw(0x90000018, 0x00000055)
        time.sleep(0.15)
        return
    if name == "fw_stop":
        bus.aw(0x9000005C, 0x000000A5)
        time.sleep(0.05)
        return
    if name == "enable_reload":
        bus.aw(0x10007F00, 0x00000000)
        time.sleep(0.02)
        return
    if name == "activ_relod":
        bus.aw(0x90000048, 0x000000EC)
        time.sleep(0.20)
        return
    if name == "safe_reload_combo":
        bus.aw(0x9000005C, 0x000000A5)
        time.sleep(0.03)
        safe_enter(bus)
        time.sleep(0.05)
        bus.aw(0x10007F00, 0x00000000)
        bus.aw(0x100072C0, 0x00000000)
        bus.aw(0x90000048, 0x000000EC)
        time.sleep(0.30)
        safe_exit(bus)
        time.sleep(0.12)
        return
    if name == "system_reset_then_activ":
        bus.aw(0x90000018, 0x00000055)
        time.sleep(0.20)
        bus.aw(0x90000048, 0x000000EC)
        time.sleep(0.25)
        return
    raise ValueError(f"unknown scenario: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", default="/dev/spidev0.0")
    parser.add_argument("--mode", type=int, default=3)
    parser.add_argument("--speed", type=int, default=1_000_000)
    parser.add_argument("--frame-len", type=int, default=512)
    parser.add_argument(
        "--scenarios",
        default="baseline,fw_stop,enable_reload,activ_relod,safe_reload_combo,system_reset,system_reset_then_activ",
        help="comma-separated scenario list",
    )
    args = parser.parse_args()

    scenarios = [x.strip() for x in args.scenarios.split(",") if x.strip()]
    print("=== HX Wakeup Matrix ===")
    print(f"dev={args.dev} mode={args.mode} speed={args.speed} frame_len={args.frame_len}")
    print(f"scenarios={scenarios}")

    bus = SpiBus(args.dev, args.mode, args.speed)
    try:
        safe_exit(bus)
        for sc in scenarios:
            print(f"\n[{sc}]")
            before = snap(bus, args.frame_len)
            print_snap("before", before)
            run_scenario(bus, sc)
            after = snap(bus, args.frame_len)
            print_snap("after ", after)
        safe_exit(bus)
    finally:
        bus.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
