# Linux on Huawei MateBook E Go (GK-W7X)

Native GPU-accelerated display driver for the Huawei MateBook E Go, the first working implementation of MSM DRM with the Himax HX83121A dual-DSI panel on the Snapdragon 8cx Gen 3 (sc8280xp) platform.

## Hardware

| Component | Details |
|-----------|---------|
| Device | Huawei MateBook E Go (GK-W7X) |
| SoC | Qualcomm Snapdragon 8cx Gen 3 (sc8280xp) |
| Panel | Himax HX83121A, 12.35" 1600x2560 @ 60 Hz |
| Display link | Dual DSI with DSC 1.1 (8 bpp, slice 800x20) |
| Backlight | DSI register 0x51 |

## What's included

- **Panel driver** (`panel-driver/`) -- standalone kernel module for the HX83121A panel with DTB overlay loader
- **Kernel patches** (`kernel-patches/`) -- 6 patches against Linux 6.18.8 fixing clock, DPU, bridge, Bluetooth, and EC suspend bugs
- **Device tree** (`device-tree/`) -- DTS source and pre-built DTB for the MateBook E Go
- **Boot configs** (`boot/`) -- reference GRUB and mkinitcpio configurations
- **Touchpad activation** (`tools/touchpad/`) -- systemd service + script for keyboard cover touchpad
- **Bluetooth fix** (`tools/bluetooth/`) -- NVM firmware patcher for WCN6855 BD address
- **Diagnostic tool** (`tools/`) -- userspace tool to read DPU/DSC/INTF/DSI hardware registers

## Bug fixes

Getting this panel working required fixing 6 bugs across 5 kernel subsystems. The 4 kernel patches address issues that affect any sc8280xp DSC dual-DSI display; the remaining 2 fixes are in the panel driver itself. An additional patch fixes EC suspend/resume.

1. **aux-bridge: handle missing endpoint** -- USB-C PHYs with DP alt-mode but no display output cause probe failure; return 0 on `-ENODEV` instead.

2. **dispcc: remove CLK_SET_RATE_PARENT from byte dividers** -- `clk_set_rate()` on `byte_intf_clk` propagates through the divider and reconfigures the parent PLL, halving the byte clock from 85.4 MHz to 42.7 MHz.

3. **DPU encoder: fix DSC width truncation** -- Integer division truncates `800*8/24` to 266 instead of rounding up to 267, creating a 1-pixel mismatch with the DSI host timing.

4. **DPU INTF: fix widebus data_width truncation** -- `267>>1 = 133` pclks * 6 bytes = 798 bytes/line, but DSC needs 800. `DIV_ROUND_UP` gives 134 * 6 = 804, sufficient.

5. **Panel driver: DSC init ordering** -- `display_on` must be sent *after* PPS and compression mode are configured, not before.

6. **Panel driver: dual-link init** -- The HX83121A requires the full init sequence (vendor commands + sleep out + PPS + compression + display_on) to be sent on *both* DSI links.

## Quick start

### Prerequisites

- Linux kernel 6.18+ source tree (aarch64)
- Cross-compilation toolchain (`aarch64-linux-gnu-gcc`)
- Device tree compiler (`dtc`)

### 1. Apply kernel patches

```bash
cd /path/to/linux-6.18.8
for p in /path/to/matebook-e-go-linux/kernel-patches/000*.patch; do
    patch -p1 < "$p"
done
```

### 2. Build kernel with the panel driver

Copy the panel driver into the kernel tree:

```bash
cp panel-driver/panel-himax-hx83121a.c drivers/gpu/drm/panel/
```

