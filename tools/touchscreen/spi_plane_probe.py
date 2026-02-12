#!/usr/bin/env python3
"""HX83121A SPI read-plane probe for MateBook E Go.

This script focuses on transport/read-plane health, not touch coordinate output.
It is intended to quickly answer:
1) Is the IC register plane readable (IC ID / status)?
2) Does event read cmd (0x30) return any non-zero payload?
3) Is current behavior stable across lengths and repeated reads?
"""

import argparse
import array
import ctypes
import fcntl
import hashlib
import os
import struct
import sys
import time
from typing import Iterable


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
        self.dev = dev
        self.mode = mode
        self.speed = speed
        self.fd = os.open(dev, os.O_RDWR)
        fcntl.ioctl(self.fd, SPI_IOC_WR_MODE, array.array("B", [mode]))
        fcntl.ioctl(self.fd, SPI_IOC_WR_BITS_PER_WORD, array.array("B", [8]))
        fcntl.ioctl(self.fd, SPI_IOC_WR_MAX_SPEED_HZ, array.array("I", [speed]))

    def close(self) -> None:
        os.close(self.fd)

    def xfer(self, tx: Iterable[int], total_len: int | None = None) -> bytes:
        tx_buf = bytearray(tx)
        if total_len is None:
            total_len = len(tx_buf)
        if total_len < len(tx_buf):
            raise ValueError("total_len smaller than tx size")
        tx_buf.extend(b"\x00" * (total_len - len(tx_buf)))

        n = total_len
        tx_c = (ctypes.c_uint8 * n)(*tx_buf[:n])
        rx_c = (ctypes.c_uint8 * n)()

        x = SpiIocTransfer()
        x.tx_buf = ctypes.addressof(tx_c)
        x.rx_buf = ctypes.addressof(rx_c)
        x.len = n
        x.speed_hz = self.speed
        x.bits_per_word = 8

        fcntl.ioctl(self.fd, spi_ioc_message(1), x)
        return bytes(rx_c)

    def hw(self, cmd: int, payload: bytes = b"") -> None:
        self.xfer([0xF2, cmd] + list(payload))

    def hr(self, cmd: int, n: int) -> bytes:
        out = self.xfer([0xF3, cmd, 0x00] + [0] * n)
        return out[3 : 3 + n]

    def burst_enable(self) -> None:
        self.hw(0x13, b"\x31")
        self.hw(0x0D, b"\x12")

    def ahb_read32(self, addr: int) -> int:
        self.burst_enable()
        self.hw(0x00, struct.pack("<I", addr))
        self.hw(0x0C, b"\x00")
        return struct.unpack("<I", self.hr(0x08, 4))[0]


def fmt_u32(v: int) -> str:
    return f"0x{v:08x}"


def summarize_payload(tag: str, payload: bytes) -> None:
    nz = sum(1 for b in payload if b)
    head = payload[:16].hex()
    tail = payload[-16:].hex() if payload else ""
    h = hashlib.sha1(payload).hexdigest()[:12]
    print(f"{tag}: len={len(payload)} nz={nz} sha1={h} head={head} tail={tail}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", default="/dev/spidev0.0")
    parser.add_argument("--mode", type=int, default=3)
    parser.add_argument("--speed", type=int, default=1_000_000)
    parser.add_argument(
        "--lengths",
        default="64,128,256,339,512,1024,2048,3072,4090",
        help="comma-separated payload lengths for cmd 0x30 and cmd 0x08 probes",
    )
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--sleep-ms", type=int, default=20)
    args = parser.parse_args()

    lengths = [int(x.strip()) for x in args.lengths.split(",") if x.strip()]
    if not lengths:
        print("no valid lengths", file=sys.stderr)
        return 2

    print("=== SPI Plane Probe ===")
    print(f"dev={args.dev} mode={args.mode} speed={args.speed}")
    print(f"lengths={lengths} repeat={args.repeat}")

    bus = SpiBus(args.dev, args.mode, args.speed)
    try:
        # Baseline register health.
        regs = {
            "IC_ID": 0x900000D0,
            "STATUS": 0x900000A8,
            "HANDSHAKE": 0x900000AC,
            "FW_STATUS": 0x9000005C,
            "SRAM0": 0x08000000,
        }
        print("\n[registers]")
        for name, addr in regs.items():
            try:
                print(f"{name:10s} {fmt_u32(bus.ahb_read32(addr))}")
            except OSError as e:
                print(f"{name:10s} read_failed errno={e.errno}")

        # Event/plane command probes.
        print("\n[cmd 0x30 length sweep]")
        for n in lengths:
            try:
                payload = bus.hr(0x30, n)
                summarize_payload(f"cmd30 n={n}", payload)
            except OSError as e:
                print(f"cmd30 n={n}: failed errno={e.errno}")

        # Baseline data register probes for comparison.
        print("\n[cmd 0x08 length sweep]")
        for n in lengths:
            try:
                payload = bus.hr(0x08, n)
                summarize_payload(f"cmd08 n={n}", payload)
            except OSError as e:
                print(f"cmd08 n={n}: failed errno={e.errno}")

        print("\n[cmd 0x30 repeat stability]")
        prev = None
        n = max(lengths)
        for i in range(args.repeat):
            try:
                payload = bus.hr(0x30, n)
            except OSError as e:
                print(f"iter={i}: failed errno={e.errno}")
                break
            diff = "-"
            if prev is not None:
                diff = str(sum(a != b for a, b in zip(prev, payload)))
            nz = sum(1 for b in payload if b)
            print(f"iter={i:02d} len={n} nz={nz} diff={diff}")
            prev = payload
            time.sleep(args.sleep_ms / 1000.0)
    finally:
        bus.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
