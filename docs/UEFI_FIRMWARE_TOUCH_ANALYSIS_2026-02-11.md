# UEFI Firmware Touch Analysis (2026-02-11)

## Scope
- Input packages:
  - `drivers/Gaokun_8CX_BIOS_P02-02W-06F_2.16.exe` (NSIS)
  - `drivers/Gaokun_8C_BIOS_P02-02W-05H_2.17.exe` (NSIS)
- Extracted payloads:
  - `/tmp/uefi-216/GKQ83216.bin`
  - `/tmp/uefi-217/GKQ82217.bin`

## Packaging Facts
- Both BIOS updaters are NSIS self-extractors.
- `install.cmd` calls:
  - `QCFirmwareUpdate.exe -SrcFile .\\GKQ83.bin -Force -Verbose` (2.16 path)
  - `QCFirmwareUpdate.exe -SrcFile .\\GKQ82.bin -Force -Verbose` (2.17 path)
- This is a firmware capsule/update flow, not a simple file copy.

## Capsule Format (Parsed)
- `GKQ83216.bin` and `GKQ82217.bin` are valid UEFI FMP capsules:
  - `EFI_CAPSULE_HEADER.CapsuleGuid = 6dcbd5ed-e82d-4c44-bda1-7194199ad92a`
  - `HeaderSize = 0x20`
  - `Flags = 0x50000`
- FMP payload header (`item0 @ 0x30`) confirms `install.cmd` GUID mapping:
  - 2.16 capsule `UpdateImageTypeId = 82315653-fe98-4014-82cf-ef099fa9357c`
  - 2.17 capsule `UpdateImageTypeId = 30769cd2-72ae-4754-ac43-cd5f01a2cd9a`
- These exactly match `flash_guid` values in each `install.cmd`.

## QCFirmwareUpdate Behavior (from binary imports/strings)
- Binary: ARM64 PE (`QCFirmwareUpdate.exe`).
- Key imported APIs:
  - `SetFirmwareEnvironmentVariableW`
  - `GetFirmwareEnvironmentVariableW`
  - file/ESP copy APIs (`CreateFileW`, `CopyFileW`, `WriteFile`, etc.)
- Help/usage strings show modes:
  - `-SrcDir`, `-SrcFile`, `-Force`, `-Verbose`, `-Result`, `-CapName`
- Log strings indicate workflow:
  - validate FMP capsule
  - copy to ESP `EFI\\UpdateCapsule\\`
  - set mass-storage capsule flag
  - process on next reboot
- Observed GUID strings in tool:
  - `39B68C46-F7FB-441B-B6EC-16B0F69821F3`
  - `8BE4DF61-93CA-11D2-AA0D-00E098032B8C` (EFI global variable GUID)

Interpretation: updater stages capsule + sets firmware variables; touch mode control (`DT02`) is still expected to happen in firmware runtime path (XBL/DXE), not in this Windows userspace tool itself.

## UEFI Volume Presence
- Both `GKQ*.bin` contain UEFI firmware volume signatures (`_FVH`), confirming they are real firmware containers.
- Primary volume contains UEFI/XBL/Display/ACPI strings and touch-related AML symbols.

## Direct Touch-Relevant Evidence

### 2.16 (`GKQ83216.bin`)
- `THPA` + `_HID` `HIMX0001`
- `THPB` + `_HID` `HIMX0002`
- `HIMX` + `_HID` `HIMX1234`
- `_SUB` `HX83121A`
- `_CID` `PNP0C50`
- `_STA` conditioned by `DT02`
- Dependency references to `\\_SB_I2C5`, `\\_SB_SPI7`, `\\_SB_SP21` (as seen in extracted AML-like strings)

### 2.17 (`GKQ82217.bin`)
- Same touch topology found:
  - `HIMX0001`, `HIMX0002`, `HIMX1234`
  - `_SUB` `HX83121A`
  - `DT02` + `_STA` gating
- Bus/device references differ from 2.16 in string dump (example offsets show `SPI1/SPI6` and `I2C2/I2C5` names in AML-like text), indicating per-platform ACPI routing differences.

## Additional Correlated Evidence
- UEFI image contains:
  - `UEFI DXE`
  - `DisplayDxe` logs and panel-init error strings
  - DSI/I2C init sequence symbols (`DSIInitSequence`, `I2CInitSequence`)
- Supports the hypothesis that pre-OS display/firmware path is tied to touch controller bring-up state.

## Interpretation
- UEFI definitely contains explicit touch ACPI objects and DT02-based interface switching logic for Himax HX83121A.
- This strongly supports the current root-cause direction: boot-time firmware path (UEFI/XBL/ACPI provisioning or related init order) can decide whether Linux later sees a readable touch register plane.

## Decompiled DSDT Findings (Concrete)

### Files generated
- `docs/acpi/DSDT_216.dat`, `docs/acpi/DSDT_216.dsl`
- `docs/acpi/DSDT_217.dat`, `docs/acpi/DSDT_217.dsl`

### DT02 is read-only in DSDT (both versions)
- 2.16:
  - `OperationRegion (T174, SystemMemory, 0x0F1AE000, 0x18)` at `docs/acpi/DSDT_216.dsl:33580`
  - `DT02` field declaration at `docs/acpi/DSDT_216.dsl:33584`
