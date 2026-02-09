# Touchscreen Research Notes

## Status: Not Working (I2C reads OK, writes blocked, firmware download impossible)

The MateBook E Go's touchscreen uses the **Himax HX83121A** TDDI (Touch & Display Driver Integration) IC. It communicates over **I2C** (not SPI as initially thought). I2C AHB register reads work perfectly, but **all AHB writes via I2C are silently discarded**, making firmware download to SRAM impossible through this path.

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

## Confirmed I2C Communication

### What Works (I2C AHB Reads)
- **IC ID**: 0x83121A00 at register 0x900000D0
- **Chip Status**: 0x05 (ACTIVE) at 0x900000A8
- **Handshake**: 0xF8 at 0x900000AC
- **FW Version**: 0x4103C20F at 0x10007004
- **HW ID**: 0x04390208 at 0x10007010
- **Sensor Name**: "Gaok" (Gaokun) at 0x10007014
- **Sorting Mode**: 0x9999 at 0x10007F04 — **IC is requesting firmware download**
- **SRAM**: All 0x78 at 0x08000000 — firmware not loaded (zero-flash)
- **Touch event data**: cmd 0x30 reads 56 bytes event buffer
- **Burst read**: Works correctly for multi-register reads

### What Does NOT Work (I2C AHB Writes)
**ALL writes via I2C are silently discarded.** Tested exhaustively:

| Address Region | Purpose | Write Result |
|---|---|---|
| 0x08000000 | SRAM (firmware target) | FAIL - reads back 0x78787878 |
| 0x10007xxx | FW registers | FAIL - values unchanged |
| 0x900000xx | IC control registers | FAIL - values unchanged |
| 0x80000xxx | SPI200 registers | FAIL |
| 0x80050xxx | Flash controller | FAIL |

**Tested write methods** (all failed):
1. Standard: bus_cmd 0x0C=0x01 (direction=write), then 0x08=[data]
2. After software reset (0x55 to 0x90000018) + AHB enable (0x11=0x01)
3. After GPIO reset (gpio99 toggle) + AHB enable
4. With WDT disable + flash reload disable
5. With password (bus_cmd 0x31=0xA5)
6. Skip direction cmd, write directly to 0x08
7. Combined addr+data in one transaction
8. Various direction values (0x01, 0x02, 0x03, 0x10, 0x80, 0xFF)

**Conclusion**: The I2C AHB bridge on this HX83121A variant appears to be hardware read-only.

## SPI Investigation

### SPI6 (GPIO 154-157) — FAILED
- DTS modified: removed GPIO 154-157 from reserved, added spi6 pinctrl (qup6 function)
- spi-geni-qcom driver probed successfully, /dev/spidev0.0 created
- GPIO state confirmed correct: func=qup6(1), drive=6mA, CS output-high
- **All SPI transfers return 0x00** regardless of mode (0-3), speed (100KHz-10MHz), or read method
- **Conclusion**: GPIO 154-157 are likely NOT physically connected to the touch IC

### SPI4 (GPIO 171-174) — N/A
- GPIO 171-172 = I2C SDA/SCL (connected, confirmed working)
- GPIO 173-174 = would be SPI CLK/CS, but spi-gpio test showed MISO stuck HIGH
- GENI SE4 proto=3 (I2C), cannot be changed at runtime (no qupv3fw.elf on sc8280xp)
- **Conclusion**: SE4 only has I2C lines connected, SPI lines (CLK/CS) not routed

## Previous Incorrect Assumptions (Corrected)

1. ~~"SPI, not I2C"~~ → **I2C works for reads, SPI doesn't work at all**
2. ~~"i2cdetect shows no devices"~~ → **i2cdetect works after toggling reset GPIO**
3. ~~"GENI SE supports both I2C and SPI"~~ → **SE4 is locked to I2C by bootloader**
4. ~~"EGoTouchRev SPI protocol"~~ → **That's Windows SPBTESTTOOL framework framing, not raw SPI**

## Zero-Flash Architecture

The HX83121A is a "zero-flash" TDDI IC:
- SRAM at 0x08000000 is empty (0x78 pattern) after boot
- `sorting_mode = 0x9999` confirms IC is in "awaiting firmware" state
- Firmware must be downloaded from host on every boot
- **Problem**: firmware download requires SRAM writes, which don't work over I2C

### Extracted Firmware
- **Source**: `himax_thp_drv.dll` from Windows driver package
- **File**: `/tmp/gaokun_thp/hx83121a_gaokun_fw.bin` (261,120 bytes)
- **Variant**: Gaokun-specific (contains "Gaok" sensor string)
- **Structure**: Standard Himax zero-flash format with CRC sections

## AHB Bridge Protocol (I2C)

The bus command protocol is identical to EGoTouchRev's SPI protocol but over I2C:

