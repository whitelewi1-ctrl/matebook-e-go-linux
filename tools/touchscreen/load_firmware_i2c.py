#!/usr/bin/env python3
"""
HX83121A Firmware Loader via I2C AHB Bridge
============================================
Based on Xiaomi's open-source hxchipset kernel driver (himax_ic_HX83121.c).

This script loads firmware directly into Code SRAM (0x08000000) WITHOUT
depending on Boot ROM. The key insight from the Xiaomi driver is:

1. System reset
2. Enter safe mode (I2C password 0x27/0x95)
3. Reset TCON + ADC (THIS IS THE CRUCIAL STEP WE WERE MISSING!)
4. Write firmware to Code SRAM via AHB bus
5. Write config to Data SRAM
6. Sense-on to start firmware execution

Usage:
  python3 load_firmware_i2c.py /path/to/hx83121a_gaokun_fw.bin

Requirements:
  - i2c-dev module loaded
  - /dev/i2c-4 accessible (i2c_hid_of driver must be unbound first)
  - IC must be in state 0x04 (idle) - typically after cold boot
"""

import os
import sys
import struct
import time
import fcntl
import ctypes

# === I2C Constants ===
I2C_SLAVE_FORCE = 0x0706
I2C_RDWR = 0x0707
I2C_ADDR_AHB = 0x48  # AHB bridge address
I2C_ADDR_HID = 0x4F  # HID interface (for verification)
I2C_BUS = 4           # /dev/i2c-4

# === HX83121A Register Addresses ===
ADDR_IC_STATUS      = 0x900000A8
ADDR_IC_ID          = 0x900000D0
ADDR_SYSTEM_RESET   = 0x90000018
ADDR_FW_ISR_CTRL    = 0x9000005C
ADDR_LEAVE_SAFE     = 0x90000098
ADDR_TCON_RESET     = 0x80020020
ADDR_ADC_RESET      = 0x80020094
ADDR_CODE_SRAM      = 0x08000000
ADDR_FLASH_RELOAD   = 0x10007F00
ADDR_SORTING_MODE   = 0x10007F04
ADDR_RELOAD_DONE    = 0x100072C0
ADDR_N_FRAME        = 0x10007294
ADDR_RAW_OUT_SEL    = 0x800204B4
ADDR_RELOAD_STATUS  = 0x80050000
ADDR_RELOAD_CRC32   = 0x80050018
ADDR_CRC_ADDR       = 0x80050020
ADDR_CRC_CMD        = 0x80050028

# === Constants ===
DATA_SYSTEM_RESET   = 0x00000055
DATA_FW_STOP        = 0x000000A5
DATA_LEAVE_SAFE     = 0x00000053
STATUS_IDLE         = 0x04
STATUS_FW_RUNNING   = 0x05
STATUS_SAFE_MODE    = 0x0C

# === Firmware partition table offset ===
FW_PARTITION_TABLE_OFFSET = 0x20030  # In firmware binary (0x20000 + 0x30 header)

# === I2C Message Structure for I2C_RDWR ===
class i2c_msg(ctypes.Structure):
    _fields_ = [
        ("addr", ctypes.c_ushort),
        ("flags", ctypes.c_ushort),
        ("len", ctypes.c_ushort),
        ("buf", ctypes.POINTER(ctypes.c_ubyte)),
    ]

class i2c_rdwr_ioctl_data(ctypes.Structure):
    _fields_ = [
        ("msgs", ctypes.POINTER(i2c_msg)),
        ("nmsgs", ctypes.c_uint),
    ]


