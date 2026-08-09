# Touchscreen Research Notes

> ## ⚠️ Status as of 2026-08-09 — read this first
>
> **This document describes the I2C-HID approach, which is no longer the recommended path.**
>
> The community has since moved to a **SPI-mode kernel driver with host-side coordinate
> computation** (i.e. an actual THP driver):
>
> - `himax-spi-core.c` (~1478 lines) + `hx-algo.c` (~1133 lines), by Kirikaze Chiyuki,
>   originating from [chiyuki0325/EGoTouchRev-Linux](https://github.com/chiyuki0325/EGoTouchRev-Linux)
> - Carried downstream as `patches/others/0003-Input-touchscreen-add-Himax-HX83121A-SPI-driver.patch`
>   in [KawaiiHachimi/linux-gaokun-buildbot](https://github.com/KawaiiHachimi/linux-gaokun-buildbot)
> - Upstream feature table now rates **touchscreen over SPI = works**, **over I2C = partial**
>   (occasional loss of contact while swiping)
>
> Consequently:
>
> - The conclusion below that **"no custom THP driver is needed"** turned out not to hold.
>   One was written, and it is now the better-working path.
> - The **`hx83121a-touch-recovery` service and its two-round bind sequence are obsolete.**
>   The SPI driver owns `reset-gpios` (tlmm 99) and the interrupt (tlmm 175) directly via DT;
>   no userspace recovery is involved.
> - The I2C bus is retained in the current device tree only for userspace debugging
>   (`/* himax ic @48 @49, enable this bus for userspace i2c IO */`).
>
> **What in this document is still valid and not available anywhere else:** the hardware
> reverse-engineering — the UEFI DXE initialization timeline, the DT02 / GPIO 174 mode-select
> mechanism, the AHB address-space writability map, the flash partition table, and the register
> map. In particular, **GPIO 174 is not managed by the current DT or by the SPI driver at all**
> (neither contains any reference to it), so the mode-select pin is currently left in whatever
> state UEFI happened to leave it in. This document remains the only written record of how that
> pin works.
>
> Treat the sections below as a **hardware reference and historical record**, not as installation
> instructions. Deprecated procedures are marked inline.

## Historical status (2026-03-08): Fully Working — Automatic Boot ROM Recovery

> **Superseded 2026-08-09.** Accurate for the I2C-HID path at the time of writing.
> See the status banner above.

## Latest Update (2026-03-08)

### Touchscreen Fully Working on NVMe Arch Linux

The HX83121A touchscreen now works reliably on the internal NVMe Arch Linux installation with automatic recovery at every boot. No Windows installation required.

**Root cause chain (fully understood):**

1. **UEFI `TouchPanelInit` DXE only runs on certain boot paths** — when booting from the NVMe with our GRUB (not the original Windows Boot Manager), UEFI skips touch initialization. The IC stays at status=0x04 (idle).

2. **Panel driver kills touch firmware** — the `panel-himax-hx83121a` kernel driver resets GPIO 99 during `hx83121a_prepare()` at ~3.9s after boot. Since HX83121A is TDDI (shared display+touch reset), this kills any touch firmware that was loaded.

3. **Boot ROM recovery works from Linux** — GPIO 99 hardware reset triggers Boot ROM to reload firmware from on-chip flash. Status goes 0x04 → 0x05 within ~0.1s.

4. **HID interface requires two-round bind sequence** — after Boot ROM loads firmware, the HID address 0x4F only responds when GPIO 174 is actively driven LOW (OE=1). A "wake" bind with 174 HIGH followed by unbind + 174 LOW + rebind is required.

**Recovery service**: `hx83121a-touch-recovery.service` runs at boot, waits for panel init to complete (by monitoring dmesg), then performs the two-round GPIO reset + bind sequence. Total recovery time: ~7 seconds from boot.

### Key Discoveries (2026-03-08)

1. **Boot ROM works reliably** — GPIO 99 reset triggers Boot ROM to copy firmware from flash to Code SRAM. Confirmed across 10+ reboots.

2. **Code SRAM 0x78787878 is normal** — hardware read-protection, NOT "empty". Returns 0x78787878 even when firmware IS running (status=0x05).

3. **Xiaomi SRAM direct-write does NOT work on our IC** — TCON+ADC reset (0x80020020/0x80020094) does not unlock Code SRAM. These registers are unreadable on our silicon revision.

4. **Touch survives Windows deletion** — contrary to earlier assumption, deleting Windows does NOT permanently kill touch. The issue was always about UEFI boot path, not Windows presence.

5. **GPIO 174 must be actively driven LOW for HID** — 0x4F (HID interface) NACKs when GPIO 174 floats (OE=0). Must keep OE=1 and drive LOW.

6. **Two-round bind is required** — binding with GPIO 174 HIGH fails but "wakes" the HID interface. Second bind with 174 LOW succeeds. Single-round recovery always fails.

### Recovery Sequence (proven reliable)

```
1. Wait for panel init (monitor dmesg for "Init sequence completed")
2. Unbind i2c_hid_of from 4-004f
3. GPIO 174 HIGH (OE=1) — I2C mode select
4. GPIO 99 LOW 50ms → HIGH — reset pulse
5. Wait for status=0x05 via AHB bridge (0x48) — Boot ROM loads ~0.1s
6. Bind i2c_hid_of (fails, but wakes HID interface)
7. Wait 1s
8. Unbind i2c_hid_of
9. GPIO 174 LOW (keep OE=1!) — HID interface becomes responsive
10. Wait 0.5s, verify 0x4F ACKs
11. Bind i2c_hid_of — touch input devices appear
```

### Deployment — DEPRECATED (2026-08-09)

> Do not use on a current kernel. The SPI driver (`himax,hx83121a-ts`) handles reset and
> interrupt itself; running this service alongside it will fight the driver over GPIO 99.
> Kept for reference on the I2C-HID path only.

```bash
# Copy recovery script
cp tools/touchscreen/hx83121a-touch-recovery /usr/local/bin/
chmod +x /usr/local/bin/hx83121a-touch-recovery

# Install and enable service
cp tools/touchscreen/hx83121a-touch-recovery.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable hx83121a-touch-recovery.service
```

### Previous: Direct SRAM Write Method (2026-02-14) — DOES NOT WORK

~~Discovered direct SRAM write via Xiaomi hxchipset driver.~~ Tested on 2026-03-08: Code SRAM remains 0x78787878 after TCON+ADC reset. **This approach is invalid for our IC revision.**

## Hardware

| Parameter | Value |
|-----------|-------|
| Touch IC | Himax HX83121A (TDDI — same IC as display driver) |
| Chip ID | 0x83121A00 |
| SPI Bus | SPI6 via spidev0.0, Mode 3 (CPOL=1, CPHA=1). 1 MHz was the rate used for manual probing only — the IC is specified at **12 MHz** (see ACPI table below), and the current in-kernel DT uses `spi-max-frequency = <12000000>` |
| I2C Bus | GENI SE4 at 0x990000 (proto=3=I2C) |
| I2C Addresses | 0x48 (AHB bridge), 0x4F (HID event interface) |
| Architecture | THP (Touchscreen Host Processing), Master/Slave dual-SPI |
| On-chip Flash | Puya P25Q40H, 4Mbit/512KB SPI NOR (JEDEC 0x856013) |
| Touch matrix | 36 RX × 18 TX electrodes |
| Max touch points | 10 |
| Interrupt GPIO | tlmm 175 (active low) |
| Reset GPIO | tlmm 99 (active low) — **WARNING: resets display too (TDDI)** |
| Mode Select GPIO | tlmm 174 — HIGH=I2C mode, LOW=SPI mode (also ACPI DT02 register at 0x0F1AE004) |
| I2C SDA/SCL | GPIO 171/172 (qup4 function) |
| SPI MISO/MOSI/CLK/CS | GPIO 154/155/156/157 (qup6 function) |
| Power supply | vreg_misc_3p3 (VCC3B), vreg_s10b |

### ACPI-Defined Interfaces (from Windows DSDT)

The DSDT defines three mutually exclusive touch interfaces, selected by firmware at boot via the **DT02** register:

| ACPI Device | HID | Bus | _STA Condition | Description |
|-------------|-----|-----|----------------|-------------|
| THPA (HIMX0001) | SPI7 (0x998000) | GPIO 99/175/8, 12MHz | DT02==0 → 0x0F | Main touch (SPI) |
| THPB (HIMX0002) | SPI20 | GPIO 39, 12MHz | DT02==0 → 0x0F | Stylus (SPI) |
| HIMX (HIMX1234) | I2C5 | addr 0x4F, 1MHz | DT02!=0 → 0x0F | I2C HID (PNP0C50) |

**DT02 register** at physical address 0x0F1AE004 (GPIO 174 IN_OUT register in TLMM):
- GPIO 174 OUT=HIGH → DT02 ≠ 0 → I2C mode (HIMX enabled)
- GPIO 174 OUT=LOW → DT02 = 0 → SPI mode (THPA/THPB enabled)

## I2C-HID — CONFIRMED WORKING

When IC firmware is running (status=0x05), the standard Linux I2C-HID stack works:
- `i2c_hid_of` probes 0x4F → HID descriptor (30 bytes, 712-byte report descriptor)
- `hid-multitouch` creates: Touchscreen (5 contacts, Protocol B) + Stylus input devices
- 60Hz report rate, ABS_MT_POSITION_X/Y 0-4096, ABS_PRESSURE 0-255, 10 slots
- VID:PID = 4858:121A, INPUT_PROP_DIRECT
- ~~**No custom THP driver needed** — IC handles coordinate computation in I2C-HID mode~~

> **Corrected 2026-08-09.** This is true of the I2C-HID path in isolation: in that mode the IC
> does compute coordinates internally. But the conclusion drawn from it — that no THP driver
> would ever be needed — did not hold. A host-side THP driver was subsequently written for the
> SPI path (`hx-algo.c`), and it now delivers better results than I2C-HID, which upstream rates
> as only *partial* due to contact loss while swiping.

## GPIO 99 Reset

Direct MMIO access for GPIO 99 hardware reset:

```python
TLMM_BASE = 0x0F100000
cfg_addr = TLMM_BASE + 99 * 0x1000    # 0x0F163000
io_addr = cfg_addr + 4                 # 0x0F163004

cfg |= (1 << 9)       # Set OE bit
write(cfg_addr, cfg)
write(io_addr, 0x00)   # LOW (reset asserted), wait 50ms
write(io_addr, 0x02)   # HIGH (reset released)
cfg &= ~(1 << 9)       # Clear OE (return to input)
write(cfg_addr, cfg)
```

## I2C AHB Bridge Protocol

Same logical protocol as SPI, but uses I2C transactions:

```
Write: i2c_write([cmd, params...])
Read:  i2c_write([cmd]), then i2c_read(N)
```

Bus commands: 0x00 (addr), 0x08 (read data), 0x0C (direction), 0x0D (INCR4=0x12), 0x13 (CONTI=0x31), 0x31/0x32 (password).

## SPI Communication

SPI6 communicates using the Himax bus command protocol:

```
Write: [0xF2, cmd, params...]          - WriteBus (full duplex, TX only)
Read:  [0xF3, cmd, 0x00, 0x00...]      - ReadBus (full duplex, skip 3 bytes then read)
```

## Flash Programming — Verified 100%

Firmware programmed to on-chip flash via SPI200 controller (0x80000xxx):
- **Size**: 261,120 bytes (full firmware binary)
- **Method**: SPI200 write-enable + page-program commands
- **Verification**: All bytes match — header ("HX83121-A"), partition table, code sections, config sections

## Key Register Map

| Register | Address | Values | Purpose |
|----------|---------|--------|---------|
| IC ID | 0x900000D0 | 0x83121A00 | Chip identification |
| Status | 0x900000A8 | 0x04=idle, 0x05=FW running, 0x0C=safe mode | Central state |
| System Reset | 0x90000018 | write 0x55 | Reset IC CPU |
| FW ISR Control | 0x9000005C | write 0xA5 | FW stop |
| Flash Reload | 0x10007F00 | 0x00=enable, 0xA55A=disable | Boot ROM reload control |
| Reload Done | 0x100072C0 | expect 0x72C0 when FW loaded | Boot ROM completion flag |
| Sorting Mode | 0x10007F04 | 0x9999=awaiting FW, 0x0000=normal | IC mode |

## UEFI TouchPanelInit DXE Reverse Engineering

Reverse-engineered from BIOS capsule. Three DXE modules handle touch init:

### Complete UEFI Touch Initialization Timeline

```
Phase 1: DisplayDxe
  - GetLcdId() → "CSOT_HX83121"
  - GPIO 38 reset → DSI init → DSC → panel lights up

Phase 2: TouchPanelInit
  - GetVariable("TouchPanelInit", attrs=0x3)
  - ConfigGpio(174) → output, pull-up
  - GpioOut(174, 1) → HIGH (I2C mode)
  - ConfigGpio(99) → output, pull-up
  - GpioOut(99, 1) → HIGH (reset released)
  → Boot ROM loads firmware (0x04 → 0x05)

Phase 3: I2cTouchPanel
  - GpioOut(174, 0) → LOW (switch to SPI mode)
  - ReadHidDescriptor() at 0x4F
  - ReadReportDescriptor()
  - Installs TouchDeviceInitProtocol
```

### UEFI Variables

| Variable | Attrs | Linux Visible | Purpose |
|----------|-------|---------------|---------|
| TouchPanelInit | 0x3 (NV+BS) | No (no RT) | DXE handshake |
| I2CWriteAndReadBUSY | 0x7 (NV+BS+RT) | Yes | Touch busy flag |

## AHB Address Space Writability

| Address Region | Size | Read | Write | Purpose |
|---|---|---|---|---|
| 0x00000000 - 0x0003FFFF | 256KB | OK | **NO** | Flash/ROM read window |
| 0x08000000 - 0x0801FFFF | 128KB | OK | **NO** | Code SRAM (HW protected) |
| 0x10006000 - 0x10007FFF | 8KB | OK | YES | FW config/data registers |
| 0x20000000 - 0x2001FFFF | 128KB | OK | YES | Data SRAM |
| 0x80000000 - 0x80050xxx | varies | OK | YES | SPI200 / Flash / Reload controllers |
| 0x90000000 - 0x900880FF | varies | OK | YES (partial) | IC core registers |

## DPMS Power Management Warning

DRM runtime power management can cause DPMS Off. When DSI link goes down, the TDDI IC becomes unreachable via I2C. The `keep-display-on.service` prevents this. Note: PMIC power rails (vreg_misc_3p3, vreg_s10b) stay up during DRM power-off — IC survives but becomes unresponsive until DSI is restored.

## Firmware Analysis

### Firmware Binary
- **File**: `hx83121a_gaokun_fw.bin` (261,120 bytes / 0x3FC00)
- **Header**: "HX83121-A", date 2022-09-27 19:30:56
- **Variant**: CSOT panel (confirmed by flash byte-by-byte match)

### Panel Variants (from himax_thp_drv.dll)

The DLL embeds 3 firmware variants for different panel types, selected by OTP project ID:
- BOE, CSOT New, **CSOT (our device)**

### Partition Table (flash offset 0x20030)

| # | SRAM Addr | Size | FW Offset | Type | Dest |
|---|-----------|------|-----------|------|------|
| 0 | 0x00000400 | 8,192 | 0x00000400 | Code | → 0x08000400 |
| 1 | 0x00002400 | 109,056 | 0x00002400 | Code | → 0x08002400 |
| 2 | 0x0001CE00 | 5,376 | 0x0001CE00 | Code | → 0x0801CE00 |
| 3 | 0x0001E300 | 5,376 | 0x0001E300 | Code | → 0x0801E300 |
| 4 | 0x0001F800 | 1,024 | 0x0001F800 | Code | → 0x0801F800 |
| 5-9 | 0x10007xxx | varies | varies | Config | FW regs |

## THP Architecture

The HX83121A uses THP (Touchscreen Host Processing) — IC outputs raw capacitive data, host software computes coordinates. On Windows, requires `HuaweiThpService` daemon. On Linux in I2C-HID mode, the IC handles coordinate computation internally — no THP needed.

## Current SPI path (2026-08-09) — and what this document still answers

The in-kernel device tree node used by the current SPI driver:

```dts
&spi6 {
	qcom,force-gsi-mode;                     /* see "open issues" below */

	touchscreen@0 {
		compatible = "himax,hx83121a-ts";
		reg = <0>;
		interrupts-extended = <&tlmm 175 IRQ_TYPE_LEVEL_LOW>;
		reset-gpios = <&tlmm 99 GPIO_ACTIVE_LOW>;
		panel = <&panel>;
		spi-max-frequency = <12000000>;
		touchscreen-size-x = <2560>;         /* upstream uses 25600 — see below */
		touchscreen-size-y = <1600>;         /* upstream uses 16000 */
		touchscreen-swapped-x-y;
		touchscreen-inverted-x;
	};
};
```

Note that IRQ (175) and reset (99) match the values documented in the hardware table above.

### Open issues in the current path

**1. GPIO 174 (mode select) is unmanaged.**

Neither the device tree nor the SPI driver contains any reference to GPIO 174. The pin is left
in whatever state UEFI left it in. Per the UEFI timeline documented below, `I2cTouchPanel`
(Phase 3) ends by driving 174 LOW — i.e. SPI mode — which is what the SPI driver needs, so the
common boot path happens to work.

This is fragile rather than slow: mode select is a binary choice of which physical interface the
IC listens on, so a wrong state means chip detection fails outright, not that touch degrades.
The risk is on boot paths where `TouchPanelInit` does not run (documented above) and potentially
across suspend/resume, where nothing in the kernel can drive the pin back.

**2. `qcom,force-gsi-mode` currently has no effect in some trees.**

The property originates from `right-0903/linux-gaokun` commit `f6b55e5`
("force to use GPI DMA for spi touchscreen") and requires the companion patch
`0025-spi-qcom-geni-Add-property-to-force-GSI-mode`. Mainline `spi-geni-qcom.c` selects its
transfer mode purely from a hardware readback of `GENI_IF_DISABLE_RO`, and has no way to
request GSI/GPI DMA; if the companion patch is absent the DT property is silently ignored.

This matters for a polling THP driver: the event stack read is

```
128 + (2 + 60*40 + 40 + 60) * 2 = 5132 bytes per frame
                                ≈ 301 KB/s @ 60 Hz, 601 KB/s @ 120 Hz
```

Large reads still fall through to SE_DMA, but the many small register transactions of the Himax
bus protocol go through the PIO FIFO path, each interrupt-driven and each re-running the
transfer setup.

**3. Reported touch resolution differs between trees.**

`right-0903` commit `de126d3` ("touchscreen: support 10x touch resolution", 2026-04-05) changed
both its DTS (`2560/1600` → `25600/16000`) and its own DKMS driver constants
(`X_SCALE 45 → 9`, `X_TOTAL/Y_TOTAL` ×10) together. The buildbot tree still carries `2560/1600`
while using a *different* driver (chiyuki0325's), which sets `input_set_abs_params(..., 0,
SZ_64K - 1, 8, 0)` and then lets `touchscreen_parse_properties()` override the maximum from DT.
Whether `2560` or `25600` is correct therefore depends on the coordinate scale that driver's
algorithm emits, which has not been confirmed here. If the DT maximum is lower than the scale
the algorithm produces, motion would appear quantized.

## Companion Docs
- `docs/TOUCHSCREEN_LIVE_TEST_2026-02-11.md` — 6 rounds of live testing
- `docs/TOUCHSCREEN_READ_PLANE_DEBUG_2026-02-11.md` — SPI event plane debug
- `docs/UEFI_FIRMWARE_TOUCH_ANALYSIS_2026-02-11.md` — UEFI capsule analysis
- `docs/ACPI_TOUCH_DIFF_216_vs_217.md` — BIOS 2.16 vs 2.17 ACPI comparison

## References

- [EGoTouchRev-rebuild](https://github.com/awarson2233/EGoTouchRev-rebuild) — Windows ARM64 userspace touch driver
- [MiCode/Xiaomi_Kernel_OpenSource (dagu-s-oss)](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/dagu-s-oss/drivers/input/touchscreen/hxchipset) — Himax driver with SRAM write (not applicable to our IC)
- [HimaxSoftware/hx_hid_util](https://github.com/HimaxSoftware/hx_hid_util) — Official Himax HID utility
- [linux-gaokun](https://github.com/right-0903/linux-gaokun) — MateBook E Go Linux support project
- [chiyuki0325/EGoTouchRev-Linux](https://github.com/chiyuki0325/EGoTouchRev-Linux) — **current SPI
  touchscreen driver and tuning algorithm** (the path that superseded this document's I2C-HID approach)
- [KawaiiHachimi/linux-gaokun-buildbot](https://github.com/KawaiiHachimi/linux-gaokun-buildbot) —
  packaging/build tree carrying the SPI driver patch and prebuilt Fedora/Ubuntu images
