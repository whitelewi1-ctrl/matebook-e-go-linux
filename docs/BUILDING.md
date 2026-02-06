# Building the Kernel and Panel Driver

## Prerequisites

- Host: x86_64 or aarch64 Linux system
- Cross-compiler: `aarch64-linux-gnu-gcc` (if building on x86_64)
- Kernel source: Linux 6.18.8 from kernel.org
- Device tree compiler: `dtc`
- Tools: `make`, `patch`, `bc`, `flex`, `bison`, `libssl-dev`

On Debian/Ubuntu:

```bash
sudo apt install gcc-aarch64-linux-gnu build-essential bc flex bison libssl-dev device-tree-compiler
```

On Arch Linux:

```bash
sudo pacman -S aarch64-linux-gnu-gcc make bc flex bison openssl dtc
```

## Option A: In-tree build (recommended)

### 1. Download and extract kernel

```bash
wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.8.tar.xz
tar xf linux-6.18.8.tar.xz
cd linux-6.18.8
```

### 2. Apply kernel patches

```bash
for p in /path/to/matebook-e-go-linux/kernel-patches/000*.patch; do
    patch -p1 < "$p"
done
```

### 3. Copy panel driver into kernel tree

```bash
cp /path/to/matebook-e-go-linux/panel-driver/panel-himax-hx83121a.c \
   drivers/gpu/drm/panel/
```

Add to `drivers/gpu/drm/panel/Kconfig`:

```kconfig
config DRM_PANEL_HIMAX_HX83121A
	tristate "Himax HX83121A DSI panel"
	depends on OF
	depends on DRM_MIPI_DSI
	depends on BACKLIGHT_CLASS_DEVICE
	help
	  Say Y or M if you have a Himax HX83121A based DSI panel.
	  Used in the Huawei MateBook E Go (GK-W7X).
```

Add to `drivers/gpu/drm/panel/Makefile`:

```makefile
obj-$(CONFIG_DRM_PANEL_HIMAX_HX83121A) += panel-himax-hx83121a.o
```

### 4. Configure kernel

```bash
# Start from defconfig
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- defconfig

# Enable required options
scripts/config --enable CONFIG_DRM_MSM
scripts/config --enable CONFIG_DRM_MSM_DSI
scripts/config --module CONFIG_DRM_PANEL_HIMAX_HX83121A
scripts/config --enable CONFIG_OF_OVERLAY
scripts/config --enable CONFIG_QCOM_DISPCC_SC8280XP

make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
```

Or use `menuconfig` for interactive configuration:

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- menuconfig
```

### 5. Build

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc)
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- dtbs
```

### 6. Install

Copy to the target device's NVMe:

```bash
# Kernel image
cp arch/arm64/boot/Image /mnt/nvme/boot/vmlinuz-linux-6.18

# Modules
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
     INSTALL_MOD_PATH=/mnt/nvme modules_install
```

## Option B: Out-of-tree module build

If you already have a running kernel and just need to build the panel driver:

### 1. Apply kernel patches first

The 4 kernel patches must be applied to the kernel source tree, and the kernel rebuilt.

### 2. Build modules

```bash
cd /path/to/matebook-e-go-linux/panel-driver

# Edit Makefile: set KDIR to your kernel source path
# KDIR := /path/to/linux-6.18.8

make
```

This produces:
- `panel-himax-hx83121a.ko` -- the panel driver
- `gaokun-overlay-loader.ko` -- DTB overlay loader (applies panel node at runtime)

### 3. Install modules

```bash
cp panel-himax-hx83121a.ko /mnt/nvme/lib/modules/$(uname -r)/extra/
cp gaokun-overlay-loader.ko /mnt/nvme/lib/modules/$(uname -r)/extra/
depmod -a
```

## Building the device tree

If you modify the DTS:

```bash
cd linux-6.18.8
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- qcom/sc8280xp-huawei-gaokun3.dtb
cp arch/arm64/boot/dts/qcom/sc8280xp-huawei-gaokun3.dtb /mnt/nvme/boot/
```

Or standalone:

```bash
dtc -I dts -O dtb -o sc8280xp-huawei-gaokun3.dtb sc8280xp-huawei-gaokun3.dts
```

## Building the diagnostic tool

```bash
cd /path/to/matebook-e-go-linux/tools
aarch64-linux-gnu-gcc -O2 -o read_dsc_regs read_dsc_regs.c
```

Run on the target device (as root):

```bash
./read_dsc_regs
```
