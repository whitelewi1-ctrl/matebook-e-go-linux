# Huawei MateBook E Go Windows Drivers

Official Huawei Windows ARM64 drivers for MateBook E Go tablets.

## GK-W7X (Snapdragon 8cx Gen 3)

| File | Version | Description |
|------|---------|-------------|
| `Gaokun_THP_Software_1.0.1.39.exe` | 1.0.1.39 | Touchscreen THP driver (contains HX83121A firmware + TSACore algorithm) |
| `Gaokun_Audio_1.0.1880.1.exe` | 1.0.1880.1 | Audio driver |
| `Gaokun_8CX_BIOS_P02-02W-06F_2.16.exe` | 2.16 | BIOS/UEFI update (8cx Gen 3, GK-W7X) |
| `Gaokun_WiFi_1.0.1760.22.exe` | 1.0.1760.22 | WiFi driver (WCN6855) |
| `Gaokun_Raven_Keyboard_1.0.0.39.exe` | 1.0.0.39 | Keyboard cover driver |
| `Gaokun_MCUSoftware_1.0.0.40.exe` | 1.0.0.40 | EC MCU firmware |

## GK-X5X (Snapdragon 8cx Gen 2)

| File | Version | Description |
|------|---------|-------------|
| `Gaokun_8C_BIOS_P02-02W-05H_2.17.exe` | 2.17 | BIOS/UEFI update (8cx Gen 2, GK-X5X) |

## Notes

- These are self-extracting Windows installers (ARM64)
- The THP driver is particularly important for touchscreen research — it contains `himax_thp_drv.dll` with embedded HX83121A firmware and `TSACore.dll` for touch coordinate calculation
- All drivers are from Huawei's official distribution package (`Gaokun-W7821T_3.222.0.7_C233.zip`)
