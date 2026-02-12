#!/usr/bin/env python3
"""Probe HX83121A event-plane behavior after mode toggles.

Focus:
1) Sweep raw_out_sel (0x100072EC) and check cmd 0x30 entropy.
2) Force status->0x05 path, then burst-poll cmd 0x30 for transient data.
"""

import argparse
import array
import ctypes
import fcntl
import hashlib
import os
import struct
import time


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


class Bus:
    def __init__(self, dev: str, mode: int, speed: int):
        self.fd = os.open(dev, os.O_RDWR)
        self.speed = speed
        fcntl.ioctl(self.fd, SPI_IOC_WR_MODE, array.array("B", [mode]))
        fcntl.ioctl(self.fd, SPI_IOC_WR_BITS_PER_WORD, array.array("B", [8]))
        fcntl.ioctl(self.fd, SPI_IOC_WR_MAX_SPEED_HZ, array.array("I", [speed]))

    def close(self) -> None:
        os.close(self.fd)

    def xfer(self, tx: bytes | bytearray | list[int], total_len: int | None = None) -> bytes:
        b = bytearray(tx)
        if total_len is None:
            total_len = len(b)
        b.extend(b"\x00" * max(0, total_len - len(b)))
        n = total_len
        tb = (ctypes.c_uint8 * n)(*b[:n])
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


def sha12(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def nz(data: bytes) -> int:
    return sum(1 for x in data if x)


def sample30(bus: Bus, nbytes: int) -> tuple[int, str]:
    p = bus.hr(0x30, nbytes)
    return nz(p), sha12(p)


def dump_state(bus: Bus, tag: str, nbytes: int) -> None:
    n, h = sample30(bus, nbytes)
    print(
        f"{tag}: "
        f"icid=0x{bus.ar(0x900000D0):08x} "
        f"status=0x{bus.ar(0x900000A8):08x} "
        f"hs=0x{bus.ar(0x900000AC):08x} "
        f"fw=0x{bus.ar(0x9000005C):08x} "
        f"raw_out=0x{bus.ar(0x100072EC):08x} "
        f"r0=0x{bus.ar(0x80050000):08x} "
        f"cmd30_nz={n} cmd30_sha={h}"
    )


def enter_safe(bus: Bus) -> None:
    bus.hw(0x31, b"\x27")
    bus.hw(0x32, b"\x95")


def leave_safe(bus: Bus) -> None:
    bus.hw(0x31, b"\x00")
    bus.hw(0x32, b"\x00")


def force_status_05(bus: Bus) -> None:
    bus.aw(0x9000005C, 0x000000A5)
    time.sleep(0.03)
    bus.aw(0x90000048, 0x000000EC)
    time.sleep(0.20)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/spidev0.0")
    ap.add_argument("--mode", type=int, default=3)
    ap.add_argument("--speed", type=int, default=1_000_000)
    ap.add_argument("--nbytes", type=int, default=512)
    ap.add_argument("--poll-count", type=int, default=120)
    ap.add_argument("--poll-interval-ms", type=int, default=20)
    args = ap.parse_args()

    print("=== HX Event Plane Probe ===")
    print(
        f"dev={args.dev} mode={args.mode} speed={args.speed} "
        f"nbytes={args.nbytes} poll_count={args.poll_count}"
    )
    bus = Bus(args.dev, args.mode, args.speed)
    try:
        leave_safe(bus)
        dump_state(bus, "initial", args.nbytes)

        # Sweep candidate raw_out_sel values.
        values = [0x00000000, 0x00000001, 0x00000002, 0x00000003, 0x00000004, 0x00000005, 0x0000000A]
        print("\n[raw_out_sel sweep]")
        for v in values:
            bus.aw(0x100072EC, v)
            time.sleep(0.03)
            n, h = sample30(bus, args.nbytes)
            status = bus.ar(0x900000A8)
            print(f"raw_out_sel=0x{v:08x} status=0x{status:08x} cmd30_nz={n} cmd30_sha={h}")

        print("\n[force status 0x05 then burst poll]")
        force_status_05(bus)
        dump_state(bus, "after_force", args.nbytes)

        seen = set()
        nonzero_hits = 0
        for i in range(args.poll_count):
            p = bus.hr(0x30, args.nbytes)
            n = nz(p)
            h = sha12(p)
            seen.add(h)
            if n > 0:
                nonzero_hits += 1
                print(f"hit iter={i:03d} nz={n} sha={h}")
            time.sleep(args.poll_interval_ms / 1000.0)

        print(
            f"poll_summary: unique_hashes={len(seen)} "
            f"nonzero_hits={nonzero_hits}/{args.poll_count}"
        )
        dump_state(bus, "final", args.nbytes)
        leave_safe(bus)
    finally:
        bus.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
