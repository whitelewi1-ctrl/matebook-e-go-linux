# UEFI DXE Touch Diff (2.16 vs 2.17)

## Inputs
- `2.16`: `/tmp/uefi-216/GKQ83216.bin`
- `2.17`: `/tmp/uefi-217/GKQ82217.bin`
- Tooling: `uefiextract` (UEFITool NE A66, CLI)

## Extraction Method
1. Full tree dump:
   - `uefiextract GKQ83216.bin all`
   - `uefiextract GKQ82217.bin all`
2. Locate DXE modules in dump tree by UI name/GUID.
3. Export PE32 payload from `1 PE32 image section/body.bin`.
4. Compare module hash/size.

Export location in repo:
- `docs/uefi_extracted/216/*`
- `docs/uefi_extracted/217/*`

## Key Findings
- `WinAcpiUpdate` exists in `2.16` but is missing in `2.17`.
- Touch/display related DXE modules are all changed between `2.16` and `2.17` (all hash-different):
  - `TouchPanelInit`
  - `I2cTouchPanel`
  - `I2C`
  - `SPI`
  - `GpioConfigDxe`
  - `AcpiPlatform`
  - `DisplayDxe`
- `TouchPanelInit` GUID is the same in both versions:
  - `8C88DA42-7CA9-40B6-9FD3-473B8A19525A`
- `I2cTouchPanel` GUID is the same in both versions:
  - `8C88DA42-7CA9-40B6-9FD3-473B8A77CC5A`

## Module Comparison

| Module | 2.16 size | 2.17 size | Status |
|---|---:|---:|---|
| AcpiPlatform | 77824 | 53248 | DIFF |
| DisplayDxe | 659456 | 483328 | DIFF |
| GpioConfigDxe | 28672 | 28672 | DIFF |
| I2C | 40960 | 36864 | DIFF |
| I2cTouchPanel | 36864 | 32768 | DIFF |
| SPI | 49152 | 40960 | DIFF |
| TouchPanelInit | 28672 | 28672 | DIFF |
| WinAcpiUpdate | 36864 | MISSING | REMOVED in 2.17 |

## Hash Snapshot
- `TouchPanelInit`
  - 2.16: `77d62aa196f002e949c59134cc9b5eea4a57a9c24acdb3541818f24b706c4a96`
  - 2.17: `97d978880c59ee0dd3a493dedbdb8bd72c0d83af393764d5190256f8ffb383b2`
- `I2cTouchPanel`
  - 2.16: `dcb5dae9171d4d53818e66873807feded591ed5b8368b3014f40265337f95858`
  - 2.17: `722dc95e1130b4f93ade9a20b38b6c4676020f8a431697cd73b5e56171d080fc`
- `DisplayDxe`
  - 2.16: `6c0b3706bd8b1848f91d36f85d30a2e4ddf6d89eabf54ecc5ad734256dd8ac89`
  - 2.17: `89e21d0f058cbde7fd97d9004334de95602e30777f89ff6c0e7def8a70394283`

## Static String Deltas (high-signal)
- `I2cTouchPanel` debug strings differ on GPIO index:
  - 2.16 shows `ConfigGpio 174 ...`
  - 2.17 shows `ConfigGpio 116 ...`
- `TouchPanelInit` build paths differ (Gen3 vs Gen2 CI trees), indicating different branch lineage.
- `WinAcpiUpdate` (2.16 only) contains `_STA` patch paths:
  - `\\_SB.GPU0._STA`
  - `\\_SB.MMU1._STA`
  - `\\_SB.IMM1._STA`
  - `\\_SB.NSP0._STA`
  - `\\_SB.SCSS._STA`
  - `\\_SB.SPSS._STA`

## Interpretation
- The “all-zero SPI read plane” on current runtime can be caused by firmware-side init/gating differences even when Linux-side SPI transport is active.
- The 2.16/2.17 DXE delta is large enough that touch/display sequencing differences are expected, not incidental.
- `WinAcpiUpdate` removal in 2.17 is a concrete firmware policy delta worth tracking against Windows boot behavior and cross-boot side effects.
