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
- **Kernel patches** (`kernel-patches/`) -- 4 patches against Linux 6.18.8 fixing clock, DPU, and bridge bugs
- **Device tree** (`device-tree/`) -- DTS source and pre-built DTB for the MateBook E Go
- **Boot configs** (`boot/`) -- reference GRUB and mkinitcpio configurations
- **Diagnostic tool** (`tools/`) -- userspace tool to read DPU/DSC/INTF/DSI hardware registers

## Bug fixes

Getting this panel working required fixing 6 bugs across 5 kernel subsystems. The 4 kernel patches address issues that affect any sc8280xp DSC dual-DSI display; the remaining 2 fixes are in the panel driver itself.

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
clk_ignore_unused pd_ignore_unused arm64.nopauth fbcon=rotate:1
devicetree /boot/sc8280xp-huawei-gaokun3.dtb
```

The `devicetree` line is **required** -- the sc8280xp UEFI firmware does not provide a suitable DTB.

See [docs/BUILDING.md](docs/BUILDING.md), [docs/BOOT_SETUP.md](docs/BOOT_SETUP.md), and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for detailed instructions.

## Current status

- Display: working (1600x2560 @ 60 Hz, hardware-accelerated via MSM DRM)
- Backlight: working (DSI-controlled)
- fbcon: working (with `fbcon=rotate:1` for portrait panel)
- Touchscreen: untested
- GPU acceleration (Adreno): untested beyond basic modesetting

## Acknowledgements

- [right-0903/linux-gaokun](https://github.com/right-0903/linux-gaokun) -- upstream sc8280xp MateBook E Go support
- Qualcomm MSM DRM maintainers
- Linux DRM subsystem

## License

This project is licensed under GPL-2.0-only. See [LICENSE](LICENSE).
