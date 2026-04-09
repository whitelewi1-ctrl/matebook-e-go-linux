# Linux on Huawei MateBook E Go (GK-W7X)

Linux enablement for the Huawei MateBook E Go on Snapdragon 8cx Gen 3 (sc8280xp), tracking the upstream SC8280XP DSI stack and upstream Himax HX83121A panel driver.

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

- **Panel driver note** (`panel-driver/`) -- placeholder documenting that the repository now uses the upstream HX83121A driver
- **Kernel patches** (`kernel-patches/`) -- 5 local patches on top of the upstream DSI base, covering display timing, bridge, Bluetooth, and EC suspend bugs
- **Device tree** (`device-tree/`) -- DTS source and pre-built DTB for the MateBook E Go
- **Boot configs** (`boot/`) -- reference GRUB and mkinitcpio configurations
- **Touchscreen recovery** (`tools/touchscreen/`) -- systemd service that restores touch after panel init resets the TDDI shared GPIO
- **Touchpad activation** (`tools/touchpad/`) -- systemd service + script for keyboard cover touchpad
- **Bluetooth fix** (`tools/bluetooth/`) -- NVM firmware patcher for WCN6855 BD address
- **Diagnostic tool** (`tools/`) -- userspace tool to read DPU/DSC/INTF/DSI hardware registers

## DSI status

The default path for this repository is now the upstream display stack:

- SC8280XP DSI controller/PHY bindings and DTS nodes are upstream
- the Himax HX83121A panel driver is upstream
- this repository keeps the MateBook E Go board DTS, remaining kernel fixes, and userspace recovery scripts

The local out-of-tree panel implementation and overlay loader have been removed from this repository. `panel-driver/` now exists only as a note that the default path is upstream.

## Bug fixes

Getting this panel working required fixes across multiple kernel subsystems. The SC8280XP DSI base support, byte-clock fix, and HX83121A panel driver are now upstream. This repository still carries the remaining local fixes plus non-display platform fixes.

1. **aux-bridge: handle missing endpoint** -- USB-C PHYs with DP alt-mode but no display output cause probe failure; return 0 on `-ENODEV` instead.

2. **dispcc: remove CLK_SET_RATE_PARENT from byte dividers** -- upstreamed; no longer carried in `kernel-patches/`.

3. **DPU encoder: fix DSC width truncation** -- Integer division truncates `800*8/24` to 266 instead of rounding up to 267, creating a 1-pixel mismatch with the DSI host timing.

4. **DPU INTF: fix widebus data_width truncation** -- `267>>1 = 133` pclks * 6 bytes = 798 bytes/line, but DSC needs 800. `DIV_ROUND_UP` gives 134 * 6 = 804, sufficient.

5. **Panel driver: DSC init ordering** -- fixed in the upstream HX83121A driver; `display_on` must be sent *after* PPS and compression mode are configured, not before.

6. **Panel driver: dual-link init** -- fixed in the upstream HX83121A driver; the full init sequence must be sent on *both* DSI links.

7. **Panel driver: dual-link brightness** -- fixed in the upstream HX83121A driver; dual-link backlight updates must avoid visible half-panel flashing.

## Quick start

### Prerequisites

- Linux kernel source tree with the upstream SC8280XP DSI nodes and upstream `panel-himax-hx83121a` driver
- Cross-compilation toolchain (`aarch64-linux-gnu-gcc`)
- Device tree compiler (`dtc`)

### 1. Apply kernel patches

```bash
cd /path/to/linux
for p in /path/to/matebook-e-go-linux/kernel-patches/0001*.patch \
         /path/to/matebook-e-go-linux/kernel-patches/0003*.patch \
         /path/to/matebook-e-go-linux/kernel-patches/0004*.patch \
         /path/to/matebook-e-go-linux/kernel-patches/0005*.patch \
         /path/to/matebook-e-go-linux/kernel-patches/0006*.patch; do
    patch -p1 < "$p"
done
```

`0002` is intentionally omitted here because the SC8280XP byte-clock fix is already upstream.

### 2. Build kernel with the upstream panel driver

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc)
```

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

### Legacy path

If you are targeting an older kernel without the upstream SC8280XP DSI work or upstream HX83121A driver, use your external backup of the previous out-of-tree implementation. This repository no longer ships that legacy path.

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

### Calibration variant (required)

The WCN6855 firmware's calibration data (`board-2.bin`) includes multiple device variants. By default, it uses `qmi-chip-id=2` (generic SC8280XP), but Huawei MateBook E Go requires `qmi-chip-id=18` (HW_GK3 variant) for proper antenna calibration.

**Two options to fix this:**

#### Option A: Device tree overlay (recommended)

Use the pre-built DTBO to automatically set the calibration variant at boot:

```bash
# Build the overlay
dtc -@ -@ -o device-tree/sc8280xp-huawei-gaokun3-calibration.dtbo \
    -I /usr/src/linux-headers-$(uname -r)/include \
    device-tree/sc8280xp-huawei-gaokun3-calibration.dtso

