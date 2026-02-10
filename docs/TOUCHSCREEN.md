# Touchscreen Research Notes

## Status: Not Working — Boot ROM requires UEFI/XBL trigger (all software methods exhausted)

The MateBook E Go's touchscreen uses the **Himax HX83121A** TDDI (Touch & Display Driver Integration) IC with a **THP (Touchscreen Host Processing) architecture** — the IC outputs raw capacitive data and host-side software computes touch coordinates. On Windows, this requires the `HuaweiThpService` daemon; stopping it disables touch entirely.

We have established communication via both **I2C** (AHB bridge at 0x48) and **SPI** (Mode 3, Himax protocol via spidev0.0 on SPI6). Firmware has been successfully programmed to on-chip flash via the SPI200 controller and **verified 100% byte-by-byte**. Flash is **unprotected** (SR1/2/3=0x00, Puya P25Q40H chip). CRC is correct. However, the **boot ROM refuses to load firmware** regardless of the method used — GPIO hardware reset, software system reset, full EGoTouchRev sequence reproduction, or reload engine manipulation. The IC stays at status=0x04 (idle) instead of 0x05 (FW running).

On a confirmed working system (Detach0-0), IC status is already 0x05 **before any driver runs**, indicating UEFI/XBL triggers Boot ROM during the display initialization phase. Our UEFI/XBL does not appear to do this.

## Hardware

| Parameter | Value |
|-----------|-------|
| Touch IC | Himax HX83121A (TDDI — same IC as display driver) |
| Chip ID | 0x83121A00 |
| SPI Bus | SPI6 via spidev0.0, Mode 3 (CPOL=1, CPHA=1), 1MHz |
| I2C Bus | GENI SE4 at 0x990000 (proto=3=I2C) |
| I2C Addresses | 0x48 (AHB bridge), 0x4F (HID event interface) |
| Architecture | THP (Touchscreen Host Processing), Master/Slave dual-SPI |
| On-chip Flash | Puya P25Q40H, 4Mbit/512KB SPI NOR (JEDEC 0x856013) |
| Touch matrix | 36 RX × 18 TX electrodes |
| Max touch points | 10 |
| Interrupt GPIO | tlmm 175 (active low) |
| Reset GPIO | tlmm 99 (active low) — **WARNING: resets display too (TDDI)** |
| I2C SDA/SCL | GPIO 171/172 (qup4 function) |
| SPI MISO/MOSI/CLK/CS | GPIO 154/155/156/157 (qup6 function) |
| Power supply | vreg_misc_3p3 (VCC3B), vreg_s10b |

### ACPI-Defined Interfaces (from Windows DSDT)

The DSDT defines three mutually exclusive touch interfaces, selected by firmware at boot:

| ACPI Device | HID | Bus | Description |
|-------------|-----|-----|-------------|
| THPA (HIMX0001) | SPI6 | GPIO 154-157, 12MHz | Main touch (SPI) |
| THPB (HIMX0002) | SPI20 | GPIO 87-90, 12MHz | Stylus (SPI) |
| HIMX (HIMX1234) | I2C4 | addr 0x4F, 1MHz | I2C HID (PNP0C50) |

**Note**: I2C HID address 0x4F is for HID event interface; 0x48 is for AHB bridge register/firmware access.

## SPI Communication — Working!

SPI6 communicates with the HX83121A using the Himax bus command protocol:

### Bus Commands (SPI)
```
Write: [0xF2, cmd, params...]          - WriteBus (full duplex, TX only)
Read:  [0xF3, cmd, 0x00, 0x00...]      - ReadBus (full duplex, skip 3 bytes then read)
```

### AHB Read (SPI)
```python
burst_enable(1)                              # 0x0D=0x13, 0x13=0x31
hw(0x00, addr_LE_4B)                         # Set address
hw(0x0C, [0x00])                             # Direction = read
data = hr(0x08, 4)                           # Read 4 bytes
```

### AHB Write (SPI)
```python
burst_enable(1)                              # 0x0D=0x13, 0x13=0x31
hw(0x00, addr_LE_4B + data_LE_4B)            # Address + data combined
```

### Burst Enable
```python
hw(0x0D, [0x12 | state])    # state=1 for burst (>4B), state=0 for single (≤4B)
hw(0x13, [0x31])             # CONTI enable
```

### Safe Mode (Password Unlock)
```python
hw(0x31, [0x27])             # Password byte 1
hw(0x32, [0x95])             # Password byte 2
# Verify: read back 0x31→0x27, 0x32→0x95
# Status (0x900000A8) becomes 0x0C (safe mode)
```

