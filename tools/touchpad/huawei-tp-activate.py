#!/usr/bin/env python3
"""Activate Huawei MateBook E Go keyboard cover touchpad.

The 12d1:10b8 keyboard cover requires:
1. SW_TABLET_MODE=0 injection - the gpio-keys switch incorrectly reports
   tablet mode ON, causing libinput to disable the touchpad
2. USB port reset - re-initializes device firmware
3. Driver rebind - triggers hid-multitouch's mt_set_modes() to set
   Input Mode=3 (Touchpad) on the freshly reset device
"""
import fcntl
import os
import struct
import subprocess
import sys
import time

VENDOR = 0x12d1
PRODUCT = 0x10b8
USBDEVFS_RESET = 21780

EV_SW = 5
EV_SYN = 0
SW_TABLET_MODE = 1
SYN_REPORT = 0

def inject_tablet_mode_off():
    """Inject SW_TABLET_MODE=0 to disable tablet mode detection."""
    # Find gpio-keys event device
    for entry in os.listdir("/sys/class/input"):
        if not entry.startswith("event"):
            continue
        try:
            name = open(f"/sys/class/input/{entry}/device/name").read().strip()
            if name == "gpio-keys":
                devpath = f"/dev/input/{entry}"
                now = time.time()
                sec = int(now)
                usec = int((now - sec) * 1000000)
                fd = os.open(devpath, os.O_WRONLY)
                os.write(fd, struct.pack("llHHi", sec, usec, EV_SW, SW_TABLET_MODE, 0))
                os.write(fd, struct.pack("llHHi", sec, usec, EV_SYN, SYN_REPORT, 0))
                os.close(fd)
                return True
        except (FileNotFoundError, ValueError, OSError):
            continue
    return False

def find_device():
    """Find USB sysfs name and devpath for 12d1:10b8."""
    for entry in os.listdir("/sys/bus/usb/devices"):
        if ':' in entry or entry.startswith('.'):
            continue
        try:
            vid = open(f"/sys/bus/usb/devices/{entry}/idVendor").read().strip()
            pid = open(f"/sys/bus/usb/devices/{entry}/idProduct").read().strip()
            if int(vid, 16) == VENDOR and int(pid, 16) == PRODUCT:
                busnum = int(open(f"/sys/bus/usb/devices/{entry}/busnum").read().strip())
                devnum = int(open(f"/sys/bus/usb/devices/{entry}/devnum").read().strip())
                return entry, f"/dev/bus/usb/{busnum:03d}/{devnum:03d}"
        except (FileNotFoundError, ValueError):
            continue
    return None, None

# Step 0: Fix tablet mode switch (must be done regardless of keyboard presence)
inject_tablet_mode_off()

sysname, devpath = find_device()
if not sysname:
    sys.exit(0)

# Step 1: USB port reset
try:
    fd = os.open(devpath, os.O_WRONLY)
    fcntl.ioctl(fd, USBDEVFS_RESET, 0)
    os.close(fd)
except Exception:
    sys.exit(1)

# Step 2: Wait for firmware to initialize
time.sleep(2)

# Step 3: Unbind/bind for fresh hid-multitouch probe
subprocess.run(["sh", "-c",
    f"echo {sysname} > /sys/bus/usb/drivers/usb/unbind"],
    check=False)
time.sleep(1)
subprocess.run(["sh", "-c",
    f"echo {sysname} > /sys/bus/usb/drivers/usb/bind"],
    check=False)

# Step 4: Wait for devices to settle
time.sleep(1)
subprocess.run(["udevadm", "settle", "--timeout=5"], check=False)

# Step 5: Re-inject tablet mode off (bind creates fresh gpio state view)
inject_tablet_mode_off()