class HX83121A_I2C:
    """I2C communication with HX83121A via AHB bridge."""

    def __init__(self, bus_num=I2C_BUS):
        self.fd = os.open(f"/dev/i2c-{bus_num}", os.O_RDWR)
        self.bus_num = bus_num

    def close(self):
        os.close(self.fd)

    def _i2c_combined(self, addr, wdata, rlen):
        """Combined write+read I2C transaction (repeated start)."""
        wbuf = (ctypes.c_ubyte * len(wdata))(*wdata)
        rbuf = (ctypes.c_ubyte * rlen)()

        msgs = (i2c_msg * 2)()
        msgs[0].addr = addr
        msgs[0].flags = 0  # write
        msgs[0].len = len(wdata)
        msgs[0].buf = ctypes.cast(wbuf, ctypes.POINTER(ctypes.c_ubyte))

        msgs[1].addr = addr
        msgs[1].flags = 1  # read (I2C_M_RD)
        msgs[1].len = rlen
        msgs[1].buf = ctypes.cast(rbuf, ctypes.POINTER(ctypes.c_ubyte))

        data = i2c_rdwr_ioctl_data()
        data.msgs = msgs
        data.nmsgs = 2

        fcntl.ioctl(self.fd, I2C_RDWR, data)
        return bytes(rbuf)

    def _i2c_write(self, addr, data):
        """Simple I2C write transaction."""
        wbuf = (ctypes.c_ubyte * len(data))(*data)
        msgs = (i2c_msg * 1)()
        msgs[0].addr = addr
        msgs[0].flags = 0
        msgs[0].len = len(data)
        msgs[0].buf = ctypes.cast(wbuf, ctypes.POINTER(ctypes.c_ubyte))

        d = i2c_rdwr_ioctl_data()
        d.msgs = msgs
        d.nmsgs = 1

        fcntl.ioctl(self.fd, I2C_RDWR, d)

    # === Direct I2C Register Access (NOT AHB) ===

    def reg_write(self, reg, value):
        """Write a single byte to I2C register (direct, not AHB)."""
        self._i2c_write(I2C_ADDR_AHB, [reg, value])

    def reg_read(self, reg):
        """Read a single byte from I2C register (direct, not AHB)."""
        data = self._i2c_combined(I2C_ADDR_AHB, [reg], 1)
        return data[0]

    # === AHB Bridge Access ===

    def ahb_read(self, addr, length=4):
        """Read from AHB address via I2C bridge (combined write+read)."""
        addr_le = struct.pack("<I", addr)
        wdata = [0x00] + list(addr_le)
        return self._i2c_combined(I2C_ADDR_AHB, wdata, length)

    def ahb_read32(self, addr):
        """Read 32-bit value from AHB address."""
        data = self.ahb_read(addr, 4)
        return struct.unpack("<I", data)[0]

    def ahb_write(self, addr, data_bytes):
        """Write to AHB address via I2C bridge (single transaction)."""
        addr_le = struct.pack("<I", addr)
        wdata = [0x00] + list(addr_le) + list(data_bytes)
        self._i2c_write(I2C_ADDR_AHB, wdata)

    def ahb_write32(self, addr, value):
        """Write 32-bit value to AHB address."""
        self.ahb_write(addr, struct.pack("<I", value))

    # === Burst Mode ===

    def burst_enable(self, enable=True):
        """Enable/disable burst mode (INCR4)."""
        # Register 0x13 = 0x31 (burst continuous mode)
        self.reg_write(0x13, 0x31)
        # Register 0x0D = 0x12 | auto_increment
        if enable:
            self.reg_write(0x0D, 0x13)  # 0x12 | 0x01 = INCR4 + auto-increment
        else:
            self.reg_write(0x0D, 0x12)  # INCR4 without auto-increment

    # === High-Level Operations ===

    def read_ic_id(self):
        """Read IC identification."""
        return self.ahb_read32(ADDR_IC_ID)

    def read_status(self):
        """Read IC status register."""
        return self.ahb_read32(ADDR_IC_STATUS) & 0xFF

    def system_reset(self):
        """Perform IC system reset."""
        self.ahb_write32(ADDR_SYSTEM_RESET, DATA_SYSTEM_RESET)
        time.sleep(0.050)  # 50ms after reset

    def enter_safe_mode(self):
        """Enter safe mode via I2C password."""
        self.reg_write(0x31, 0x27)
        self.reg_write(0x32, 0x95)
        time.sleep(0.010)

    def verify_safe_mode(self):
        """Verify IC is in safe mode (status 0x0C)."""
        for _ in range(10):
            status = self.read_status()
            if status == STATUS_SAFE_MODE:
                return True
            time.sleep(0.010)
        return False

    def reset_tcon(self):
        """Reset TCON controller (required before SRAM write!)."""
        self.ahb_write32(ADDR_TCON_RESET, 0x00000000)
        time.sleep(0.010)

    def reset_adc(self):
        """Reset ADC controller (required before SRAM write!)."""
        self.ahb_write32(ADDR_ADC_RESET, 0x00000000)
        time.sleep(0.005)
        self.ahb_write32(ADDR_ADC_RESET, 0x00000001)
        time.sleep(0.010)

    def write_sram(self, addr, data):
        """Write data to SRAM via AHB bridge.

        For HX83121A, max chunk size is 4096 bytes.
        For I2C, we write 4 bytes at a time with auto-increment.
        """
        total = len(data)
        offset = 0
        chunk_size = 4  # I2C AHB bridge: 4 bytes per transaction

        self.burst_enable(True)

        while offset < total:
            remaining = total - offset
            write_len = min(chunk_size, remaining)

            # Pad to 4 bytes if needed
            chunk = data[offset:offset + write_len]
            if len(chunk) < 4:
                chunk = chunk + b'\x00' * (4 - len(chunk))

            self.ahb_write(addr + offset, chunk)
            offset += write_len

            # Progress indicator every 4KB
            if offset % 4096 == 0:
                pct = offset * 100 // total
                print(f"\r  Writing SRAM: {offset}/{total} ({pct}%)", end="", flush=True)

        print(f"\r  Writing SRAM: {total}/{total} (100%) done")
        self.burst_enable(False)

    def hw_crc_check(self, addr, length):
        """Hardware CRC check using reload engine."""
        # Set CRC check address
        self.ahb_write32(ADDR_CRC_ADDR, addr)

        # Set CRC command: length | 0x0099 (from Xiaomi driver)
        cmd = (length << 8) | 0x0099
        self.ahb_write32(ADDR_CRC_CMD, cmd)

        # Wait for CRC complete (bit0 of reload_status == 0)
        for _ in range(100):
            status = self.ahb_read32(ADDR_RELOAD_STATUS)
            if (status & 1) == 0:
                break
            time.sleep(0.010)

        # Read CRC result
        crc = self.ahb_read32(ADDR_RELOAD_CRC32)
        return crc

    def sense_on(self):
        """Start firmware execution (sense_on sequence)."""
        # Clear raw output select (HX83121A specific)
        self.ahb_write32(ADDR_RAW_OUT_SEL, 0x00000000)

        # Clear sorting mode
        self.ahb_write32(ADDR_SORTING_MODE, 0x00000000)

        # Set N-frame to 1
        self.ahb_write32(ADDR_N_FRAME, 0x00000001)

        # Clear 2nd flash reload flag
        self.ahb_write32(ADDR_RELOAD_DONE, 0x00000000)

        # Enable flash reload
        self.ahb_write32(ADDR_FLASH_RELOAD, 0x00000000)

        # Leave safe mode
        self.ahb_write32(ADDR_LEAVE_SAFE, DATA_LEAVE_SAFE)
        time.sleep(0.100)


