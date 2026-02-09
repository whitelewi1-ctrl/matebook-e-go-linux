# Touchscreen Research Notes

## Status: Not Working — Code SRAM hardware write-protected, Boot ROM not auto-loading

The MateBook E Go's touchscreen uses the **Himax HX83121A** TDDI (Touch & Display Driver Integration) IC. We have established communication via both **I2C** (AHB bridge at 0x48) and **SPI** (Mode 3, Himax protocol via spidev0.0 on SPI6). Firmware has been successfully programmed to on-chip flash via the SPI200 controller and verified 100%. However, **code SRAM (0x08000000) is hardware write-protected** from both I2C and SPI, and the **boot ROM does not auto-load firmware from flash** after GPIO reset. The IC stays at status=0x04 (idle) instead of 0x05 (FW running).

## Hardware

| Parameter | Value |
|-----------|-------|
| Touch IC | Himax HX83121A (TDDI — same IC as display driver) |
| Chip ID | 0x83121A00 |
| SPI Bus | SPI6 via spidev0.0, Mode 3 (CPOL=1, CPHA=1), 1MHz |
| I2C Bus | GENI SE4 at 0x990000 (proto=3=I2C) |
| I2C Addresses | 0x48 (AHB bridge), 0x4F (HID event interface) |
| Architecture | Master/Slave dual-IC, zero-flash |
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

## Boot ROM — Not Auto-Loading

After GPIO reset with correct register setup:
- **Status (0x900000A8)**: 0x04 (idle) — never reaches 0x05 (FW running)
- **reload_done (0x100072C0)**: 0x00000000 — never becomes 0x72C0
- **Code SRAM**: 0x78787878 at all addresses
- **reload_status (0x80050000)**: 0x00000012 (initial)
- **Flash data**: Intact and correct

### Full EGoTouchRev Boot Sequence Attempted
Following the exact sequence from [Detach0-0's Windows driver](https://github.com/awarson2233/EGoTouchRev-rebuild):

1. Clear 0x100072C0 (reload_done flag)
2. GPIO 99 reset (LOW 20ms, then HIGH)
3. burst_enable(1)
4. init_buffers_and_register (clear 0x10007550)
5. Enter safe mode
6. Write 0x00000000 to 0x10007F00 (flash reload enable)
7. Write 0x00000000 to 0x10007F04 (sorting mode)
8. 5× retry: clear 0x100072C0, GPIO reset, burst_enable, check status==0x05
9. Fallback: system reset (0x90000018=0x55)

**Result**: Status stays at 0x04 through all 5 attempts. Boot ROM does not load firmware.

### Reload Engine Investigation
- Writing 0xEC to activ_relod (0x90000048) changes reload_status from 0x12 to 0x01000000
- But NO data is copied to code SRAM
- CRC registers (0x80050018) stay at 0xFFFFFFFF
- Pre-configuring reload_addr_from/cmd_beat has no effect

## Firmware Analysis

### Firmware Binary
- **File**: `hx83121a_gaokun_fw.bin` (261,120 bytes / 0x3FC00)
- **Source**: Extracted from Windows `himax_thp_drv.dll` driver
- **Header**: "HX83121-A", date 2022-09-27
- **Variant**: Gaokun-specific (contains "Gaok" sensor string)

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

### Hypothesis
On Detach0-0's Windows system, the **proprietary Himax driver** (from `himax_thp_drv.dll`) loads firmware to code SRAM via SPI using an unknown protocol. After that, GPIO reset preserves SRAM contents, and boot ROM re-validates/restarts FW. EGoTouchRev only does the reset+check, not the initial FW load.

## TDDI Coupling Warning

**CRITICAL**: The HX83121A is a TDDI IC. Resetting via GPIO 99 also resets the display controller:
- DSI link errors (byte_clk stuck)
- Display goes black
- Requires full system reboot to recover

Never reset GPIO 99 while the display is active!

## Possible Next Approaches

### Approach A: Ask Detach0-0
Key questions:
1. Is IC status already 0x05 when EGoTouchRev starts?
2. Does the Windows proprietary driver load FW first?
3. After cold reboot, does your driver work without Windows loading FW?
4. Is code SRAM populated before your first GPIO reset?

### Approach B: Cold Power Cycle Test
Full shutdown → power on → immediately check flash persistence and boot ROM behavior.
Boot ROM may only trigger on Power-On Reset (POR), not on GPIO reset.

### Approach C: Windows Warm Reboot
Boot Windows (FW loaded to SRAM) → warm reboot to Linux without resetting GPIO 99 → SRAM may retain firmware.

### Approach D: Reverse Windows DLL
The `himax_thp_drv.dll` contains firmware download code. It may use a special SPI command that bypasses the AHB bridge to write directly to code SRAM.

### Approach E: UEFI Application
Write a custom UEFI app that loads touch firmware before Linux boots, using raw MMIO SPI access.

### Approach F: Community / Upstream
- [linux-gaokun](https://github.com/right-0903/linux-gaokun) project tracks MateBook E Go Linux support
- [awarson2233/EGoTouchRev-rebuild](https://github.com/awarson2233/EGoTouchRev-rebuild) — reference Windows driver
- Wait for community progress or contribute findings

## References

- [EGoTouchRev-rebuild](https://github.com/awarson2233/EGoTouchRev-rebuild) — Windows ARM64 userspace touch driver
- [MiCode/Xiaomi_Kernel_OpenSource (dagu-s-oss)](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/dagu-s-oss/drivers/input/touchscreen/hxchipset) — Himax hxchipset driver with full firmware download
- `drivers/input/touchscreen/himax_hx83112b.c` — Kernel Himax I2C driver (no FW download)