```
Bus Commands (first byte of I2C write):
  0x00 [addr3 addr2 addr1 addr0]  - Set AHB target address (LITTLE ENDIAN!)
  0x08 [data...]                   - Read/write data
  0x0C [dir]                       - Direction: 0x00=read, 0x01=write (writes don't work)
  0x0D [val]                       - INCR4: 0x10=enable
  0x11 [val]                       - AHB enable: 0x01
  0x13 [val]                       - CONTI: 0x31=enable
  0x30                             - Read event data (56 bytes)
  0x31 [val]                       - Safe mode / password

Read sequence:
  burst_enable() → bus_write(0x00, LE_addr) → bus_write(0x0C, 0x00) → bus_read(0x08, N)

Write sequence (DOES NOT WORK on this IC):
  burst_enable() → bus_write(0x00, LE_addr) → bus_write(0x0C, 0x01) → bus_write(0x08, data)
```

## Key Register Map

| Register | Address | Read Value | Purpose |
|----------|---------|------------|---------|
| IC ID | 0x900000D0 | 0x83121A00 | Chip identification |
| Chip Status | 0x900000A8 | 0x05 | 0x05=ACTIVE |
| Handshake | 0x900000AC | 0xF8 | Boot handshake |
| System Reset | 0x90000018 | - | Write 0x55 for reset (if writes worked) |
| FW ISR Control | 0x9000005C | - | Write 0xA5 for FW stop |
| FW Version | 0x10007004 | 0x4103C20F | Firmware version |
| HW ID | 0x10007010 | 0x04390208 | Hardware ID |
| Sensor Name | 0x10007014 | "Gaok" | Sensor variant |
| Sorting Mode | 0x10007F04 | 0x9999 | 0x9999=awaiting FW |
| Flash Reload | 0x100072C0 | varies | Reload status |
| SRAM Base | 0x08000000 | 0x78787878 | Firmware target (empty) |

## Possible Next Approaches

### Approach 1: I2C HID Protocol
The HX83121A might support I2C HID natively when firmware IS loaded (by UEFI).
- UEFI loads touch firmware during boot → touch works in UEFI
- If Linux panel driver skips re-init (skip_init=1), UEFI FW stays active
- Try reading I2C HID descriptor from register 0x0001
- Script: `/tmp/touch_i2c_hid_test.py` (not yet run)

### Approach 2: Preserve UEFI Touchscreen State
- Boot with panel driver `skip_init=1` to avoid re-initializing the TDDI
- UEFI already downloads firmware and enables touch
- The I2C HID interface might already be active
- Risk: display timing might not match Linux expectations

### Approach 3: DSI Command-Based Firmware Download
- The panel driver already sends DSI commands successfully to both links
- The HX83121A might accept firmware data via DSI generic/DCS commands
- This bypasses the I2C AHB write limitation entirely
- Needs research into Himax DSI firmware download protocol

### Approach 4: Investigate Windows Driver More Deeply
- Check if Windows himax_thp_drv.dll uses a different I2C write mechanism
- Check if there's an I2C "unlock" sequence before writes
- Check if Windows uses DMA or a different bus master for SRAM writes

### Approach 5: Contact linux-gaokun Maintainers
- The gaokun3 DTS already has touch IC entries, implying someone has worked on this
- Ask about their touchscreen experience and any unlisted patches

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
- Service `/etc/systemd/system/disable-blanking.service` prevents console blanking

## DTS Changes Made (2026-02-09)

```dts
/* 1. Removed GPIO 154-157 from reserved ranges */
gpio-reserved-ranges = <70 2>, <74 6>, <83 4>, <125 2>, <128 2>;
/* was: ... <128 2>, <154 4>; */

/* 2. Added spi6 pinctrl */
spi6_default: spi6-default-state {
    spi-pins {
        pins = "gpio154", "gpio155", "gpio156";
        function = "qup6";
        drive-strength = <6>;
        bias-disable;
    };
    cs-pins {
        pins = "gpio157";
        function = "qup6";
        drive-strength = <6>;
        bias-disable;
        output-high;
    };
};

/* 3. Enabled spi6 with spidev */
&spi6 {
    pinctrl-0 = <&spi6_default>;
    pinctrl-names = "default";
    status = "okay";
    spidev@0 {
        compatible = "rohm,dh2228fv";
        reg = <0>;
        spi-max-frequency = <10000000>;
    };
};
```

**Result**: SPI6 probed but returns all zeros. These changes may need to be reverted.

## References

- [EGoTouchRev-rebuild](https://github.com/awarson2233/EGoTouchRev-rebuild) — Windows userspace driver with reverse-engineered SPI protocol
- `drivers/input/touchscreen/himax_hx83112b.c` — Kernel Himax I2C driver (related IC)
- `drivers/input/touchscreen/himax_hx852x.c` — Simpler Himax I2C driver
- `drivers/hid/hid-goodix-spi.c` — Example SPI touchscreen HID driver
- Himax HX83121A — Display + touch integrated controller IC (TDDI)