def parse_partition_table(fw_data):
    """Parse firmware partition table to get SRAM regions."""
    # Partition table starts at FW offset 0x20030 (after 0x30 header in the 0x20000 area)
    # Actually, in our firmware file, the partition table is at file offset 0x20030
    pt_offset = 0x20030
    partitions = []

    for i in range(20):  # Max 20 entries
        entry_offset = pt_offset + i * 16
        if entry_offset + 16 > len(fw_data):
            break

        sram_addr, size, fw_off, flags = struct.unpack_from("<IIII", fw_data, entry_offset)

        if size == 0 or sram_addr == 0xFFFFFFFF:
            break

        partitions.append({
            'sram_addr': sram_addr,
            'size': size,
            'fw_offset': fw_off,
            'flags': flags,
            'type': 'code' if sram_addr < 0x10000000 else 'config'
        })

    return partitions


def load_firmware(dev, fw_data):
    """Main firmware loading sequence."""

    print("=== HX83121A Firmware Loader ===")
    print(f"Firmware size: {len(fw_data)} bytes")

    # Step 0: Verify IC communication
    print("\n[0] Verifying I2C communication...")
    try:
        ic_id = dev.read_ic_id()
        print(f"  IC ID: 0x{ic_id:08X}", end="")
        if ic_id == 0x83121A00:
            print(" ✓")
        else:
            print(f" ✗ (expected 0x83121A00)")
            return False
    except Exception as e:
        print(f"  I2C communication failed: {e}")
        print("  Make sure i2c_hid_of is unbound and IC is accessible")
        return False

    status = dev.read_status()
    print(f"  IC Status: 0x{status:02X}", end="")
    if status == STATUS_IDLE:
        print(" (idle - no firmware)")
    elif status == STATUS_FW_RUNNING:
        print(" (FW running)")
    elif status == STATUS_SAFE_MODE:
        print(" (safe mode)")
    else:
        print(f" (unknown)")

    # Step 1: System Reset
    print("\n[1] System reset...")
    dev.system_reset()
    time.sleep(0.100)

    # Re-enable burst after reset
    dev.burst_enable(False)

    status = dev.read_status()
    print(f"  Status after reset: 0x{status:02X}")

    # Step 2: Enter Safe Mode
    print("\n[2] Entering safe mode...")
    dev.enter_safe_mode()

    if dev.verify_safe_mode():
        print("  Safe mode confirmed ✓ (status = 0x0C)")
    else:
        status = dev.read_status()
        print(f"  WARNING: Status = 0x{status:02X} (expected 0x0C)")
        print("  Continuing anyway...")

    # Step 3: Reset TCON and ADC (CRUCIAL!)
    print("\n[3] Resetting TCON + ADC (unlocks Code SRAM write)...")
    dev.reset_tcon()
    print("  TCON reset ✓")
    dev.reset_adc()
    print("  ADC reset ✓")

    # Step 4: Test Code SRAM writability
    print("\n[4] Testing Code SRAM write...")
    test_addr = 0x08000400  # First code partition start
    try:
        # Write test pattern
        dev.ahb_write32(test_addr, 0xDEADBEEF)
        time.sleep(0.005)

        # Read back
        val = dev.ahb_read32(test_addr)
        if val == 0xDEADBEEF:
            print(f"  Code SRAM write SUCCESS! ✓ (0x{test_addr:08X} = 0x{val:08X})")
        elif val == 0x78787878:
            print(f"  Code SRAM still inaccessible (0x78787878) ✗")
            print("  TCON/ADC reset did not unlock SRAM write")
            return False
        else:
            print(f"  Unexpected read back: 0x{val:08X}")
            print("  Trying to continue...")
    except Exception as e:
        print(f"  SRAM test failed: {e}")
        return False

    # Step 5: Parse partition table and write firmware
    print("\n[5] Parsing firmware partition table...")
    partitions = parse_partition_table(fw_data)

    code_parts = [p for p in partitions if p['type'] == 'code']
    config_parts = [p for p in partitions if p['type'] == 'config']

    print(f"  Found {len(code_parts)} code partitions, {len(config_parts)} config partitions")
    for i, p in enumerate(partitions):
        dest = 0x08000000 + p['sram_addr'] if p['type'] == 'code' else p['sram_addr']
        print(f"  [{i}] {p['type']:6s}: sram=0x{p['sram_addr']:08X} -> dest=0x{dest:08X} size={p['size']} fw_off=0x{p['fw_offset']:06X}")

    # Step 6: Write code partitions to Code SRAM
    print("\n[6] Writing code partitions to Code SRAM...")
    total_code_bytes = sum(p['size'] for p in code_parts)
    print(f"  Total code size: {total_code_bytes} bytes")

    for i, p in enumerate(code_parts):
        dest_addr = 0x08000000 + p['sram_addr']
        data = fw_data[p['fw_offset']:p['fw_offset'] + p['size']]
        print(f"  Code partition {i}: 0x{dest_addr:08X} ({p['size']} bytes)")
        dev.write_sram(dest_addr, data)

    # Step 7: Write config partitions to Data SRAM
    print("\n[7] Writing config partitions to Data SRAM...")
    for i, p in enumerate(config_parts):
        dest_addr = p['sram_addr']  # Config addresses are direct SRAM addresses
        data = fw_data[p['fw_offset']:p['fw_offset'] + p['size']]
        print(f"  Config partition {i}: 0x{dest_addr:08X} ({p['size']} bytes)")
        dev.write_sram(dest_addr, data)

    # Step 8: Verify Code SRAM (read back first few bytes)
    print("\n[8] Verifying Code SRAM...")
    verify_addr = 0x08000400
    expected = fw_data[0x400:0x408]
    actual = dev.ahb_read(verify_addr, 4) + dev.ahb_read(verify_addr + 4, 4)

    if actual[:len(expected)] == expected:
        print(f"  Verification at 0x{verify_addr:08X}: MATCH ✓")
    else:
        print(f"  Verification MISMATCH:")
        print(f"    Expected: {expected.hex()}")
        print(f"    Actual:   {actual.hex()}")

    # Step 9: HW CRC check (optional)
    print("\n[9] Hardware CRC check...")
    try:
        crc = dev.hw_crc_check(0x08000000, total_code_bytes)
        print(f"  HW CRC result: 0x{crc:08X}", end="")
        if crc == 0:
            print(" ✓ (CRC=0, correct)")
        else:
            print(" (non-zero, may still be OK)")
    except Exception as e:
        print(f"  CRC check failed: {e} (continuing)")

    # Step 10: Sense On (start firmware)
    print("\n[10] Starting firmware (sense_on)...")
    dev.sense_on()

    # Wait for firmware to start
    time.sleep(0.500)

    # Check status
    try:
        status = dev.read_status()
        print(f"  IC Status: 0x{status:02X}", end="")
        if status == STATUS_FW_RUNNING:
            print(" ✓ FIRMWARE RUNNING!")
            return True
        else:
            print(f" ✗ (expected 0x05)")

            # Try reading reload_done
            reload = dev.ahb_read32(ADDR_RELOAD_DONE)
            print(f"  Reload done: 0x{reload:08X}")
            return False
    except Exception as e:
        print(f"  Status read failed: {e}")
        print("  (This might be normal if IC transitioned state)")
        return False


