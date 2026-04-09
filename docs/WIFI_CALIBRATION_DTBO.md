# WiFi Calibration DTBO for Huawei MateBook E Go

## Problem

The WCN6855 WiFi firmware (`board-2.bin`) includes calibration data for different
device variants. By default, it uses `qmi-chip-id=2` (generic SC8280XP),
but Huawei MateBook E Go requires `qmi-chip-id=18` (HW_GK3 variant) for proper
antenna calibration.

## Solution

This device tree overlay dynamically overrides the calibration variant at boot time
without modifying the firmware binary.

## Building

```bash
dtc -@ -@ -o sc8280xp-huawei-gaokun3-calibration.dtbo \
    -I /usr/src/linux-headers-6.18/include \
    sc8280xp-huawei-gaokun3-calibration.dtso
```

Note: Using `/usr/src/linux-headers-` ensures compatibility with the running kernel.

## Installation

### Option A: Copy to firmware directory (recommended)

```bash
sudo cp sc8280xp-huawei-gaokun3-calibration.dtbo /lib/firmware/ath11k/
```

The firmware loader will automatically load this overlay when the WiFi module
initializes.

### Option B: Bootloader integration

Add to your GRUB config:

```grub
devicetree /boot/sc8280xp-huawei-gaokun3.dtb,/boot/sc8280xp-huawei-gaokun3-calibration.dtbo
```

Multiple DTBOs are comma-separated in the `devicetree` parameter.

### Option C: UEFI Shell

If using UEFI shell:

```bash
# Copy to ESP partition
devicetree-copy-py /boot/esp/ESP/EFI/BOOT/sc8280xp-huawei-gaokun3-calibration.dtbo
```

## Verification

After reboot, check dmesg:

```bash
dmesg | grep ath11k
dmesg | grep "calibration"
```

You should see log entries indicating the HW_GK3 variant is being used.

## Comparison with Python Script

| Feature | Python Script | DTBO Overlay |
|---------|--------------|--------------|
| Installation | Manual (post-install) | Automatic (boot) |
| Persistence | Lost on firmware update | Survives firmware updates |
| Cleanliness | Binary file modification | Pure device tree |
| Upstream compatibility | Low (custom binary) | High (standard mechanism) |

## Troubleshooting

If calibration doesn't apply:

1. Check overlay is loaded:
   ```bash
   ls -l /sys/firmware/devicetree/base/
   ```

2. Verify WiFi module reads the property:
   ```bash
   grep -r "calibration" /sys/class/net/wlan* 2>/dev/null
   ```

3. Check for conflicts:
   ```bash
   dmesg | grep "overlay" | grep "error"
   ```

## Copyright

Copyright (c) 2026 Lewis White
SPDX-License-Identifier: GPL-2.0-or-later
