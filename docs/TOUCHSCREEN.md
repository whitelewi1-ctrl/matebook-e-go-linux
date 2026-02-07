# Touchscreen Research Notes

## Status: Not Working (SPI driver needed)

The MateBook E Go's touchscreen uses the **Himax HX83121A** touch controller IC (integrated into the display driver IC). It communicates over **SPI**, not I2C. The current DTS incorrectly configures it as HID-over-I2C, and the touch IC does not respond on the I2C bus.

## Hardware

| Parameter | Value |
|-----------|-------|
| Touch IC | Himax HX83121A (same IC as display driver) |
| Bus | **SPI** (GENI SE4 at 0x990000) |
| Architecture | Master/Slave dual-IC |
| Touch matrix | 36 RX x 18 TX electrodes |
| Max touch points | 10 |
| Interrupt GPIO | tlmm 175 (active low) |
| Reset GPIO | tlmm 99 (active low) |
| Power supply | vreg_misc_3p3 (VCC3B), vreg_s10b |

## Evidence That It's SPI, Not I2C

1. **i2cdetect shows no devices** on i2c-4 (bus at 0x990000) -- the touch IC does not ACK any I2C address
2. **Windows driver uses SPI** -- Huawei's `HuaweiThpService.exe` communicates via `SPBTESTTOOL` kernel driver using SPI opcodes (0xF2/0xF3 for Master, 0xF4/0xF5 for Slave)
3. **The GENI SE at 0x990000 supports both I2C and SPI** -- only one mode can be active. The DTS currently enables `i2c@990000` and disables `spi@990000`
4. **The [EGoTouchRev-rebuild](https://github.com/awarson2233/EGoTouchRev-rebuild) project** successfully communicates with the touch IC using SPI on Windows

## SPI Protocol (from EGoTouchRev reverse engineering)

### Bus Framing

Each SPI transaction starts with an opcode byte:

| Opcode | Direction | Target |
|--------|-----------|--------|
| 0xF2 | Write | Master |
| 0xF3 | Read | Master |
| 0xF4 | Write | Slave |
| 0xF5 | Read | Slave |

**Read format**: `[opcode] [cmd] [dummy] [data...]`
**Write format**: `[opcode] [cmd] [addr(4, optional)] [data...]`

### Register Access via AHB Bridge

The touch IC uses an AHB bus bridge for register access:

| Command | Address | Purpose |
|---------|---------|---------|
| cmd 0x00 | -- | Set target AHB address (4 bytes) |
| cmd 0x08 | -- | Read AHB data |
| cmd 0x0C | -- | Set AHB direction (0x00=read) |
| cmd 0x0D | -- | Burst mode (0x12=off, 0x13=on) |
| cmd 0x13 | -- | Continuous mode (0x31=enable) |
| cmd 0x31 | -- | Safe mode ({0x27,0x95}=enter, {0x00,0x00}=exit) |

### Key Register Map

| Register | Address | Purpose |
|----------|---------|---------|
| System Reset | 0x90000018 | Write 0x55 for SW reset |
| FW ISR Control | 0x9000005C | Write 0xA5 for FW stop |
| Status Check | 0x900000A8 | Read: 0x05 = active |
| Chip ID | 0x900000D0 | HX83121A identification |
| Flash Reload | 0x100072C0 | Read: 0xC072 = reload done |
| Raw Out Select | 0x100072EC | 0xF6=rawdata, 0x0A=idle |
| Sorting Mode | 0x10007F04 | 0x0000=normal, 0x2222=open |
| FW Version | 0x10007004 | Firmware version |
| RX/TX Count | 0x100070F4 | Panel electrode count |
| Resolution | 0x100070FC | X/Y resolution |
| SRAM Raw Data | 0x10000000 | Raw frame data start |

### Frame Format

- **Master frame**: 5063 bytes = 7 header + 4800 heatmap (40x60 grid, 16-bit) + 256 status table
- **Slave frame**: 339 bytes (pen/noise data)
- **Status table** (last 256 bytes of master frame): contains processed touch coordinates and stylus data

### Init Sequence (sense_on)

1. Enter safe mode (`{0x27, 0x95}` to cmd 0x31)
2. Set N frame count
3. Disable flash reload
4. Switch mode (0x0000=normal to 0x10007F04)
5. Hardware/software reset
6. Wait for flash reload (0xC072 at 0x100072C0)
7. Set raw data type (0xF6 to 0x100072EC)
8. Write SRAM password (0x5AA5)
9. Exit safe mode

## DTS Changes Needed

To enable SPI touchscreen, the DTS would need:

```dts
/* Disable I2C mode */
&i2c4 {
    status = "disabled";
};

/* Enable SPI mode on the same GENI SE */
&spi4 {
    status = "okay";
    pinctrl-0 = <&ts0_default>;
    pinctrl-names = "default";

    touchscreen@0 {
        compatible = "himax,hx83121a-ts";  /* needs new driver */
        reg = <0>;
        spi-max-frequency = <10000000>;     /* TBD - check Windows SPI clock */
        interrupts-extended = <&tlmm 175 IRQ_TYPE_LEVEL_LOW>;
        reset-gpios = <&tlmm 99 GPIO_ACTIVE_LOW>;
        vdd-supply = <&vreg_misc_3p3>;
        vddl-supply = <&vreg_s10b>;
    };
};
```

## Linux Driver Options

### Option 1: Adapt existing `himax_hx83112b.c`

The kernel has `drivers/input/touchscreen/himax_hx83112b.c` for a related Himax IC. However:
- It only supports I2C transport
- The HX83121A uses a different register set (on-cell vs in-cell)
- Would need significant modifications for SPI + dual Master/Slave

### Option 2: Port EGoTouchRev to Linux kernel module

The EGoTouchRev project has detailed SPI protocol, register maps, and init sequences. Key gaps:
- **Coordinate extraction** -- currently reads raw heatmap, not processed coordinates
- **Normal mode** -- hasn't found the register sequence for DSP-processed coordinates
- **VHF/input reporting** -- no code for injecting touch events

### Option 3: Write a new SPI HID driver

If the touch IC supports HID-over-SPI (Microsoft's HIDSPI protocol), a `hid-over-spi` style driver could work. However:
- The IC likely uses a proprietary protocol, not standard HIDSPI
- The EGoTouchRev reverse engineering suggests a custom Himax protocol

### Option 4: Userspace driver via spidev

Quick prototyping path:
1. Enable `spi@990000` with a `spidev` compatible node
2. Use `spidev` from userspace to send the SPI commands from EGoTouchRev
3. Once communication is verified, develop a proper kernel driver

## Recommended Next Steps

1. **Switch GENI SE to SPI mode** in DTS and verify basic SPI communication using `spidev`
2. **Port the EGoTouchRev init sequence** to a Linux test script
3. **Read the touch IC chip ID** (0x900000D0) to confirm communication
4. **Investigate the status table** (last 256 bytes of master frame) -- it may contain processed coordinates
5. **Check if the IC supports I2C at all** -- some HX83121A variants might have I2C disabled in firmware

## References

- [EGoTouchRev-rebuild](https://github.com/awarson2233/EGoTouchRev-rebuild) -- Windows userspace driver with reverse-engineered SPI protocol
- `drivers/input/touchscreen/himax_hx83112b.c` -- Kernel Himax I2C driver (related IC)
- `drivers/hid/hid-goodix-spi.c` -- Example SPI touchscreen HID driver
- Himax HX83121A -- Display + touch integrated controller IC
