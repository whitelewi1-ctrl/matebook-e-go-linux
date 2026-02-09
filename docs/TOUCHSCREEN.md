# Touchscreen Research Notes

## Status: Not Working (I2C partial writes OK, but code SRAM hardware read-only)

The MateBook E Go's touchscreen uses the **Himax HX83121A** TDDI (Touch & Display Driver Integration) IC. It communicates over **I2C** via an AHB bridge. After discovering the I2C password unlock sequence, we confirmed that **IC registers, FW registers, and data SRAM (0x20000000) are writable**, but **code SRAM (0x08000000) remains hardware read-only** via I2C. Since firmware code (~126KB) must be loaded into code SRAM, I2C firmware download is impossible. SPI is the only write path to code SRAM, but SPI lines are not physically connected on this device.

## Hardware

| Parameter | Value |
|-----------|-------|
| Touch IC | Himax HX83121A (same IC as display driver - TDDI) |
| Bus | **I2C** via GENI SE4 at 0x990000 (proto=3=I2C, set by bootloader) |
| I2C Addresses | 0x48 (Master IC), 0x49 (Slave IC) |
| Architecture | Master/Slave dual-IC |
| Touch matrix | 36 RX x 18 TX electrodes |
| Max touch points | 10 |
| Interrupt GPIO | tlmm 175 (active low) |
| Reset GPIO | tlmm 99 (active low) — **WARNING: resets display too (TDDI)** |
| I2C SDA/SCL | GPIO 171/172 (qup4 function) |
| Power supply | vreg_misc_3p3 (VCC3B), vreg_s10b |

### ACPI-Defined Interfaces (from Windows DSDT)

The DSDT defines three mutually exclusive touch interfaces, selected by firmware at boot:

| ACPI Device | HID | Bus | Description |
|-------------|-----|-----|-------------|
| THPA (HIMX0001) | SPI6 | GPIO 154-157, 12MHz | Main touch (SPI) |
| THPB (HIMX0002) | SPI20 | GPIO 87-90, 12MHz | Stylus (SPI) |
| HIMX (HIMX1234) | I2C4 | addr 0x4F, 1MHz | I2C HID (PNP0C50) |

**Note**: I2C HID address 0x4F is for HID event interface; 0x48 is for AHB bridge register/firmware access.

## I2C AHB Bridge Protocol

### Bus Commands

```
Bus Commands (first byte of I2C write):
  0x00 [addr_LE(4B)] [data_LE(4B)]  - AHB address + optional write data (combined format)
  0x08 [data...]                      - Read data register
  0x0C [dir]                          - Direction: 0x00=read (for 3-step read)
  0x0D [val]                          - INCR4: 0x12=enable (NOTE: 0x12 for HX83121, not 0x10!)
  0x11 [val]                          - AHB enable: 0x01
  0x13 [val]                          - CONTI: 0x31=enable
  0x30                                - Read event data (56 bytes)
  0x31 [val]                          - I2C password byte 1 (0x27 for safe mode)
  0x32 [val]                          - I2C password byte 2 (0x95 for safe mode)
```

### AHB Read Sequence (3-step)
```
burst_enable()  →  i2c_write([0x00] + addr_LE)
                →  i2c_write([0x0C, 0x00])         # direction = read
                →  i2c_write_read([0x08], 4)        # read 4 bytes
```

### AHB Write Sequence (combined format)
```
burst_enable()  →  i2c_write([0x00] + addr_LE + data_LE)   # 9 bytes total
```

**Important**: Writes use the "combined format" — address and data in a single I2C transaction with bus command 0x00. The 3-step write method (direction=0x01 + cmd 0x08) does NOT work.

### Burst Enable
```
i2c_write([0x13, 0x31])   # CONTI enable
i2c_write([0x0D, 0x12])   # INCR4 enable (0x12 for HX83121!)
```

### I2C Password Unlock (Safe Mode Entry)
```
i2c_write([0x31, 0x27])   # password byte 1
i2c_write([0x32, 0x95])   # password byte 2
# Wait 50ms, then verify: chip_status (0x900000A8) byte0 == 0x0C
```

After password unlock, IC registers, FW registers, and data SRAM become writable.

## AHB Writability Map (After Password Unlock)

