# Linux on Huawei MateBook E Go (GK-W7X)

Native GPU-accelerated display driver for the Huawei MateBook E Go, the first working implementation of MSM DRM with the Himax HX83121A dual-DSI panel on the Snapdragon 8cx Gen 3 (sc8280xp) platform.

## Hardware

| Component | Details |
|-----------|---------|
| Device | Huawei MateBook E Go (GK-W7X) |
| SoC | Qualcomm Snapdragon 8cx Gen 3 (sc8280xp) |
| Panel | Himax HX83121A, 12.35" 1600x2560 @ 60/120 Hz |
| Display link | Dual DSI with DSC 1.1 (8 bpp, slice 800x20) |
| Backlight | DSI register 0x51 |
| Touchscreen | Himax HX83121A TDDI, I2C 0x48/0x4F, SPI6 |
| Audio | WCD938x codec + WSA8835 v2 speakers (SoundWire) |

## What's included

- **Panel driver** (`panel-driver/`) -- standalone kernel module for the HX83121A panel with DTB overlay loader
- **Kernel patches** (`kernel-patches/`) -- 6 patches against Linux 6.18.8 fixing clock, DPU, bridge, Bluetooth, and EC suspend bugs
- **Device tree** (`device-tree/`) -- DTS source and pre-built DTB for the MateBook E Go
- **Boot configs** (`boot/`) -- reference GRUB and mkinitcpio configurations
- **Touchscreen recovery** (`tools/touchscreen/`) -- systemd service that restores touch after panel init resets the TDDI shared GPIO
- **Touchpad activation** (`tools/touchpad/`) -- systemd service + script for keyboard cover touchpad
- **Bluetooth fix** (`tools/bluetooth/`) -- NVM firmware patcher for WCN6855 BD address
- **Diagnostic tool** (`tools/`) -- userspace tool to read DPU/DSC/INTF/DSI hardware registers

## Bug fixes

Getting this panel working required fixing 7 bugs across 5 kernel subsystems. The 4 kernel patches address issues that affect any sc8280xp DSC dual-DSI display; the remaining 3 fixes are in the panel driver itself. An additional patch fixes EC suspend/resume.

1. **aux-bridge: handle missing endpoint** -- USB-C PHYs with DP alt-mode but no display output cause probe failure; return 0 on `-ENODEV` instead.

2. **dispcc: remove CLK_SET_RATE_PARENT from byte dividers** -- `clk_set_rate()` on `byte_intf_clk` propagates through the divider and reconfigures the parent PLL, halving the byte clock from 85.4 MHz to 42.7 MHz.

3. **DPU encoder: fix DSC width truncation** -- Integer division truncates `800*8/24` to 266 instead of rounding up to 267, creating a 1-pixel mismatch with the DSI host timing.

4. **DPU INTF: fix widebus data_width truncation** -- `267>>1 = 133` pclks * 6 bytes = 798 bytes/line, but DSC needs 800. `DIV_ROUND_UP` gives 134 * 6 = 804, sufficient.

5. **Panel driver: DSC init ordering** -- `display_on` must be sent *after* PPS and compression mode are configured, not before.

6. **Panel driver: dual-link init** -- The HX83121A requires the full init sequence (vendor commands + sleep out + PPS + compression + display_on) to be sent on *both* DSI links.

7. **Panel driver: dual-link brightness** -- Setting brightness via DCS 0x51 on two DSI links sequentially can cause a brief right-half flash. Direct writes are used (no ramping) as the flash is only visible during rapid continuous adjustment.

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

## Touchscreen

The HX83121A is a TDDI (Touch and Display Driver Integration) IC -- it shares GPIO 99 (reset) with the display. The panel init sequence resets this GPIO, killing the touch firmware. The UEFI `TouchPanelInit` only runs on Windows boot paths, so Linux boots without touch.

The recovery service (`tools/touchscreen/`) uses a two-round I2C rebind sequence to restore touch after every boot (~7s):

1. Set GPIO 174 HIGH (I2C mode), reset GPIO 99, wait for Boot ROM
2. Bind `i2c_hid` (fails, but wakes the HID interface at 0x4F)
3. Set GPIO 174 LOW (OE=1), rebind `i2c_hid` (succeeds)

