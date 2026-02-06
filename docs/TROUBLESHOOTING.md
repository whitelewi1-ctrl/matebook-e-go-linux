# Troubleshooting

## Display does not light up

### Check 1: Is the custom DTB loaded?

The most common cause is GRUB not loading the custom device tree. Verify your GRUB config has:

```
devicetree /boot/sc8280xp-huawei-gaokun3.dtb
```

Without this, the firmware's built-in DTB is used, which lacks the panel node.

### Check 2: Verify the panel driver loaded

```bash
dmesg | grep -i hx83121a
dmesg | grep -i "panel"
```

You should see the init sequence messages. If not, the panel driver module may not be loaded or the DTB panel node is missing.

### Check 3: Check for DSI errors

```bash
dmesg | grep -i "dsi"
```

Look for:
- `accum_err` values (should be 0 after init)
- Timeout errors
- PHY/PLL lock failures

### Check 4: Check DPU/CRTC status

```bash
dmesg | grep -E "crtc|dpu|intf"
```

Look for:
- `crtc: active=1 enable=1` -- CRTC is configured
- Mode string should show `1600x2560`

### Check 5: Verify clock rates

```bash
dmesg | grep -i "clk\|pll\|vco\|byte"
```

Expected values:
- VCO: 683.6 MHz
- byte_clk: 85.4 MHz
- pixel_clk: 113.9 MHz
- byte_intf_clk: 42.7 MHz

If byte_clk shows 42.7 MHz (half of expected), the CLK_SET_RATE_PARENT patch (0002) is not applied.

## Black screen with backlight on

If the backlight is on but the screen is black:

1. **DSC mismatch**: Check `dmesg` for width/timing values. The DPU and DSI must agree on compressed width (267 for this panel).
2. **Init sequence sent to only one DSI link**: Both links must receive the full init. Check `dmesg` for init messages on both DSI0 and DSI1.
3. **display_on sent too early**: `display_on` must come after PPS and compression mode. Check the panel driver's `prepare`/`enable` sequence.

## USB-C ports not working

If USB does not work after booting with the custom kernel:

1. Verify patch 0001 (aux-bridge) is applied. Without it, the USB-C PHY probe fails due to the missing DP bridge endpoint.
2. Check `dmesg | grep -i "aux-bridge\|qmp"` for probe errors.

## Display corruption or artifacts

1. **FIFO underflow**: Check `dmesg` for underflow errors. Ensure patch 0004 (widebus DIV_ROUND_UP) is applied.
2. **Wrong clock rate**: Verify byte_clk is 85.4 MHz, not 42.7 MHz.

## Kernel panic on boot

1. Try booting with the stable kernel (6.14 with simpledrm) to verify the system is healthy.
2. Add `earlycon` to kernel parameters for early serial output (if serial access is available).
3. Ensure `arm64.nopauth` is in the boot parameters.

## Filesystem corruption after hard reboot

Use btrfs instead of ext4. btrfs is more resilient to unclean shutdowns during development. If corruption occurs:

```bash
btrfs check /dev/nvme0n1pX
btrfs check --repair /dev/nvme0n1pX  # only if needed
```

## Hardware register debugging

The `tools/read_dsc_regs.c` tool can dump DPU, DSC, INTF, and DSI hardware registers to verify the configuration:

```bash
cd tools/
gcc -O2 -o read_dsc_regs read_dsc_regs.c
sudo ./read_dsc_regs
```

This requires root access and reads from `/dev/mem`.

## Useful dmesg filters

```bash
# All display-related messages
dmesg | grep -iE "dsi|dpu|dsc|panel|drm|msm|crtc|intf|disp"

# Clock tree
dmesg | grep -i "clk\|pll\|vco"

# Errors only
dmesg | grep -iE "error|fail|timeout|underflow"
```
