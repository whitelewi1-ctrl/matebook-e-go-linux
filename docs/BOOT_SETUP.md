# Boot Setup Guide

## Overview

The Huawei MateBook E Go boots via UEFI with GRUB as the bootloader. A custom device tree blob (DTB) must be loaded by GRUB because the firmware's built-in DTB does not include the panel node.

## Filesystem layout

| Partition | Mount point | Filesystem | Notes |
|-----------|-------------|------------|-------|
| NVMe EFI System Partition | `/boot/efi` | FAT32 | GRUB EFI binary |
| NVMe root | `/` | btrfs | Kernel, initramfs, DTB |

btrfs is recommended over ext4 due to better resilience against frequent hard reboots during development.

## GRUB configuration

Place this in your GRUB config (e.g., `/boot/grub/grub.cfg` or `/etc/grub.d/40_custom`):

```
menuentry "Linux 6.18 (MSM DRM)" {
    linux /boot/vmlinuz-linux-6.18 root=UUID=<your-root-uuid> rootfstype=btrfs rw \
        clk_ignore_unused pd_ignore_unused arm64.nopauth \
        iommu.passthrough=0 iommu.strict=0 \
        pcie_aspm.policy=powersupersave efi=noruntime \
        fbcon=rotate:1 loglevel=7
    initrd /boot/initramfs-linux-6.18.img
    devicetree /boot/sc8280xp-huawei-gaokun3.dtb
}
```

### Required boot parameters

| Parameter | Purpose |
|-----------|---------|
| `clk_ignore_unused` | Prevent the kernel from disabling clocks that appear unused but are needed by display hardware |
| `pd_ignore_unused` | Same for power domains |
| `arm64.nopauth` | Disable pointer authentication (firmware may not support it) |
| `fbcon=rotate:1` | Rotate the fbcon framebuffer 90 degrees for the portrait-orientation panel |
| `devicetree /boot/sc8280xp-huawei-gaokun3.dtb` | **Critical**: load the custom DTB with panel node |

### Optional parameters

| Parameter | Purpose |
|-----------|---------|
| `iommu.passthrough=0 iommu.strict=0` | IOMMU lazy mode for better performance |
| `pcie_aspm.policy=powersupersave` | Aggressive PCIe power saving |
| `efi=noruntime` | Disable EFI runtime services (may improve stability) |
| `loglevel=7` | Verbose kernel logging (useful for debugging, reduce to 3 for normal use) |

## initramfs configuration (mkinitcpio)

For Arch Linux with mkinitcpio, ensure these modules are included:

```
MODULES=(btrfs nvme nvme-core phy-qcom-qmp-pcie phy-qcom-qmp-combo phy-qcom-qmp-usb phy-qcom-snps-femto-v2 simpledrm drm drm_kms_helper drm_shmem_helper usb-storage uas typec mmc_core mmc_block)
```

Include the Adreno firmware:

```
FILES=(/lib/firmware/qcom/a660_sqe.fw)
```

Standard hooks:

```
HOOKS=(base udev autodetect modconf block filesystems fsck)
```

Rebuild initramfs after any changes:

```bash
mkinitcpio -p linux-6.18
```

## Installation checklist

1. Copy kernel image to `/boot/vmlinuz-linux-6.18`
2. Copy DTB to `/boot/sc8280xp-huawei-gaokun3.dtb`
3. Copy modules to `/lib/modules/<version>/`
4. Generate initramfs
5. Update GRUB config with `devicetree` line
6. Reboot

## Dual-boot with stable kernel

The reference `boot/grub.cfg` includes two entries:
- **6.18 (MSM DRM)**: Full GPU-accelerated display via MSM DRM
- **6.14 (simpledrm)**: Fallback with simpledrm (no GPU acceleration, but stable)

Keep the stable kernel entry as a fallback during development.
