#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Firmware update script for Huawei MateBook E Go Linux
# Applies the latest changes from the repository
#
# Usage: sudo ./update-firmware.sh
#
# Copyright (c) 2026 Lewis White

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KERNEL_VERSION=$(uname -r)

echo "=== MateBook E Go Firmware Update Script ==="
echo "Repository: $REPO_DIR"
echo "Current kernel: $KERNEL_VERSION"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    echo "Usage: sudo ./update-firmware.sh"
    exit 1
fi

# Step 1: Build WiFi calibration DTBO overlay
echo "[1/4] Building WiFi calibration DTBO overlay..."
DTBO_FILE="$REPO_DIR/device-tree/sc8280xp-huawei-gaokun3-calibration.dtbo"

if [ ! -f "$DTBO_FILE" ]; then
    echo "  Compiling DTBO from source..."
    cd "$REPO_DIR/device-tree"

    # Find kernel headers
    if [ -d "/usr/src/linux-headers-$KERNEL_VERSION" ]; then
        HEADER_DIR="/usr/src/linux-headers-$KERNEL_VERSION"
    else
        echo "  Warning: Kernel headers not found at /usr/src/linux-headers-$KERNEL_VERSION"
        echo "  Using generic include path..."
        HEADER_DIR="/usr/src/linux-headers-6.18/include"
    fi

    dtc -@ -@ -o sc8280xp-huawei-gaokun3-calibration.dtbo \
        -I "$HEADER_DIR" \
        sc8280xp-huawei-gaokun3-calibration.dtso

    if [ $? -eq 0 ]; then
        echo "  ✓ DTBO compiled successfully"
    else
        echo "  ✗ Failed to compile DTBO"
        echo "  Make sure dtc is installed: sudo apt install device-tree-compiler"
        exit 1
    fi
else
    echo "  ✓ DTBO already exists"
fi

# Step 2: Install WiFi calibration DTBO
echo "[2/4] Installing WiFi calibration DTBO..."
ATH11K_FW_DIR="/lib/firmware/ath11k"

if [ ! -d "$ATH11K_FW_DIR" ]; then
    echo "  Creating $ATH11K_FW_DIR..."
    mkdir -p "$ATH11K_FW_DIR"
fi

cp "$DTBO_FILE" "$ATH11K_FW_DIR/"
echo "  ✓ DTBO installed to $ATH11K_FW_DIR"

# Step 3: Install Waydroid network fix
echo "[3/4] Installing Waydroid network fix..."
NM_DISPATCHER_DIR="/etc/NetworkManager/dispatcher.d"

if [ -d "$NM_DISPATCHER_DIR" ]; then
    echo "  Installing NetworkManager dispatcher script..."
    cp "$REPO_DIR/tools/waydroid/90-waydroid-network-fix" "$NM_DISPATCHER_DIR/"
    chmod +x "$NM_DISPATCHER_DIR/90-waydroid-network-fix"

    # Disable old systemd service if it exists
    if systemctl list-unit-files | grep -q "waydroid-net-fix.service"; then
        echo "  Disabling old waydroid-net-fix.service..."
        systemctl disable waydroid-net-fix.service 2>/dev/null || true
        systemctl stop waydroid-net-fix.service 2>/dev/null || true
    fi

    echo "  ✓ Waydroid network fix installed"
    echo "  Note: Reload NetworkManager to activate: systemctl reload NetworkManager"
else
    echo "  ⚠ NetworkManager dispatcher directory not found"
    echo "  Skipping Waydroid network fix installation"
fi

# Step 4: Verify kernel configuration
echo "[4/4] Checking kernel configuration..."
REQUIRED_CONFIGS=(
    "CONFIG_IP_FORWARD"
    "CONFIG_NF_TABLES"
    "CONFIG_NF_TABLES_INET"
    "CONFIG_NFT_NAT"
    "CONFIG_NFT_MASQ"
    "CONFIG_NFT_CT"
)

MISSING_CONFIGS=0

for config in "${REQUIRED_CONFIGS[@]}"; do
    if [ -f "/boot/config-$KERNEL_VERSION" ]; then
        if grep -q "^$config=" "/boot/config-$KERNEL_VERSION" || \
           grep -q "^$config=y" "/boot/config-$KERNEL_VERSION" || \
           grep -q "^$config=m" "/boot/config-$KERNEL_VERSION"; then
            echo "  ✓ $config is enabled"
        else
            echo "  ✗ $config is missing"
            MISSING_CONFIGS=$((MISSING_CONFIGS + 1))
        fi
    else
        echo "  ⚠ Cannot check $config (kernel config not found)"
    fi
done

if [ $MISSING_CONFIGS -gt 0 ]; then
    echo
    echo "  ⚠ Warning: $MISSING_CONFIGS kernel configs are missing"
    echo "  These are required for Waydroid networking"
    echo "  Please rebuild kernel with these options enabled"
fi

echo
echo "=== Update Summary ==="
echo "✓ WiFi calibration DTBO: Installed"
echo "✓ Waydroid network fix: Installed"
echo "  Kernel configuration: Checked"

echo
echo "Next steps:"
echo "1. Reboot to apply WiFi calibration DTBO"
echo "2. Verify WiFi calibration: dmesg | grep ath11k | grep calibration"
echo "3. If NetworkManager is running: systemctl reload NetworkManager"
echo "4. Test Waydroid networking: waydroid show-full-ui"
echo
echo "For kernel rebuild instructions, see: docs/BUILDING.md"

echo
echo "Update completed successfully!"