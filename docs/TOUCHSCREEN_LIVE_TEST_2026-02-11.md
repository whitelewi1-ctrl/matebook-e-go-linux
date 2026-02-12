# Touchscreen Live Test Log (2026-02-11)

## Scope
- Device: MateBook E Go (GK-W7X)
- Host access: SSH to `whitelewis@192.168.1.74`
- Goal: Validate current touchscreen bring-up state and run a fresh test cycle

## Confirmed Environment Facts
- Kernel: `6.18.8-gaokun3`
- `keep-display-on.service` was broken before test (`status=203/EXEC`) due to bad shebang in `/usr/local/bin/keep-display-on.sh`.
- Shebang fixed to `#!/bin/sh`; service now starts.
- I2C touch node exists in sysfs: `/sys/bus/i2c/devices/4-0048` (`name=hx83121a`), but AHB reads via `i2ctransfer` currently fail with `No such device or address`.
- SPI device existed in sysfs (`spi0.0`) but no SPI driver was bound initially; `/dev/spidev0.0` absent.
- Manual load of `/home/whitelewis/spidev.ko` created `/dev/spidev0.0`.

## Baseline Result Before New Round
- Script: `/home/whitelewis/touch_post_reboot_check.py`
- Result: register/flash reads return `0x00000000` across key addresses; not valid runtime data.
- Interpretation: transport path not producing valid IC register data at runtime (not direct evidence of hardware damage).

## Test Plan (This Round)
1. Ensure display keepalive and runtime PM state are sane.
2. Ensure `spidev` is available.
3. Run baseline snapshot (`touch_post_reboot_check.py`).
4. Run hardware reset attempt (`touch_gpio_reset.py`).
5. Re-run snapshot and compare deltas.
6. Record conclusions and next branch.

## Safety Note
- `touch_gpio_reset.py` toggles GPIO99 (TDDI reset) and may blank display temporarily.

## Round-1 Results (Executed)

### Pre-check
- `keep-display-on.service`: `active`
- DRM power: `/sys/class/drm/card1/device/power/control=on`, `runtime_status=active`
- `/dev/spidev0.0`: present

### Baseline (`touch_post_reboot_check.py`)
- Core status fields all `0x00000000`:
  - IC ID / Status / FW Status / Reload regs
- Code SRAM readback all zeros.
- Flash alias readback all zeros.
- Script summary: `Flash integrity: 18/40 correct`, `Flash data did NOT survive! 22 mismatches.`

### Reset test (`touch_gpio_reset.py`)
- Before reset: IC/Status/SRAM/Flash all `0x00000000`.
- Method 1 (sysfs gpio): failed (`/sys/class/gpio/gpio99/direction` missing).
- Method 2 (MMIO): toggled GPIO99 low/high successfully.
- After 5s: still `IC=0x00000000, Status=0x00000000, SRAM[0]=0x00000000`.

### Post-reset recheck
- Re-running `touch_post_reboot_check.py` shows no change vs baseline.
- Still all-zero readback on key IC/SRAM/flash addresses.

## Current Interpretation
- This round does **not** look like a normal `0x04` vs `0x05` boot-state issue.
- Current failure mode is deeper transport/path invalidity:
  - I2C AHB path: `No such device or address` on `0x48`.
  - SPI path (`spidev0.0`) returns all-zero payloads for all key register windows.
- Hardware-burn scenario remains unlikely from this dataset alone; behavior is deterministic and reproducible, but currently no valid register plane is observable.

## Next Actions (Proposed)
1. Capture a known-good run immediately after a clean boot where `0x48` was previously readable, then diff against this broken state.
2. Verify SPI transfer alignment (`skip` bytes / bus mode / command framing) against the last known-good script revision.
3. Confirm whether a recent kernel/module change altered `998000.spi` binding or bus timing defaults.

## Round-2 Results (Executed)

