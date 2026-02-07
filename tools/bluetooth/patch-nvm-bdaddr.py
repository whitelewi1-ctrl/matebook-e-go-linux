#!/usr/bin/env python3
"""Patch BD address in QCA WCN6855 NVM firmware file.

The NVM firmware for the WCN6855 on the Huawei MateBook E Go ships with a
partially invalid BD address (ad:5a:00:00:00:00). This script generates a
stable, locally-administered BD address from the device serial number and
patches it into the NVM file at the correct TLV offset.

Usage:
    sudo python3 patch-nvm-bdaddr.py

The script will:
1. Read the device serial from /sys/class/dmi/id/product_serial
2. Generate a unique BD address via MD5 hash (locally-administered, unicast)
3. Back up the original NVM file (.orig)
4. Patch the 6-byte BD address at TLV tag_id=2 (offset 92)
"""

import hashlib
import os
import shutil
import struct
import sys

NVM_FILE = "/lib/firmware/qca/hpnv21g.b9f"
BD_ADDR_TAG_ID = 2
TLV_HEADER_SIZE = 4  # __le32 type_len


def parse_nvm_find_bdaddr(data):
    """Parse QCA NVM TLV format and return offset of BD address data."""
    if len(data) < TLV_HEADER_SIZE + 12:
        return None

    type_len = struct.unpack_from('<I', data, 0)[0]
    tlv_type = type_len & 0xFF
    tlv_length = type_len >> 8

    offset = TLV_HEADER_SIZE

    # Type 4 = enclosing header, skip to inner
    if tlv_type == 4:
        if len(data) < offset + TLV_HEADER_SIZE:
            return None
        type_len = struct.unpack_from('<I', data, offset)[0]
        tlv_length = type_len >> 8
        offset += TLV_HEADER_SIZE

    # Parse tlv_type_nvm entries: tag_id(2) + tag_len(2) + reserve1(4) + reserve2(4) + data
    idx = 0
    while idx < tlv_length:
        entry_offset = offset + idx
        if entry_offset + 12 > len(data):
            break
        tag_id = struct.unpack_from('<H', data, entry_offset)[0]
        tag_len = struct.unpack_from('<H', data, entry_offset + 2)[0]
        data_offset = entry_offset + 12

        if data_offset + tag_len > len(data):
            break

        if tag_id == BD_ADDR_TAG_ID and tag_len == 6:
            return data_offset

        idx += 12 + tag_len

    return None


def generate_bdaddr(serial):
    """Generate a locally-administered unicast BD address from a serial string."""
    h = hashlib.md5(serial.encode()).hexdigest()[:12]
    first = (int(h[0:2], 16) | 0x02) & 0xFE  # locally-administered, unicast
    return bytes([first]) + bytes.fromhex(h[2:12])


def main():
    if os.geteuid() != 0:
        print("Error: must run as root", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(NVM_FILE):
        print(f"Error: {NVM_FILE} not found", file=sys.stderr)
        sys.exit(1)

    # Read device serial
    try:
        serial = open("/sys/class/dmi/id/product_serial").read().strip()
    except (FileNotFoundError, PermissionError):
        serial = "gaokun3"
    print(f"Device serial: {serial}")

    # Generate address
    addr_bytes = generate_bdaddr(serial)
    addr_str = ":".join(f"{b:02x}" for b in addr_bytes)
    print(f"Generated BD address: {addr_str}")

    # Read NVM file
    data = bytearray(open(NVM_FILE, "rb").read())
    bd_offset = parse_nvm_find_bdaddr(data)
    if bd_offset is None:
        print("Error: could not find BD address tag in NVM file", file=sys.stderr)
        sys.exit(1)

    old_addr = ":".join(f"{b:02x}" for b in data[bd_offset:bd_offset + 6])
    print(f"Current BD address at offset {bd_offset}: {old_addr}")

    if data[bd_offset:bd_offset + 6] == addr_bytes:
        print("Already patched, nothing to do.")
        sys.exit(0)

    # Backup original
    backup = NVM_FILE + ".orig"
    if not os.path.exists(backup):
        shutil.copy2(NVM_FILE, backup)
        print(f"Backed up original to {backup}")

    # Patch
    data[bd_offset:bd_offset + 6] = addr_bytes
    open(NVM_FILE, "wb").write(data)

    # Verify
    verify = open(NVM_FILE, "rb").read()
    verify_addr = ":".join(f"{b:02x}" for b in verify[bd_offset:bd_offset + 6])
    print(f"Patched BD address: {verify_addr}")
    print("Done. Reboot to apply.")


if __name__ == "__main__":
    main()
