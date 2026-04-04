#!/usr/bin/env python3
"""
Add a qmi-chip-id=18 variant=HW_GK3 entry to ath11k board-2.bin
by cloning the existing qmi-chip-id=2,variant=HW_GK3 calibration data.

Usage: python3 patch_board.py <board-2.bin> <output.bin>
"""
import struct
import sys
import shutil

MAGIC = b"QCA-ATH11K-BOARD"
PREFIX = "bus=pci,vendor=17cb,device=1103,subsystem-vendor=17cb,subsystem-device=0108,"
SRC_KEY = PREFIX + "qmi-chip-id=2,qmi-board-id=255,variant=HW_GK3"
NEW_KEY = PREFIX + "qmi-chip-id=18,qmi-board-id=255,variant=HW_GK3"

def align4(n):
    return (n + 3) & ~3

def make_ie(ie_id, data):
    """Build an IE: id(4) + len(4) + data + padding"""
    hdr = struct.pack('<II', ie_id, len(data))
    pad = bytes(align4(len(data)) - len(data))
    return hdr + data + pad

def parse_board(data):
    """Return list of (outer_ie_id, [(inner_id, inner_data), ...], raw_outer_data)"""
    magic_len = align4(len(MAGIC) + 1)
    assert data[:len(MAGIC)] == MAGIC
    pos = magic_len
    entries = []
    while pos + 8 <= len(data):
        ie_id, ie_len = struct.unpack_from('<II', data, pos)
        pos += 8
        ie_data = data[pos:pos + ie_len]
        pos += align4(ie_len)
        # Parse inner IEs
        inner = []
        ipos = 0
        while ipos + 8 <= len(ie_data):
            iid, ilen = struct.unpack_from('<II', ie_data, ipos)
            ipos += 8
            idata = ie_data[ipos:ipos + ilen]
            ipos += align4(ilen)
            inner.append((iid, idata))
        entries.append((ie_id, inner))
    return entries

def find_board_blob(entries, key):
    key_bytes = key.encode('ascii')
    for ie_id, inner in entries:
        if ie_id != 0:
            continue
        name = None
        blob = None
        for iid, idata in inner:
            if iid == 0:
                name = idata
            elif iid == 1:
                blob = idata
        if name == key_bytes and blob is not None:
            return blob
    return None

def build_board_entry(name_str, blob):
    """Build outer BOARD IE from name string and calibration blob."""
    name_ie = make_ie(0, name_str.encode('ascii'))
    data_ie = make_ie(1, blob)
    inner = name_ie + data_ie
    return make_ie(0, inner)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input board-2.bin> <output board-2.bin>")
        sys.exit(1)

    src_path, dst_path = sys.argv[1], sys.argv[2]
    shutil.copy2(src_path, dst_path)

    with open(src_path, 'rb') as f:
        data = f.read()

    entries = parse_board(data)
    blob = find_board_blob(entries, SRC_KEY)
    if blob is None:
        print(f"ERROR: source entry not found: {SRC_KEY}")
        sys.exit(1)

    print(f"Found source entry: {SRC_KEY}")
    print(f"  Blob size: {len(blob)} bytes")

    # Check if destination entry already exists
    existing = find_board_blob(entries, NEW_KEY)
    if existing is not None:
        print(f"Destination entry already exists: {NEW_KEY}")
        sys.exit(0)

    new_ie = build_board_entry(NEW_KEY, blob)
    print(f"Adding new entry: {NEW_KEY}")

    with open(dst_path, 'ab') as f:
        f.write(new_ie)

    print(f"Done. Written to {dst_path}")
    print(f"Add to WiFi DT node: qcom,ath11k-calibration-variant = \"HW_GK3\";")