### SPI transport sanity
- `spi0.0` is present and bound to `spidev`:
  - `/sys/bus/spi/devices/spi0.0/modalias = spi:dh2228fv`
  - `/sys/bus/spi/devices/spi0.0/uevent` includes `DRIVER=spidev`
- SPI kernel statistics confirm real traffic (not a dead ioctl path):
  - `messages=1204`, `transfers=1204`, `bytes_tx=5307`, `bytes_rx=5307`
  - `errors=0`, `timedout=0`

### SPI parameter sweep
- Tested `mode=0/1/2/3` and speed `200k/500k/1M/2M/4M/8M`.
- All combinations returned all-zero payload for probe frame (`F3 ...`).
- Conclusion: not a simple SPI mode/frequency mismatch.

### GPIO state evidence (`/sys/kernel/debug/gpio`)
- Touch bus pins are muxed as expected:
  - `GPIO154/155/156/157` on `func1` (SPI path)
  - `GPIO171/172` on `func1` (I2C path)
- Reset/IRQ related levels observed:
  - `GPIO99 = high`
  - `GPIO175 = high`
- Powerdown-named lines:
  - `GPIO178/179 = out high`
- No obvious evidence of a permanently asserted reset/powerdown from this snapshot.

### Repeated reset-window test
- Ran 5 cycles of:
  - `touch_gpio_reset.py` (GPIO99 reset toggle)
  - immediate `touch_spi_check.py`
- Every cycle still produced:
  - raw SPI response all zeros
  - `IC ID = 0x00000000`
  - software reset retry still `0x00000000`

## Updated Interpretation
- Read-plane failure is now strongly characterized as:
  - SPI controller path alive and transferring.
  - Peripheral response remains deterministic all-zero across mode/speed/reset variants.
- This is consistent with device-side logic not being in a readable runtime state, rather than a host SPI framing typo.

## Round-3 Results (DT02 Runtime Check)

### Why this was tested
- ACPI DSDT shows touch path selection via `DT02`:
  - `DT02 == 0` => SPI devices (`HIMX0001/HIMX0002`) enabled
  - `DT02 != 0` => I2C HID (`HIMX1234`) enabled

### Read-only physical register snapshot (`/dev/mem`)
- `T174` (`0x0F1AE000`) on this BIOS branch:
  - `DT01=0x000003c3`
  - `DT02=0x00000000`
  - `DT03=0x000000e2`
  - `DT04=0x00000000`
  - `DT05=0x00000001`
  - `DT06=0x00000801`
- Additional fields:
  - `T100` (`0x0F164000`): `D301=0x241`, `D302=0x3`, others align with DT group
  - `TG08` (`0x0F108000`): `TG01=0x1`, `TG02=0x1`, others align with DT group

### Attempted runtime DT02 override
- Tried reversible experiment: write `DT02=1`, retest buses, then restore.
- Result: write path failed immediately (`/dev/mem` mmap write -> `EINVAL`), so runtime override was blocked on this kernel/security configuration.
- Practical meaning: in current environment we can observe selector state but cannot patch it from Linux userspace using `/dev/mem`.

### Interpretation update
- Firmware-selected mode is confirmed SPI (`DT02=0`) at runtime.
- Bus-routing mismatch is unlikely on this device (BIOS 2.16 map and Linux observed controllers align).
- Current all-zero read-plane issue is therefore not explained by wrong DT02 mode alone.

## Round-4 Results (EFI Variable Probe)

### Why this was tested
- `I2cTouchPanel`/`TouchPanelInit` binaries contain `GetVariable` call-path debug strings.
- If a firmware variable is missing/changed across boot paths, touch init branch can diverge.