| Address Region | Size | Read | Write | Purpose |
|---|---|---|---|---|
| 0x00000000 - 0x0001FFFF | 128KB | OK | **NO** | Boot ROM (read-only) |
| 0x08000000 - 0x0801FFFF | 128KB | OK | **NO** | Code SRAM (firmware target) |
| 0x10007000 - 0x10007FFF | 4KB | OK | **YES** | FW config registers |
| 0x20000000 - 0x2001FFFF | 128KB | OK | **YES** | Data SRAM |
| 0x80020000 - 0x80050xxx | varies | OK | **YES** | TCON / SPI200 / Flash controller |
| 0x90000000 - 0x900000FF | 256B | OK | **YES** | IC control registers |
| 0xE000E000 - 0xE000EFFF | 4KB | **NO** (returns 0) | **NO** | Cortex-M PPB (not accessible via AHB bridge) |

### Code SRAM: Exhaustive Write Testing

All of the following methods were tested and **none** could write to code SRAM (0x08000000):

1. Combined write `[0x00][addr][data]` after password unlock
2. All bus commands 0x00-0x16 with addr+data payload
3. Direction=0x01 + cmd 0x08 (3-step write)
4. After system reset (0x55 to 0x90000018) + safe mode
5. After TCON reset + ADC reset (sense_off sequence)
6. With activ_relod register = 0xEC
7. With disable_flash_reload = 0x9AA9
8. Via slave address 0x49 (same IC, same restriction)
9. Without burst mode
10. All INCR4 values (0x00-0xFF)
11. SPI200 indirect write
12. Writing to 0x00000xxx (boot ROM alias) — different memory, also read-only
13. Cortex-M VTOR remapping to 0x20000000 — PPB registers not accessible

**Conclusion**: Code SRAM is hardware read-only via the I2C AHB bridge. This is a silicon-level restriction, not a software/configuration issue.

### Data SRAM: Writable (with limitations)

Data SRAM at 0x20000000 (128KB) IS writable via I2C:
- **Single-word (4B) writes**: 100% reliable (verified 256/256 consecutive writes)
- **Burst writes**: Fail (only last word takes effect)
- **Write speed**: ~3,300 bytes/sec (limited by I2C transaction overhead)
- **Region size**: 128KB (0x20000000 - 0x2001FFFF)
- **Not aliased**: 0x20000000 and 0x08000000 are separate memory regions

## Firmware Analysis

### Firmware Binary
- **File**: `hx83121a_gaokun_fw.bin` (261,120 bytes / 0x3FC00)
- **Source**: Extracted from Windows `himax_thp_drv.dll` driver
- **Header**: "HX83121-A", date 2022-09-27
- **Variant**: Gaokun-specific (contains "Gaok" sensor string)

### Partition Table (at firmware offset 0x20030)

Format: 16-byte header + 16-byte entries: `[sram_addr(4)][size(4)][fw_offset(4)][flags(4)]`

| # | SRAM Address | Size | FW Offset | Type |
|---|---|---|---|---|
| 0 | 0x00000400 | 8,192 | 0x00080 | Code (→ 0x08000400) |
| 1 | 0x00002400 | 109,568 | 0x02080 | Code (→ 0x08002400) |
| 2 | 0x0001CE00 | 5,376 | 0x1C880 | Code (→ 0x0801CE00) |
| 3 | 0x0001E300 | 5,376 | 0x1DD80 | Code (→ 0x0801E300) |
| 4 | 0x0001F800 | 1,024 | 0x1F280 | Code (→ 0x0801F800) |
| 5 | 0x10007000 | 120 | 0x1F680 | Config (FW regs) |
| 6 | 0x10007084 | 528 | 0x1F700 | Config (FW regs) |
| 7 | 0x10007300 | 180 | 0x1F910 | Config (FW regs) |
| 8 | 0x100072F0 | 16 | 0x1F9C8 | Config (FW regs) |
| 9 | 0x100073F0 | 32 | 0x1F9D8 | Config (FW regs) |

- **Code partitions (0-4)**: ~126KB total → must go to code SRAM (0x08000xxx) — **NOT writable via I2C**
- **Config partitions (5-9)**: ~876 bytes total → go to FW registers (0x10007xxx) — writable via I2C

**Note**: Partition table addresses (0x00000400 etc.) map to code SRAM. The Xiaomi hxchipset driver source confirms these addresses go to SRAM region 0x08000xxx on the Cortex-M memory map.

## Key Register Map

