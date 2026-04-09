# Building the Kernel

## Prerequisites

- Host: x86_64 or aarch64 Linux system
- Cross-compiler: `aarch64-linux-gnu-gcc` (if building on x86_64)
- Kernel source: a recent Linux tree that already includes the upstream SC8280XP DSI support and upstream `panel-himax-hx83121a`
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

## Recommended build

### 1. Download and extract kernel

```bash
wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.8.tar.xz
tar xf linux-6.18.8.tar.xz
cd linux-6.18.8
```

### 2. Apply repository patches

```bash
for p in \
    /path/to/matebook-e-go-linux/kernel-patches/0001-*.patch \
    /path/to/matebook-e-go-linux/kernel-patches/0003-*.patch \
    /path/to/matebook-e-go-linux/kernel-patches/0004-*.patch \
    /path/to/matebook-e-go-linux/kernel-patches/0005-*.patch \
    /path/to/matebook-e-go-linux/kernel-patches/0006-*.patch; do
    patch -p1 < "$p"
done
```

`0002-clk-qcom-dispcc-sc8280xp-remove-CLK_SET_RATE_PARENT.patch` was removed from this repository because that byte-clock fix is already upstream.

### 3. Configure kernel

```bash
# Start from defconfig
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- defconfig

# Display
scripts/config --enable CONFIG_DRM_MSM
scripts/config --enable CONFIG_DRM_MSM_DSI
scripts/config --module CONFIG_DRM_PANEL_HIMAX_HX83121A
scripts/config --enable CONFIG_QCOM_DISPCC_SC8280XP

# Waydroid networking (IP forwarding is required for container NAT)
scripts/config --enable CONFIG_IP_FORWARD

make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
```

Or use `menuconfig` for interactive configuration:

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- menuconfig
```

### 4. Build

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc)
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- dtbs
```

### 5. Install

Copy to the target device's NVMe:

```bash
# Kernel image
cp arch/arm64/boot/Image /mnt/nvme/boot/vmlinuz-linux-6.18

# Modules
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
     INSTALL_MOD_PATH=/mnt/nvme modules_install
```

## Legacy path

The repository no longer ships the previous out-of-tree panel driver or overlay loader. For pre-upstream kernels, use an external backup of that legacy implementation.

## Building the device tree

If you modify the DTS:

```bash
cd linux
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
