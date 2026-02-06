# Kernel Patches

Four patches against Linux 6.18.8 required to bring up a dual-DSI DSC display on the Snapdragon 8cx Gen 3 (sc8280xp). All four are necessary for the Huawei MateBook E Go's HX83121A panel; patches 2-4 likely affect any sc8280xp DSC display.

## Applying

```bash
cd /path/to/linux-6.18.8
for p in /path/to/kernel-patches/000*.patch; do
    patch -p1 < "$p"
done
```

Dry run first:

```bash
for p in /path/to/kernel-patches/000*.patch; do
    patch -p1 --dry-run < "$p"
done
```

---

## 0001 -- bridge: aux-bridge: handle missing endpoint

**File:** `drivers/gpu/drm/bridge/aux-bridge.c`

**Problem:** On the sc8280xp, USB-C PHYs (qmp-combo) register auxiliary devices for DP alt-mode output. When no display endpoint is defined in the device tree (because the port is not connected to a display), `devm_drm_of_get_bridge()` returns `-ENODEV`, and the auxiliary device probe fails. This cascading failure prevents the entire USB-C PHY from loading, breaking USB functionality.

**Root cause:** The aux-bridge driver treats all `drm_of_get_bridge` errors identically, but `-ENODEV` simply means "no display output here" and is not an error.

**Fix:** When `devm_drm_of_get_bridge()` returns `-ENODEV`, return 0 (success) without adding a bridge, allowing the PHY to continue probing.

**Impact:** sc8280xp devices with USB-C ports that have DP alt-mode capability but no display connected.

---

## 0002 -- clk: qcom: dispcc-sc8280xp: remove CLK_SET_RATE_PARENT from byte dividers

**File:** `drivers/clk/qcom/dispcc-sc8280xp.c`

**Problem:** The DSI byte clock runs at the wrong frequency. Expected: 85.4 MHz. Actual: 42.7 MHz (exactly half).

**Root cause:** The four `byte_div_clk_src` dividers (disp{0,1}\_cc\_mdss\_byte{0,1}\_div\_clk\_src) have `CLK_SET_RATE_PARENT` set. When the DSI driver calls `clk_set_rate()` on `byte_intf_clk` (the child of the divider), the clock framework propagates the rate change up through the divider to the parent PLL. The PLL is reconfigured to produce a rate that, divided by the divider, equals the requested `byte_intf_clk` rate -- effectively halving the byte clock.

**Fix:** Remove `CLK_SET_RATE_PARENT` from all four byte divider clocks. Rate changes on the divider now only adjust the divider ratio, leaving the parent PLL at its correct frequency.

**Impact:** Any sc8280xp DSI display. Without this fix, the DSI link clock is wrong and the panel will not initialize.

---

## 0003 -- drm/msm/dpu: fix DSC compressed width truncation in encoder

**File:** `drivers/gpu/drm/msm/disp/dpu1/dpu_encoder_phys_vid.c`

**Problem:** The DPU encoder and DSI host disagree on the compressed line width. DPU computes 266 pixels; DSI computes 267 pixels. The 1-pixel mismatch causes the display to fail.

**Root cause:** The DPU encoder uses integer division:

```c
width = width * bpp / (bpc * 3);
// 800 * 8 / 24 = 266  (truncated from 266.67)
```

The DSI host (`dsi_timing_setup()`) uses `DIV_ROUND_UP` and gets 267.

**Fix:** Replace integer division with `DIV_ROUND_UP` to match the DSI host:

```c
width = DIV_ROUND_UP(width * bpp, bpc * 3);
// DIV_ROUND_UP(6400, 24) = 267
```

**Impact:** Any sc8280xp DSC display where `(width * bpp) % (bpc * 3) != 0`. This includes all 8bpp DSC configurations on panels with slice_width=800.

---

## 0004 -- drm/msm/dpu: fix widebus data_width truncation in INTF

**File:** `drivers/gpu/drm/msm/disp/dpu1/dpu_hw_intf.c`

**Problem:** Display underflows when wide-bus mode is active with an odd compressed width. The INTF data window is 2 bytes short, causing a FIFO underflow.

**Root cause:** Wide-bus mode halves the width using right-shift:

```c
data_width = p->width >> 1;
// 267 >> 1 = 133  (truncated)
// 133 pclks * 6 bytes/pclk = 798 bytes
// DSC needs 800 bytes per line -> underflow!
```

**Fix:** Use `DIV_ROUND_UP(width, 2)` instead of right-shift:

```c
data_width = DIV_ROUND_UP(p->width, 2);
// DIV_ROUND_UP(267, 2) = 134
// 134 * 6 = 804 bytes >= 800 -> OK
```

**Impact:** Any sc8280xp DSC display with wide-bus enabled and an odd compressed width. This is a direct consequence of patch 0003 (which correctly rounds up the width to 267).