| Register | Address | Read Value | Purpose |
|----------|---------|------------|---------|
| IC ID | 0x900000D0 | 0x83121A00 | Chip identification |
| Chip Status | 0x900000A8 | 0x05/0x0C | 0x05=ACTIVE, 0x0C=SAFE_MODE |
| Handshake | 0x900000AC | 0xF8 | Boot handshake |
| System Reset | 0x90000018 | writable | Write 0x55 to reset touch IC CPU |
| FW ISR Control | 0x9000005C | writable | Write 0xA5 for FW stop |
| FW Version | 0x10007004 | 0x4103C20F | Firmware version |
| HW ID | 0x10007010 | 0x04390208 | Hardware ID |
| Sensor Name | 0x10007014 | "Gaok" | Sensor variant |
| Sorting Mode | 0x10007F04 | 0x9999 | 0x9999=awaiting FW, 0x0909=after reset |
| Flash Reload | 0x10007F00 | varies | Write 0x9AA9 to disable flash reload |
| SRAM Base | 0x08000000 | 0x78787878 | Firmware target (empty) |
| Data SRAM | 0x20000000 | varies | Writable 128KB data SRAM |

## SPI Investigation

### SPI6 (GPIO 154-157) — NOT CONNECTED
- DTS modified: removed GPIO 154-157 from reserved, added spi6 pinctrl (qup6 function)
- spi-geni-qcom driver probed successfully, /dev/spidev0.0 created
- GPIO state confirmed correct: func=qup6(1), drive=6mA, CS output-high
- **All SPI transfers return 0x00** regardless of mode (0-3), speed (100KHz-10MHz)
- **Conclusion**: GPIO 154-157 are NOT physically connected to the touch IC

### SPI20 (GPIO 87-90) — NOT CONNECTED
- GPIO state: mux=0 (GPIO mode), not configured for any QUP function
- **Conclusion**: Not connected, likely for optional stylus digitizer

### SPI4 (GPIO 171-174) — I2C ONLY
- GPIO 171-172 = I2C SDA/SCL (connected, confirmed working)
- GENI SE4 proto=3 (I2C), cannot be changed at runtime (no qupv3fw.elf on sc8280xp)
- **Conclusion**: SE4 only has I2C lines connected

## Possible Next Approaches

### Approach A: Dual-Boot Warm Reboot
Windows loads touch firmware into SRAM on every boot. If we:
1. Boot Windows (firmware loaded into code SRAM)
2. Warm reboot to Linux without resetting GPIO 99
3. Code SRAM may retain firmware content

**Risk**: SRAM content may not survive warm reboot; UEFI may reset touch IC.

### Approach B: UEFI Application
Write a custom UEFI application that:
1. Opens the I2C controller in SPI mode (or uses raw MMIO)
2. Downloads firmware to code SRAM before Linux boots
3. Uses the SPI protocol which CAN write to code SRAM

**Advantage**: Runs before Linux, can use any hardware interface.
**Challenge**: UEFI SPI access on sc8280xp is undocumented.

### Approach C: Re-examine SPI Physical Connections
- Use multimeter/oscilloscope to trace GPIO 154-157 physical routes
- Check if there's an alternate QUP/GPIO combination for SPI to the touch IC
- The ACPI DSDT says THPA uses SPI6 — firmware expects it to work

### Approach D: Community / Upstream Progress
- The [linux-gaokun](https://github.com/right-0903/linux-gaokun) project tracks MateBook E Go Linux support
- Wait for upstream Himax TDDI driver with firmware download support
- Contribute findings to help others working on this device

### Approach E: I2C HID (Partial Touch Without FW Download)
- UEFI may leave touch active if we don't reset the TDDI
- I2C HID descriptor at address 0x4F, register 0x0001
- Requires `skip_init=1` in panel driver to avoid re-initializing TDDI
- **Risk**: Display timing might not match; UEFI may not initialize touch on every boot

## TDDI Coupling Warning

**CRITICAL**: The HX83121A is a TDDI (Touch & Display Driver Integration) IC. Resetting the touch controller via GPIO 99 also resets the display controller, causing:
- DSI link errors (byte_clk stuck)
- Display goes black
- Requires full system reboot to recover

Never reset GPIO 99 while the display is active!

## Display Blanking Issue

GNOME/GDM has a 5-minute screen timeout that triggers DPMS Off, which crashes the DSI clocks:
- `consoleblank=0` kernel parameter only affects fbcon, not enough
- Must disable GDM (`systemctl disable gdm`) during touchscreen debugging
- Or use `xset s off -dpms` / `gsettings set org.gnome.desktop.session idle-delay 0`

## References

- [EGoTouchRev-rebuild](https://github.com/awarson2233/EGoTouchRev-rebuild) — Windows userspace driver with reverse-engineered SPI protocol
- [MiCode/Xiaomi_Kernel_OpenSource (dagu-s-oss)](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/dagu-s-oss/drivers/input/touchscreen/hxchipset) — Himax hxchipset driver with full firmware download implementation
- `drivers/input/touchscreen/himax_hx83112b.c` — Kernel Himax I2C driver (no FW download)
- Himax HX83121A — Display + touch integrated controller IC (TDDI)