Add to `drivers/gpu/drm/panel/Kconfig` and `Makefile`, then build:

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc)
```

Or build as an out-of-tree module using the provided Makefile in `panel-driver/`.

### 3. Install DTB and configure GRUB

```bash
cp device-tree/sc8280xp-huawei-gaokun3.dtb /boot/
```

Key GRUB parameters (see `boot/grub.cfg` for full reference):

```
clk_ignore_unused pd_ignore_unused arm64.nopauth fbcon=rotate:1 usbhid.quirks=0x12d1:0x10b8:0x20000000 consoleblank=0
devicetree /boot/sc8280xp-huawei-gaokun3.dtb
```

The `devicetree` line is **required** -- the sc8280xp UEFI firmware does not provide a suitable DTB.

The `usbhid.quirks` parameter enables the keyboard cover touchpad (see Keyboard Cover section below).

See [docs/BUILDING.md](docs/BUILDING.md), [docs/BOOT_SETUP.md](docs/BOOT_SETUP.md), and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for detailed instructions.

## Keyboard cover touchpad

The MateBook E Go keyboard cover (USB 12d1:10b8) requires two fixes for full touchpad support:

### 1. USB HID quirk

Add to your kernel command line:

```
usbhid.quirks=0x12d1:0x10b8:0x20000000
```

This sets `HID_QUIRK_NO_INIT_REPORTS` (BIT(29) = 0x20000000). Without it, the HID subsystem sends `GET_REPORT` requests that return empty responses, blocking the control queue and preventing `hid-multitouch` from setting Input Mode=3 (Touchpad).

### 2. Activation service

The touchpad firmware requires a USB port reset after enumeration, followed by a driver rebind so `hid-multitouch` can successfully configure the device. The script also injects `SW_TABLET_MODE=0` to work around the `gpio-keys` tablet-mode switch reporting an inverted state (the DTS fix changes the GPIO polarity to `GPIO_ACTIVE_LOW`, but the software injection provides a fallback).

```bash
cp tools/touchpad/huawei-tp-activate.py /usr/local/bin/
cp tools/touchpad/huawei-touchpad.service /etc/systemd/system/
chmod +x /usr/local/bin/huawei-tp-activate.py
systemctl daemon-reload
systemctl enable huawei-touchpad.service
```

The service runs before the display manager at `sysinit.target`, ensuring the touchpad is ready when GNOME/Wayland starts.

## Bluetooth (WCN6855 / btqca)

The WCN6855 Bluetooth controller ships with a partially invalid BD address (`ad:5a:00:00:00:00`) in its NVM firmware. Additionally, the kernel's `btqca` driver incorrectly marks the controller as `HCI_UNCONFIGURED` even when a valid address is present in the NVM. Two fixes are required:

### 1. Kernel patch

Apply `kernel-patches/0005-bluetooth-btqca-fix-USE_BDADDR_PROPERTY-for-valid-NVM-address.patch`. This changes `qca_check_bdaddr()` to only set `HCI_QUIRK_USE_BDADDR_PROPERTY` when the BD address is all-zero (`BDADDR_ANY`), rather than whenever it matches the NVM file. Without this patch, the controller stays in `HCI_UNCONFIGURED` state and `btmgmt info` shows 0 controllers.

### 2. NVM firmware patch

Patch the NVM firmware with a valid BD address derived from the device serial number:

```bash
sudo python3 tools/bluetooth/patch-nvm-bdaddr.py
```

This generates a stable, locally-administered unicast address from the MD5 hash of the device serial (`/sys/class/dmi/id/product_serial`) and writes it to the BD address tag (tag_id=2) in `/lib/firmware/qca/hpnv21g.b9f`. A backup of the original file is saved as `.orig`.

Reboot after applying both fixes. Verify with:

```bash
btmgmt info          # Should show hci0 as Primary controller
bluetoothctl show     # Should show Powered: yes
```

## WiFi (WCN6855 / ath11k)

WiFi works via `ath11k_pci`. If `CONFIG_PCI_PWRCTRL=y` is built into the kernel, delete the duplicate module to avoid a symbol conflict:

```bash
rm /usr/lib/modules/$(uname -r)/kernel/drivers/pci/pwrctrl/pci-pwrctrl-core.ko
depmod -a
```

Auto-load WiFi modules by creating `/etc/modules-load.d/wifi.conf`:

```
pci-pwrctrl-pwrseq
ath11k_pci
```

## Current status

- Display: working (1600x2560 @ 60 Hz, hardware-accelerated via MSM DRM)
- Backlight: working (DSI-controlled)
- fbcon: working (with `fbcon=rotate:1` for portrait panel)
- Keyboard cover: working (keyboard + touchpad with usbhid quirk + activation service)
- Bluetooth: working (WCN6855 / btqca, with NVM patch + kernel patch)
- WiFi: working (WCN6855 / ath11k_pci)
- Touchscreen: not working (I2C read-only; firmware download blocked, see [docs/TOUCHSCREEN.md](docs/TOUCHSCREEN.md))
- GPU acceleration (Adreno): untested beyond basic modesetting

## Acknowledgements

- [right-0903/linux-gaokun](https://github.com/right-0903/linux-gaokun) -- upstream sc8280xp MateBook E Go support
- Qualcomm MSM DRM maintainers
- Linux DRM subsystem

## License

This project is licensed under GPL-2.0-only. See [LICENSE](LICENSE).