```bash
cp tools/touchscreen/hx83121a-touch-recovery /usr/local/bin/
cp tools/touchscreen/hx83121a-touch-recovery.service /etc/systemd/system/
chmod +x /usr/local/bin/hx83121a-touch-recovery
systemctl daemon-reload
systemctl enable hx83121a-touch-recovery.service
```

I2C touch speed can be increased to 1 MHz (from 400 kHz default) by patching the DTB:

```bash
fdtput -t i device-tree/sc8280xp-huawei-gaokun3.dtb /soc@0/geniqup@9c0000/i2c@990000 clock-frequency 1000000
```

## Audio

Audio uses the Qualcomm AudioReach stack: ADSP firmware → SoundWire → WCD938x (headphones) + WSA8835 (speakers).

The stock ALSA UCM configuration only recognizes the Lenovo X13s. To enable audio on the MateBook E Go, patch the UCM config to match the Huawei DMI:

```bash
# /usr/share/alsa/ucm2/conf.d/sc8280xp/sc8280xp.conf
# Add a HUAWEI match block that reuses the X13s profile (same codec hardware)
```

See `tools/audio/sc8280xp.conf` for the patched UCM configuration.

Required firmware (from Huawei Windows partition or backup):
- `/lib/firmware/qcom/sc8280xp/HUAWEI/gaokun3/qcadsp8280.mbn`
- `/lib/firmware/qcom/sc8280xp/SC8280XP-HUAWEI-MATEBOOKEGO-tplg.bin` → symlink to `HUAWEI/gaokun3/audioreach-tplg.bin`

Module loading config:
```bash
# /etc/modules-load.d/audio.conf
lpasscc_sc8280xp
snd-soc-sc8280xp

# /etc/modprobe.d/audio-deps.conf
softdep pinctrl_sc8280xp_lpass_lpi pre: lpasscc_sc8280xp
```

## 120 Hz display

The panel supports 120 Hz via DSC mode (init register E2=0x00). The driver includes both 60 Hz and 120 Hz modes, selectable in GNOME Settings → Displays.

- 120 Hz: native vtotal (2736)
- 60 Hz: doubled vtotal (5472), same link speed

## Battery and EC

The Huawei EC driver (`huawei-gaokun-ec`) and battery driver (`huawei-gaokun-battery`) provide battery status, charging control, and smart charge support. These are built as modules from the kernel source tree (requires `CONFIG_EC_HUAWEI_GAOKUN=m` and `CONFIG_BATTERY_HUAWEI_GAOKUN=m`).

## USB-C (UCSI)

The UCSI driver (`ucsi_huawei_gaokun`) enables USB Type-C functionality including power delivery negotiation. Requires the EC driver. Build with `CONFIG_UCSI_HUAWEI_GAOKUN=m`.

## Current status

- Display: working (1600x2560 @ 60/120 Hz, hardware-accelerated via MSM DRM)
- GPU: working (Adreno 690, OpenGL 4.6 + Vulkan 1.3 via freedreno/turnip)
- Backlight: working (DSI-controlled, direct dual-link writes)
- Touchscreen: working (TDDI recovery service, 1 MHz I2C)
- Audio: working (WCD938x + WSA8835 via SoundWire + UCM patch)
- Battery: working (huawei-gaokun-ec + huawei-gaokun-battery)
- USB-C: working (UCSI via huawei-gaokun-ec)
- fbcon: working (with `fbcon=rotate:1` for portrait panel)
- Keyboard cover: working (keyboard + touchpad with usbhid quirk + activation service)
- Bluetooth: working (WCN6855 / btqca, with NVM patch + kernel patch)
- WiFi: working (WCN6855 / ath11k_pci)
- Camera: not supported (no upstream driver)
- Suspend: s2idle configured, untested

## Acknowledgements

- [right-0903/linux-gaokun](https://github.com/right-0903/linux-gaokun) -- upstream sc8280xp MateBook E Go support
- Qualcomm MSM DRM maintainers
- Linux DRM subsystem

## License

This project is licensed under GPL-2.0-only. See [LICENSE](LICENSE).