## I2C AHB Bridge Protocol

Same logical protocol as SPI, but uses I2C transactions:

```
Write: i2c_write([cmd, params...])
Read:  i2c_write([cmd]), then i2c_read(N)
```

Bus commands are identical: 0x00 (addr), 0x08 (read data), 0x0C (direction), 0x0D (INCR4=0x12), 0x13 (CONTI=0x31), 0x31/0x32 (password).

## GPIO 99 Reset — Working!

Direct MMIO access for GPIO 99 hardware reset:

```python
TLMM_BASE = 0x0F100000
cfg_addr = TLMM_BASE + 99 * 0x1000    # 0x0F163000
io_addr = cfg_addr + 4                 # 0x0F163004

# IMPORTANT: After reboot, OE=0 (input mode). Must set OE=1 first!
cfg |= (1 << 9)       # Set OE bit
write(cfg_addr, cfg)

# Reset sequence:
write(io_addr, 0x00)   # LOW (reset asserted), wait 20ms
write(io_addr, 0x02)   # HIGH (reset released)
cfg &= ~(1 << 9)       # Clear OE (return to input)
write(cfg_addr, cfg)
```

**Verification**: IC returns 0xFFFFFFFF during reset LOW, recovers after release.

## Flash Programming — Verified 100%

Firmware programmed to on-chip flash via SPI200 controller (0x80000xxx):
- **Size**: 261,120 bytes (full firmware binary)
- **Method**: SPI200 write-enable + page-program commands
- **Verification**: All bytes match — header ("HX83121-A"), partition table, code sections, config sections
- **Persistence**: Survives GPIO reset and tablet reboot (cold power cycle not yet tested)

## AHB Address Space Writability (Definitive — I2C AND SPI tested)

| Address Region | Size | Read | Write | Purpose |
|---|---|---|---|---|
| 0x00000000 - 0x0003FFFF | 256KB | OK | **NO** (silent drop) | Flash/ROM read window |
| 0x08000000 - 0x0801FFFF | 128KB | OK | **NO** (silent drop) | Code SRAM — firmware target |
| 0x10006000 - 0x10007FFF | 8KB | OK | **YES** | FW config/data registers |
| 0x20000000 - 0x2001FFFF | 128KB | OK | **YES** (single-word) | Data SRAM |
| 0x80000000 - 0x80050xxx | varies | OK | **YES** | SPI200 / Flash / Reload controllers |
| 0x90000000 - 0x900880FF | varies | OK | **YES** (partial) | IC core registers |

## Code SRAM Write — ALL Methods Failed (I2C AND SPI)

Every attempt to write to 0x08000xxx returns 0x78787878 (empty pattern):

| # | Method | Result |
|---|--------|--------|
| 1 | Standard AHB write (0x00+addr+data) | FAIL |
| 2 | Safe mode (password unlock 0x31/0x32) | FAIL |
| 3 | MCU off (bus cmd 0x82 = 0xDA) | FAIL |
| 4 | FW stop (0x9000005C = 0xA5) + TCON/ADC off | FAIL |
| 5 | Direction register = write (0x0C = 0x01) | FAIL |
| 6 | All INCR4 values (0x10, 0x11, 0x12, 0x13, 0xFF) | FAIL |
| 7 | No burst mode (single word) | FAIL |
| 8 | Immediate post-reset write (within 1-2ms) | FAIL |
| 9 | Oncell flash unlock sequence (magic to 0x00-0x0C) | FAIL |
| 10 | All above via I2C AND SPI | FAIL |

**Conclusion**: Code SRAM has **hardware write protection** that cannot be disabled from the SPI/I2C bus. Only the IC's internal hardware (boot ROM / reload engine) can write to it.

## Boot ROM — ALL Methods Exhausted, NOT Loading

### Verified OK
- Flash content 100% matches DLL-extracted firmware (byte-by-byte comparison via I2C AHB bridge)
- Flash not protected (SPI Status Register 1/2/3 = 0x00)
- Flash CRC correct (0x7D4E5A69 at 0x3FBFC → HW CRC = 0)
- Flash header "HX83121-A" present at flash address 0x00000
- GPIO99 reset works correctly (IC resets, I2C communication recovers)
- IC responds with correct ID (0x83121A00) after every reset

### After Every Reset Attempt
- **Status (0x900000A8)**: 0x04 (idle) — **never** reaches 0x05 (FW running)
- **reload_done (0x100072C0)**: 0x00000000 — **never** becomes 0x72C0
- **Code SRAM**: 0x78787878 at all addresses — **never** populated
- **reload_status (0x80050000)**: 0x00000012 (initial)
- **Boot stat (0x900000E0)**: 0x54930000 (unchanged across all tests)
- **Flash data**: Intact and correct