def unbind_i2c_hid():
    """Unbind i2c_hid_of driver to release I2C bus."""
    unbind_path = "/sys/bus/i2c/drivers/i2c_hid_of/unbind"
    try:
        with open(unbind_path, 'w') as f:
            f.write("4-004f")
        print("  i2c_hid_of unbound ✓")
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"  Unbind failed (may already be unbound): {e}")
        return True  # Continue anyway


def bind_i2c_hid():
    """Rebind i2c_hid_of driver to pick up the touchscreen."""
    bind_path = "/sys/bus/i2c/drivers/i2c_hid_of/bind"
    try:
        with open(bind_path, 'w') as f:
            f.write("4-004f")
        print("  i2c_hid_of rebound ✓")
        return True
    except Exception as e:
        print(f"  Rebind failed: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <firmware.bin>")
        print(f"  firmware.bin: HX83121A firmware file (261,120 bytes)")
        sys.exit(1)

    fw_path = sys.argv[1]

    # Load firmware
    print(f"Loading firmware from {fw_path}...")
    with open(fw_path, 'rb') as f:
        fw_data = f.read()

    if len(fw_data) != 261120:
        print(f"WARNING: Firmware size {len(fw_data)} != expected 261,120 bytes")

    # Verify firmware header
    header = fw_data[0:10].decode('ascii', errors='replace')
    if header.startswith('HX83121'):
        print(f"  Header: {header.rstrip(chr(0))} ✓")
    else:
        print(f"  WARNING: Unexpected header: {fw_data[0:10].hex()}")

    # Unbind i2c_hid_of
    print("\nUnbinding i2c_hid_of driver...")
    unbind_i2c_hid()

    # Open I2C
    dev = HX83121A_I2C(I2C_BUS)

    try:
        success = load_firmware(dev, fw_data)
    finally:
        dev.close()

    if success:
        print("\n" + "=" * 50)
        print("FIRMWARE LOADED SUCCESSFULLY!")
        print("=" * 50)
        print("\nRebinding i2c_hid_of driver...")
        time.sleep(1.0)
        bind_i2c_hid()
        print("\nTouchscreen should now be available!")
        print("Check: cat /proc/bus/input/devices | grep -A5 4858")
    else:
        print("\n" + "=" * 50)
        print("FIRMWARE LOADING FAILED")
        print("=" * 50)
        print("\nRebinding i2c_hid_of...")
        bind_i2c_hid()
        sys.exit(1)


if __name__ == "__main__":
    main()