- 2.17:
  - `OperationRegion (T116, SystemMemory, 0x03174000, 0x18)` at `docs/acpi/DSDT_217.dsl:100578`
  - `DT02` field declaration at `docs/acpi/DSDT_217.dsl:100582`
- No `Store(..., DT02)` or `DT02 = ...` assignment found in either DSDT.
- Conclusion: DSDT only consumes `DT02`; value is likely written by pre-AML firmware stage.

### Touch device `_STA` gating (same logic in both BIOS lines)
- 2.16 devices:
  - `THPA` at `docs/acpi/DSDT_216.dsl:33613`
  - `THPB` at `docs/acpi/DSDT_216.dsl:33676`
  - `HIMX` at `docs/acpi/DSDT_216.dsl:33734`
- 2.17 devices:
  - `THPA` at `docs/acpi/DSDT_217.dsl:100611`
  - `THPB` at `docs/acpi/DSDT_217.dsl:100669`
  - `HIMX` at `docs/acpi/DSDT_217.dsl:100722`
- Logic:
  - `THPA._STA`: `DT02 == 0` -> `0x0F`, else `0x00`
  - `THPB._STA`: `DT02 == 0` -> `0x0F`, else `0x00`
  - `HIMX._STA`: `DT02 == 0` -> `0x00`, else `0x0F`
- Interpretation:
  - `DT02 == 0`: SPI touch path enabled (`HIMX0001/HIMX0002`)
  - `DT02 != 0`: I2C HID path enabled (`HIMX1234`, `PNP0C50`)

### Bus/GPIO mapping differences
- 2.16 (`SDM8280` DSDT):
  - `THPA`: `\\_SB.SPI7`, speed `0x00B71B00` (12 MHz), GPIOs include `0x63/0xAF/0x08`
  - `THPB`: `\\_SB.SP21`, speed `0x00B71B00` (12 MHz), GPIO int `0x27`
  - `HIMX`: `\\_SB.I2C5`, addr `0x4F`, 1 MHz
- 2.17 (`SDM8180` DSDT):
  - `THPA`: `\\_SB.SPI1`, speed `0x00BEBC20` (12.5 MHz), GPIOs include `0x36/0x71/0x3C`
  - `THPB`: `\\_SB.SPI6`, speed `0x00BEBC20` (12.5 MHz), GPIO int `0x98`
  - `HIMX`: `\\_SB.I2C2`, addr `0x4F`, 1 MHz

## Runtime Cross-Check on Target
- Running tablet reports:
  - `bios_vendor = HUAWEI`
  - `bios_version = 2.16`
  - `product_name = GK-W7X`
- So active branch is 2.16 / `GKQ83216`.
- 2.16 DSDT resource map matches Linux-discovered controllers:
  - `SPI7` base `0x00998000` ↔ Linux `998000.spi`
  - `I2C5` base `0x00990000` ↔ Linux `990000.i2c`

## DT register runtime snapshot (read-only)
- Read from `/dev/mem` on target:
  - `DT01..DT06 @ 0x0F1AE000`: `0x3c3, 0x0, 0xe2, 0x0, 0x1, 0x801`
  - Key bit: `DT02 = 0x0` (SPI path selected)
- Attempt to write `DT02` at runtime via `/dev/mem` failed (`EINVAL`), so current kernel setup allows observation but not selector override from userspace.

## Recommended Next Reverse Steps
1. Focus on firmware/XBL/DXE code that populates `DT02` backing memory (`0x0F1AE000+4` for 2.16 branch, `0x03174000+4` for 2.17 branch).
2. Correlate DSDT bus names with current Linux board wiring and active SPI controller (`998000.spi`) to ensure we are targeting the right touch node.
3. Investigate `DisplayDxe` path for side effects that may gate touch readiness before OS handoff.
4. If possible, collect boot-stage logs around DT02 write and touch node initialization.

## DXE Binary Diff Update (2026-02-11, Round 2)
- A full UEFI tree extraction was completed for both versions using:
  - `uefiextract GKQ83216.bin all`
  - `uefiextract GKQ82217.bin all`
- Touch/display-relevant DXE PE32 binaries were exported to:
  - `docs/uefi_extracted/216/*`
  - `docs/uefi_extracted/217/*`
- New detailed diff document:
  - `docs/UEFI_DXE_TOUCH_DIFF_216_vs_217.md`

### High-confidence binary facts
- `WinAcpiUpdate` is present in 2.16 and absent in 2.17.
- All key modules are hash-different between 2.16 and 2.17:
  - `TouchPanelInit`, `I2cTouchPanel`, `I2C`, `SPI`, `GpioConfigDxe`, `AcpiPlatform`, `DisplayDxe`
- `TouchPanelInit` and `I2cTouchPanel` keep the same GUIDs across versions, but PE payload changes.

### Why this matters for current issue
- This confirms firmware touch/display init logic did change materially between BIOS lines.
- It supports the hypothesis that current “SPI transport alive but all-zero payload” can originate from firmware-side init state, not only Linux driver framing.
