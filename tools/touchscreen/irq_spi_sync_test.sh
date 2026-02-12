#!/usr/bin/env bash
set -euo pipefail

TMPF="$(mktemp)"
FORCE_STATUS_05="${FORCE_STATUS_05:-0}"
cleanup() {
  rm -f "$TMPF"
}
trap cleanup EXIT

# Monitor touch IRQ edges in background.
timeout 16s gpiomon -c gpiochip4 -e both 175 >"$TMPF" &
MONPID=$!

python3 - <<'PY'
import os
import fcntl
import array
import ctypes
import hashlib
import time
import struct

SPI_IOC_WR_MODE = 0x40016B01
SPI_IOC_WR_BITS_PER_WORD = 0x40016B03
SPI_IOC_WR_MAX_SPEED_HZ = 0x40046B04
FORCE_STATUS_05 = os.environ.get("FORCE_STATUS_05", "0") == "1"

def SPI_IOC_MESSAGE(n):
    return 0x40006B00 | (n * 32 << 16)

class X(ctypes.Structure):
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

def xfer(fd, tx, tl=None):
    if tl is None:
        tl = len(tx)
    tx = bytearray(tx) + bytearray(max(0, tl - len(tx)))
    tb = (ctypes.c_uint8 * tl)(*tx[:tl])
    rb = (ctypes.c_uint8 * tl)()
    x = X()
    x.tx_buf = ctypes.addressof(tb)
    x.rx_buf = ctypes.addressof(rb)
    x.len = tl
    x.speed_hz = 1000000
    x.bits_per_word = 8
    fcntl.ioctl(fd, SPI_IOC_MESSAGE(1), x)
    return bytes(rb)

def hw(fd, cmd, payload=b""):
    xfer(fd, [0xF2, cmd] + list(payload))

def ar(fd, addr):
    hw(fd, 0x13, b"\x31")
    hw(fd, 0x0D, b"\x12")
    hw(fd, 0x00, struct.pack("<I", addr))
    hw(fd, 0x0C, b"\x00")
    return struct.unpack("<I", xfer(fd, [0xF3, 0x08, 0x00] + [0] * 4)[3:7])[0]

def aw(fd, addr, val):
    hw(fd, 0x13, b"\x31")
    hw(fd, 0x0D, b"\x12")
    hw(fd, 0x00, struct.pack("<I", addr) + struct.pack("<I", val))

fd = os.open("/dev/spidev0.0", os.O_RDWR)
fcntl.ioctl(fd, SPI_IOC_WR_MODE, array.array("B", [3]))
fcntl.ioctl(fd, SPI_IOC_WR_BITS_PER_WORD, array.array("B", [8]))
fcntl.ioctl(fd, SPI_IOC_WR_MAX_SPEED_HZ, array.array("I", [1000000]))

print(f"status_before=0x{ar(fd,0x900000A8):08x}")
if FORCE_STATUS_05:
    aw(fd, 0x90000048, 0x000000EC)
    time.sleep(0.20)
    print(f"status_after_force=0x{ar(fd,0x900000A8):08x}")

start = time.time()
count = 0
nz_hits = 0
hashes = set()
while time.time() - start < 15.0:
    payload = xfer(fd, [0xF3, 0x30, 0x00] + [0] * 512)[3:]
    n = sum(1 for b in payload if b)
    h = hashlib.sha1(payload).hexdigest()[:10]
    hashes.add(h)
    if n > 0:
        nz_hits += 1
    count += 1
    time.sleep(0.05)

os.close(fd)
print(f"spi_samples={count} spi_nonzero_hits={nz_hits} spi_unique_hash={len(hashes)}")
print("spi_hashes", sorted(hashes))
PY

wait "$MONPID" || true
echo "irq_edges=$(wc -l <"$TMPF")"
echo "irq_first_last:"
{ head -n 3 "$TMPF"; tail -n 3 "$TMPF"; } | sed -n '1,12p'