### Runtime EFI variable findings
- Enumerated `efivars` on target: no variable name directly matching `TouchPanelInit/HIMAX/HIMX`.
- Found related variables:
  - `DisplayPanelConfiguration-882f8c2b-9646-435f-8de5-f208ff80c1bd`
  - `DisplayPpiFlag-882f8c2b-9646-435f-8de5-f208ff80c1bd`
  - `DisplaySupportedPanelCount-882f8c2b-9646-435f-8de5-f208ff80c1bd`
  - `DisplaySupportedPanelList-882f8c2b-9646-435f-8de5-f208ff80c1bd`
  - `UEFIDisplayInfo-9042a9de-23dc-4a38-96fb-7aded080516a`
  - `I2CWriteAndReadBUSY-24c38995-0940-4318-adeb-26bd5a2df237`
- Byte-level snapshots:
  - `DisplayPanelConfiguration`: attrs `0x00000006`, payload `00`
  - `DisplayPpiFlag`: attrs `0x00000007`, payload `00`
  - `DisplaySupportedPanelCount`: attrs `0x00000006`, payload `00 00 00 00`
  - `I2CWriteAndReadBUSY`: attrs `0x00000007`, payload `01`
  - `UEFIDisplayInfo`: non-empty structured payload (0x7C bytes total)

### Interpretation update
- There is no obvious exposed `TouchPanelInit` efivar key on this Linux runtime.
- Display-related EFI vars are present and consistent with firmware display init path being active.
- `I2CWriteAndReadBUSY=1` is a potentially relevant firmware status bit and should be correlated with Windows-boot and cold-boot deltas in next tests.

## Round-5 Results (Read-Plane Recovery Check)

### Immediate regression run
- `touch_spi_check.py` now reports valid key values again:
  - `IC ID = 0x83121a00`
  - `Status = 0x00000004`
  - `SRAM[0] = 0x78787878`
  - `Sorting = 0xad7a45bc`
  - `Handshake = 0x000000f8`
- Note: its probe `Raw:` line still shows zeros, but structured register reads are valid.

### Full validation
- `touch_post_reboot_check.py` now returns a healthy register plane:
  - IC identity/config fields populated (not all-zero)
  - Flash alias readback passes `40/40`
  - `*** Flash data survived reboot! ***`
- Remaining issue:
  - Input subsystem still has no internal touchscreen node (`/proc/bus/input/devices` only shows LID on internal I2C plus external USB HID devices).

### Updated interpretation
- The current blocker moved from “read-plane invalid” to “input-stack registration missing”.
- Hardware burn-out hypothesis is further weakened.
- Next useful direction is kernel/input integration path (driver bind + event device exposure), not raw transport recovery.

## Round-6 Results (Input Missing Root Cause)

### What was verified
- Runtime touch read-plane is valid (`IC ID` readable, flash alias `40/40`).
- Yet `/proc/bus/input/devices` still has no internal touchscreen node.
- `spi0.0` is bound to `spidev` (raw transport only).

### Root cause found
- Live/boot DTB currently in use (`/boot/sc8280xp-huawei-gaokun3.dtb`) contains:
  - `i2c@990000/touchscreen@48` (`himax,hx83121a`)
  - **no** `touchscreen@4f` (`hid-over-i2c`)
- Direct dynamic test confirmed this is blocking:
  - manual `new_device hid-over-i2c 0x4f` fails with  
    `i2c_hid_of 4-004f: HID register address not provided`
  - i.e. missing DT property path (`hid-descr-addr`) in active DTB.

### Prepared fix (safe, not replacing original DTB)
- Built test DTB:
  - `/boot/sc8280xp-huawei-gaokun3.hidfix.dtb`
  - includes `touchscreen@4f` + `hid-descr-addr=<0x1>` + IRQ/vdd bindings.
- Added GRUB rollback-safe boot entry:
  - `Arch Linux 6.18 (hidfix DTB)`
  - original entries untouched.

### Next test step
- Reboot and choose `Arch Linux 6.18 (hidfix DTB)`.
- After boot, verify:
  1. `dmesg | grep -Ei "i2c_hid|hid-over-i2c|himax|touch"`
  2. `cat /proc/bus/input/devices` shows internal touchscreen event node.