# Install to firmware directory
sudo cp device-tree/sc8280xp-huawei-gaokun3-calibration.dtbo /lib/firmware/ath11k/
```

Reboot. The overlay will automatically apply `qcom,ath11k-calibration-variant = "HW_GK3"` when the WiFi module loads.

See [docs/WIFI_CALIBRATION_DTBO.md](docs/WIFI_CALIBRATION_DTBO.md) for details.

#### Option B: Manual firmware patching (legacy)

Use the Python script to patch the firmware binary:

```bash
sudo python3 tools/wifi/patch_board.py \
    /lib/firmware/ath11k/WCN6855/hw2.0/board-2.bin \
    /lib/firmware/ath11k/WCN6855/hw2.0/board-2.bin
```

This clones the existing `qmi-chip-id=2` calibration data and appends a `qmi-chip-id=18` entry. Note: this modification is lost when the `ath11k-firmware` package updates.

**After applying either fix**, verify with:

```bash
dmesg | grep -i ath11k | grep -i calibration
iw dev wlan0 info | grep ssid
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

## Waydroid (Android in Linux)

Waydroid runs Android apps in an LXC container on Wayland. The custom kernel includes nftables modules required for container networking.

### Kernel requirements

The following must be enabled (built-in or module):

```
CONFIG_NF_TABLES=y
CONFIG_NF_TABLES_INET=y
CONFIG_NFT_NAT=y
CONFIG_NFT_MASQ=y
CONFIG_NFT_CT=y
CONFIG_NFT_REJECT=m
CONFIG_NETFILTER_XT_TARGET_CHECKSUM=y
```

**Note:** `CONFIG_IP_MULTIPLE_TABLES` (policy routing) causes system freeze when waydroid GUI launches on this platform. Do not enable it.

### Network fix

Android's IpClient does not receive the default gateway via DHCP in the LXC veth environment. A systemd service automatically adds the route:

```bash
cp tools/waydroid/waydroid-net-fix.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable waydroid-net-fix.service
```

### Play Protect certification

The system image ships with `ro.build.tags=test-keys` which fails Play Protect. Fix via overlay:

```bash
# Create overlay build.prop with release-keys
mkdir -p /var/lib/waydroid/overlay/system
cp /var/lib/waydroid/rootfs/system/build.prop /var/lib/waydroid/overlay/system/build.prop
sed -i 's/test-keys/release-keys/g; s/userdebug/user/g' /var/lib/waydroid/overlay/system/build.prop
```

Then register the device at https://www.google.com/android/uncertified/ with the android_id from:

```bash
sudo waydroid shell -- sqlite3 /data/data/com.google.android.gsf/databases/gservices.db \
  "select * from main where name = 'android_id';"
```

## Current status

- Display: working (1600x2560 @ 60/120 Hz, hardware-accelerated via MSM DRM)
- GPU: working (Adreno 690, OpenGL 4.6 + Vulkan 1.3 via freedreno/turnip)
- Video decode: Venus hardware codec enabled (CONFIG_VIDEO_QCOM_VENUS)
- Backlight: working (DSI-controlled, direct dual-link writes)
- Touchscreen: working (TDDI recovery service, 1 MHz I2C)
- Audio: working (WCD938x + WSA8835 via SoundWire + UCM patch)
- Battery: working (huawei-gaokun-ec + huawei-gaokun-battery)
- USB-C: working (UCSI via huawei-gaokun-ec)
- fbcon: working (with `fbcon=rotate:1` for portrait panel)
- Keyboard cover: working (keyboard + touchpad with usbhid quirk + activation service + udev auto-recovery)
- Bluetooth: working (WCN6855 / btqca, with NVM patch + kernel patch)
- WiFi: working (WCN6855 / ath11k_pci)
- Waydroid: working (with network fix service, Play Store certified)
- Camera: not supported (no upstream driver)
- Sensors: not supported (SLPI DSP, no Linux driver)
- Suspend: s2idle works, minor resume glitches

## Acknowledgements

- [right-0903/linux-gaokun](https://github.com/right-0903/linux-gaokun) -- upstream sc8280xp MateBook E Go support
- Qualcomm MSM DRM maintainers
- Linux DRM subsystem

## License

This project is licensed under GPL-2.0-only. See [LICENSE](LICENSE).