### All Failed Boot Attempts

| # | Method | Tool | Result |
|---|--------|------|--------|
| 1 | GPIO99 hardware reset (20ms LOW) | C tool via gpiochip4 | 0x04 |
| 2 | System reset (0x90000018=0x55) | I2C AHB write | 0x04 |
| 3 | 5× GPIO reset (EGoTouchRev hx_sense_on sequence) | GPIO + I2C | 0x04 |
| 4 | Safe mode + data SRAM config + GPIO reset | I2C + GPIO | 0x04 |
| 5 | Reload engine activ_relod (0xEC to 0x90000048) | I2C | reload_status changes, no SRAM copy |
| 6 | Oscillator enable (0x900880A8/E0) before reset | I2C | 0x04 |
| 7 | Flash auto mode (0x80000004) | I2C | 0x04 |
| 8 | Long reset pulse (500ms) | GPIO | 0x04 |
| 9 | Config partitions written from FW binary | I2C | 0x04 |
| 10 | Full EGoTouchRev init_buffers + hx_sense_on(true) | GPIO + I2C | 0x04 |

### Full EGoTouchRev Sequence Reproduction (Test #10 detail)
Following the **exact** sequence from [Detach0-0's Windows driver](https://github.com/awarson2233/EGoTouchRev-rebuild):

1. GPIO99 reset (bus_fail handler: hw_reset slave+master)
2. check_bus + burst_enable
3. init_buffers_and_register (clear 0x10007550 80B + 0x1000753C 4B)
4. Enter safe mode (0x31=0x27, 0x32=0x95)
5. hx_set_N_frame(1) — write 0x01 then 0x7F0C0001 to 0x10007294
6. hx_reload_set(0) — write 0x00000000 to 0x10007F00 (enable flash reload)
7. hx_switch_mode(RAWDATA) — write 0x00000000 to 0x10007F04
8. 5× retry: clear 0x100072C0, GPIO99 reset, burst_enable, poll status
9. Fallback: software system reset (0x90000018=0x55)

**Result**: Status stays at 0x04 through all 5 HW reset attempts + SW reset. Boot ROM does not load firmware.

### Flash Protection Check
Via SPI200 RDSR/JEDEC commands through I2C AHB bridge:
- Flash SR1 = 0x00 (no block protect, no write enable latch)
- Flash SR2 = 0x00 (no quad enable, no security bits)
- Flash SR3 = 0x00 (no write protect)
- JEDEC ID = 0x856013 (Puya P25Q40H, 4Mbit/512KB)

### Reload Engine Investigation
- Writing 0xEC to activ_relod (0x90000048) changes reload_status from 0x12 to 0x10
- But NO data is copied to code SRAM
- CRC registers (0x80050018) stay at 0xFFFFFFFF
- Pre-configuring reload_addr_from/cmd_beat has no effect

### Conclusion
The Boot ROM requires an **external trigger from UEFI/XBL** during the display initialization phase. On Detach0-0's working system, IC status is already 0x05 before any Windows driver runs. This trigger cannot be replicated from Linux userspace via I2C, SPI, or GPIO.

## Firmware Analysis

### Firmware Binary
- **File**: `hx83121a_gaokun_fw.bin` (261,120 bytes / 0x3FC00)
- **Source**: Extracted from Windows `himax_thp_drv.dll` driver (Copy4 variant)
- **Header**: "HX83121-A", date 2022-09-27 19:30:56
- **Variant**: CSOT panel (confirmed by flash byte-by-byte match)

### Panel Variants (from himax_thp_drv.dll in Gaokun_THP_Software_1.0.1.39.exe)

The DLL embeds **3 full firmware copies** for different panel types, selected by OTP project ID:

| DLL Offset | Date | MD5 | Panel Type |
|-----------|------|-----|------------|
| 0x0681c0 | 19:32:44 | 4454a1c2... | BOE (estimated) |
| 0x0a7dc0 | 19:34:25 | aaf608db... | CSOT New (estimated) |
| 0x0e79c0 | 19:30:56 | e538f2f6... | **CSOT — our device** |

4 panel types referenced in DLL strings: "Found CSOT panel!", "Found CSOT New panel!", "Found BOE new panel!", "Found BOE old panel!". Selection is done by `hx_firmware_remapping()` based on `getProjectID_OTP()` + CG Color + Sensor ID.

**Our device's flash matches Copy4 (CSOT) exactly** — firmware variant mismatch has been ruled out as the Boot ROM failure cause.

### Partition Table (flash offset 0x20030)

Format: 16-byte entries: `[sram_addr(4)][size(4)][fw_offset(4)][flags(4)]`

| # | SRAM Addr | Size | FW Offset | Flags | Type | Dest |
|---|-----------|------|-----------|-------|------|------|
| 0 | 0x00000400 | 8,192 | 0x00000400 | 0x0A | Code | → 0x08000400 |
| 1 | 0x00002400 | 109,056 | 0x00002400 | 0x00 | Code | → 0x08002400 |
| 2 | 0x0001CE00 | 5,376 | 0x0001CE00 | 0x00 | Code | → 0x0801CE00 |
| 3 | 0x0001E300 | 5,376 | 0x0001E300 | 0x00 | Code | → 0x0801E300 |
| 4 | 0x0001F800 | 1,024 | 0x0001F800 | 0x00 | Code | → 0x0801F800 |
| 5 | 0x10007000 | 120 | 0x00021400 | 0x00 | Config | FW regs |
| 6 | 0x10007084 | 528 | 0x000214FE | 0x00 | Config | FW regs |
| 7 | 0x10007300 | 180 | 0x00021E00 | 0x00 | Config | FW regs |
| 8 | 0x100072F0 | 16 | 0x00021DD0 | 0x00 | Config | FW regs |
| 9 | 0x100073F0 | 32 | 0x00021DE0 | 0x00 | Config | FW regs |

**Note**: Code partition sram_addr values are offsets within code SRAM (0x08000000 + sram_addr). Config partitions go directly to FW register addresses. 0x10007F00 (flash_reload) and 0x10007F04 (sorting_mode) are NOT in any config partition.

## Key Register Map

| Register | Address | Values | Purpose |
|----------|---------|--------|---------|
| IC ID | 0x900000D0 | 0x83121A00 | Chip identification |
| Status | 0x900000A8 | 0x04=idle, 0x05=FW running, 0x0C=safe mode | Central state |
| System Reset | 0x90000018 | write 0x55 | Reset IC CPU |
| FW ISR Control | 0x9000005C | write 0xA5 | FW stop |
| activ_relod | 0x90000048 | write 0xEC | Trigger reload (doesn't work) |
| Reset Event | 0x900000E4 | varies | Flag: reset occurred |
| Flash Reload | 0x10007F00 | 0x00=enable, 0xA55A=disable | Boot ROM reload control |
| Reload Done | 0x100072C0 | expect 0x72C0 when FW loaded | Boot ROM completion flag |
| Sorting Mode | 0x10007F04 | 0x9999=awaiting FW, 0x0000=normal | IC mode |
| Reload Status | 0x80050000 | 0x12=initial, 0x01000000=after activ_relod | HW reload engine |
| Reload CRC32 | 0x80050018 | 0xFFFFFFFF=not computed | HW CRC result |
| Flash Checksum | 0x80000044 | 0x00000000 | Flash checksum register |

## EGoTouchRev Analysis

[Detach0-0's Windows driver](https://github.com/awarson2233/EGoTouchRev-rebuild) is a userspace touch driver for Windows ARM64. Key findings:

- **Does NOT download firmware** — assumes boot ROM loads FW from flash
- **Boot sequence**: GPIO reset → check status=0x05 → poll reload_done=0x72C0
- **Uses SPI** via SPBTESTTOOL.sys driver (IOCTLs for SPI full-duplex + GPIO control)
- **Dual device**: master (THPA/SPI6) + slave (THPB/SPI20)

### Root Cause Hypothesis
The Boot ROM requires a trigger from UEFI/XBL that occurs during the display initialization phase — possibly a specific DSI command, power sequencing event, or flash controller initialization that we cannot replicate from Linux userspace.

**Ruled out**: Flash content mismatch, flash protection, flash CRC, GPIO reset timing, data SRAM configuration, reload engine, software reset, 6.18 MSM DRM disruption (same result on 6.14 simpledrm), **firmware variant mismatch** (flash confirmed as correct CSOT variant).

**Remaining possibilities**:
1. UEFI/XBL sends a specific command during DSI panel init that triggers Boot ROM
2. Factory flash contains additional data (header/config) not present in the DLL-extracted firmware
3. IC OTP is configured for "host-triggered boot" rather than "auto-load on power-on"

## TDDI Coupling Warning

**CRITICAL**: The HX83121A is a TDDI IC. Resetting via GPIO 99 also resets the display controller:
- DSI link errors (byte_clk stuck)
- Display goes black
- Requires full system reboot to recover

Never reset GPIO 99 while the display is active!

## Next Steps (Priority Order)

### 1. Windows Warm Reboot Test (Highest Priority)
Install Windows via UUP dump → boot → verify touch works (status=0x05) → warm reboot to Linux → immediately check IC status via I2C.
- If status=0x05 persists: UEFI/XBL Boot ROM trigger carries over through warm reboot
- Compare flash content and IC registers between Windows-booted and Linux-booted states
- Test reading touch event data via bus cmd 0x30

### 2. Get Detach0-0's Flash Dump
Ask Detach0-0 to dump their flash content (especially 0x20000-0x2002F header area and 0x40000+ region) for byte-by-byte comparison with our DLL-extracted firmware.

### 3. Investigate UEFI Touch Init Module
Huawei's UEFI firmware likely contains a touch initialization module that triggers Boot ROM. Reverse-engineering this could reveal the exact trigger mechanism.

### 4. Write Linux THP Driver (after Boot ROM is solved)
Once firmware loads successfully (status=0x05):
- **Option A**: Linux THP driver — read raw touch data via SPI bus cmd 0x30, compute coordinates on host, output via uinput
- **Option B**: Switch IC to I2C HID mode (HIMX1234 at 0x4F) → use standard hid-multitouch kernel driver
- Windows `HuaweiThpService` reads 5063 bytes (master) + 339 bytes (slave) per frame via SPI

### 5. UEFI Application (Fallback)
Write a custom UEFI app or DXE driver that runs before Linux boot and triggers the Boot ROM using the same mechanism as the OEM UEFI.

### 6. Community / Upstream
- [linux-gaokun](https://github.com/right-0903/linux-gaokun) — MateBook E Go Linux support project
- [awarson2233/EGoTouchRev-rebuild](https://github.com/awarson2233/EGoTouchRev-rebuild) — Windows ARM64 userspace touch driver
- Contribute findings to help the community

## THP (Touchscreen Host Processing) Architecture

Unlike traditional touchscreens where the IC computes coordinates internally, the HX83121A uses **THP** — the IC only outputs raw capacitive sensing data, and host-side software computes touch coordinates, gestures, and palm rejection.

### Windows THP Software Stack (Gaokun_THP_Software_1.0.1.39.exe)

```
SpbThpTool.sys (ARM64 KMDF)     ← SPI kernel driver, ACPI\HIMX0001/HIMX0002
  └── IOCTL interface
SpiModule.x64.dll                ← Userspace SPI layer (DeviceIoControl)
himax_thp_drv.dll (1.5MB)       ← Himax IC core driver
  ├── 3 embedded FW variants (CSOT, CSOT New, BOE)
  ├── hx_firmware_remapping()    ← OTP project ID → FW selection
  ├── flashProgramming()         ← Flash programming via SPI200
  └── hx_sense_on()              ← Start touch sensing
TSACore.dll (1.7MB)              ← Touch Signal Algorithm (raw → coords)
TSAPrmt.dll (5.0MB)              ← TSA parameters (per-panel tuning)
ApDaemon.dll (1.5MB)             ← Main daemon orchestrator
  ├── DriverThp                  ← Touch driver management
  ├── ThpBase                    ← Base touch processing
  └── VHF injection              ← HID reports to Windows
HidInjectorThp.sys (ARM64 KMDF) ← VHF virtual HID driver
THP_Service.dll                  ← Windows Service wrapper
HuaweiThpService.exe (.NET)      ← Service entry point
```

**Stopping HuaweiThpService = touch stops working** (confirmed by forum users)

### Linux Implications
- Standard `hid-multitouch` won't work directly (IC doesn't output HID reports in THP mode)
- Need either:
  - Custom Linux THP driver (SPI → raw data → coordinate computation → uinput/evdev)
  - Switch IC to I2C HID mode (HIMX1234/PNP0C50 at 0x4F) if supported by firmware
- The DLL's coordinate algorithm may need reverse-engineering for proper Linux implementation

## References

- [EGoTouchRev-rebuild](https://github.com/awarson2233/EGoTouchRev-rebuild) — Windows ARM64 userspace touch driver
- [MiCode/Xiaomi_Kernel_OpenSource (dagu-s-oss)](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/dagu-s-oss/drivers/input/touchscreen/hxchipset) — Himax hxchipset driver with full firmware download
- `drivers/input/touchscreen/himax_hx83112b.c` — Kernel Himax I2C driver (no FW download)
