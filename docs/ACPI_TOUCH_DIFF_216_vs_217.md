# ACPI Touch Diff: BIOS 2.16 vs 2.17

## Source
- `docs/acpi/DSDT_216.dsl`
- `docs/acpi/DSDT_217.dsl`

## Common logic (same in both)
- Touch split controlled by `DT02`:
  - `THPA._STA` and `THPB._STA`: enabled when `DT02 == 0`
  - `HIMX._STA`: enabled when `DT02 != 0`
- Device IDs:
  - `THPA`: `HIMX0001`
  - `THPB`: `HIMX0002`
  - `HIMX`: `HIMX1234`, `_SUB = HX83121A`, `_CID = PNP0C50`

## DT register backing region
- 2.16: `OperationRegion (T174, SystemMemory, 0x0F1AE000, 0x18)` (`DT02` at +0x4)
- 2.17: `OperationRegion (T116, SystemMemory, 0x03174000, 0x18)` (`DT02` at +0x4)

## THPA (main touch SPI endpoint)
- 2.16:
  - SPI bus: `\\_SB.SPI7`
  - SPI speed: `0x00B71B00` (12 MHz)
  - GPIOs in `_CRS`: reset/io `0x63`, irq `0xAF`, wake `0x08`
- 2.17:
  - SPI bus: `\\_SB.SPI1`
  - SPI speed: `0x00BEBC20` (12.5 MHz)
  - GPIOs in `_CRS`: reset/io `0x36`, irq `0x71`, wake `0x3C`

## THPB (secondary/stylus SPI endpoint)
- 2.16:
  - SPI bus: `\\_SB.SP21`
  - SPI speed: `0x00B71B00` (12 MHz)
  - GPIO irq: `0x27`
- 2.17:
  - SPI bus: `\\_SB.SPI6`
  - SPI speed: `0x00BEBC20` (12.5 MHz)
  - GPIO irq: `0x98`

## HIMX (I2C HID endpoint)
- 2.16:
  - Controller: `\\_SB.I2C5`
  - Address: `0x4F`
  - Bus speed: `0x000F4240` (1 MHz)
  - Includes GPIO IO + IRQ entries
- 2.17:
  - Controller: `\\_SB.I2C2`
  - Address: `0x4F`
  - Bus speed: `0x000F4240` (1 MHz)
  - Includes IRQ entry

## Practical implications
1. `DT02` is read by AML but not written there; setter is likely pre-AML firmware path.
2. 2.16/2.17 touch routing is platform-specific (different SPI/I2C controllers and GPIO numbering).
3. Bringing a 2.17-style software assumption to a 2.16 platform (or vice versa) will mis-target touch buses.
