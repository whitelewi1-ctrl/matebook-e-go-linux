# Touchscreen Read-Plane Debug Log (2026-02-11)

## TL;DR (Current State)

- IC control plane is reachable in healthy boots (`IC_ID=0x83121a00`, flash readback OK).
- Event plane read via raw SPI (`F3/F5 + cmd 0x30`) is persistently all-zero.
- `status` can be driven to `0x05` by some sequences, but `0x30` still all-zero.
- GPIO175 does produce edges, but no-touch and touch windows are nearly identical (`~35` vs `~36-37` per 15s), so it behaves like background periodic activity in current mode.
- Current best hypothesis: our raw `0x30` path is not equivalent to Windows `GetFrame` data path (or missing additional gate/protocol context).

## Hand-off Checklist (Next Session)

1. Keep using `tools/touchscreen/spi_plane_probe.py` as entry gate.
2. Prefer healthy boot state (`IC_ID` readable) before any deeper test.
3. Do not use GPIO175 edge count alone as touch-validity signal.
4. Move effort to reproducing Windows `GetFrame` semantics (IOCTL/driver path), not more `0x30` address sweeps.
5. Use synchronized script `tools/touchscreen/irq_spi_sync_test.sh` only as correlation evidence, not success criterion.

## Scope
- Device under test: `whitelewis@192.168.1.16`
- Goal: Investigate and stabilize the "read-plane anomaly" before moving to SPI->uinput bridging.
- Focus: transport + register/event read behavior (not coordinate algorithm yet).

## What Was Executed

### 1. Verified runtime basics
- `keep-display-on.service` is `active`.
- DRM runtime PM:
  - `/sys/class/drm/card1/device/power/control = on`
  - `/sys/class/drm/card1/device/power/runtime_status = active`

### 2. SPI node status
- Initial state in this boot: `/dev/spidev0.0` missing.
- Recovery:
  - `modprobe spidev` / `insmod /home/whitelewis/spidev.ko`
  - `/dev/spidev0.0` restored.

### 3. SPI register/event probe
- Direct probe result:
  - `IC ID` readback raw bytes: `00000000`
  - `F3 0x30` read payload: all zero (multiple lengths tested up to 4090 bytes)
  - `F3 0x08` large payload read: also all zero
- Existing script verification:
  - `/home/whitelewis/touch_spi_check.py` reports:
    - `Raw: 000...`
    - `IC ID: 0x00000000 [BAD]`
    - software reset still `0x00000000`

### 4. Reset attempt
- Executed `/home/whitelewis/touch_gpio_reset.py`.
- GPIO99 MMIO toggle succeeded (low -> high), but post-reset still:
  - `IC ID = 0x00000000`
  - `Status = 0x00000000`
  - no read-plane recovery.

### 5. I2C cross-check
- `i2cdetect -y 4` currently shows no responding 0x48 device.
- Sysfs node exists (`/sys/bus/i2c/devices/4-0048`) but no bus-level response.

## Current Diagnosis

This boot is in a **full read-plane collapse state**:
- SPI transport file node can be present, but returned data is all zero.
- I2C bridge address (0x48) does not ACK.
- GPIO reset and software reset do not recover.

This is different from the earlier "healthy but idle" state (`IC ID readable, status=0x04`).

## Key Implication

Do **not** start coordinate/uinput work from this runtime state.
First gate should be:
1. `IC ID == 0x83121a00` readable.
2. `STATUS`/`HANDSHAKE` readable and non-zero.
3. `0x30` event payload has non-zero entropy.

Only after these are true should SPI->uinput bridging be enabled.

## New Tool Added

- Script: `tools/touchscreen/spi_plane_probe.py`
- Purpose:
  - one-shot read-plane health probe,
  - compare `0x30` vs `0x08` payload entropy,
  - repeatability/diff statistics.

### Usage (on target)
```bash
sudo python3 /path/to/spi_plane_probe.py --dev /dev/spidev0.0
```

## This Round Baseline (Captured)

Executed:
```bash
sudo python3 /tmp/spi_plane_probe.py --dev /dev/spidev0.0 --repeat 6
```

Observed:
- Registers:
  - `IC_ID=0x00000000`
  - `STATUS=0x00000000`
  - `HANDSHAKE=0x00000000`
  - `FW_STATUS=0x00000000`
  - `SRAM0=0x00000000`
- `cmd 0x30` payloads (`64..4090` bytes): all-zero, `nz=0`.
- `cmd 0x08` payloads (`64..4090` bytes): all-zero, `nz=0`.
- Repeat stability (`4090` bytes x6): `diff=0` across all iterations.

Conclusion for this snapshot: deterministic full-zero read-plane collapse.

## Contrast Snapshot: 192.168.1.69

Same probe script on `192.168.1.69` shows a different class of state:
- Register plane is readable:
  - `IC_ID=0x83121a00`
  - `STATUS=0x00000004`
  - `HANDSHAKE=0x000000f8`
  - `SRAM0=0x78787878`
- `cmd 0x30` payload remains all-zero (`nz=0` for `64..4090`), stable across repeats.
- `cmd 0x08` payload is non-zero and stable (starts with `edfeadde...` and many `0x78` bytes).

`touch_post_reboot_check.py` on `192.168.1.69`:
- Flash integrity `40/40` correct.
- Reload controller registers populated.
- Safe-mode and `activ_relod` sequence does not move state to running (`status` stays `0x04`).

Interpretation:
- `192.168.1.16`: full read-plane collapse (all-zero everywhere).
- `192.168.1.69`: read-plane healthy, but firmware still not entering sensing/running mode (event plane dead).

## A/B Test: Panel Module Isolation

Objective:
- Validate whether repeated panel driver init (`panel_himax_hx83121a`) is the root cause of touch read-plane anomalies.

Method:
- A: normal boot (panel module enabled).
- B: boot entry `TEST: No Panel (check IC status via SSH)` with:
  - `modprobe.blacklist=panel_himax_hx83121a`

B-state verification (`192.168.1.75`):
- `/proc/cmdline` contains `modprobe.blacklist=panel_himax_hx83121a`.
- `lsmod` shows no `panel_himax_hx83121a`.

B-state probe result:
- Register plane readable:
  - `IC_ID=0x83121a00`
  - `STATUS=0x00000004`
  - `HANDSHAKE=0x000000f8`
  - `SRAM0=0x78787878`
- Event plane remains dead:
  - `cmd 0x30` all-zero (`nz=0`) for `64..4090`, stable repeats.
- Data plane/readback remains good:
  - `cmd 0x08` non-zero, stable.
  - `touch_post_reboot_check.py` flash integrity `40/40`, reload regs populated.

Conclusion:
- Disabling `panel_himax_hx83121a` does **not** resolve the core issue (`status=0x04`, event plane dead).
- Root cause is more likely in touch IC mode transition / boot-trigger sequence, not panel module runtime behavior alone.

## Wakeup Matrix Result (`hx_wakeup_matrix.py`)

Script:
- `tools/touchscreen/hx_wakeup_matrix.py`

Run target:
- `192.168.1.75` (no-panel boot entry active)

Key scenarios and outcomes:
- `fw_stop`:
  - `fw_status` changed to `0xA5`
  - `status` stayed `0x04`
  - `cmd30_nz` stayed `0`
- `activ_relod`:
  - `status` changed `0x04 -> 0x05`
  - reload status `r0` changed `0x12 -> 0x10`
  - `cmd30_nz` still `0` (all-zero event plane)
- `system_reset_then_activ`:
  - also drives `status` to `0x05`
  - `cmd30_nz` still `0`
- `safe_reload_combo`:
  - returns to `status=0x04`
  - `cmd30_nz` still `0`

Interpretation:
- We can force the state byte to `0x05`, but this alone does not produce non-zero event-plane data.
- Therefore, `status==0x05` is necessary but not sufficient for real touch frame output in current sequence.

## Extended Event-Plane Tests (`hx_event_plane_probe.py`)

Script:
- `tools/touchscreen/hx_event_plane_probe.py`

On `192.168.1.75`:
- Initial: `status=0x04`, `raw_out_sel=0xfdfe7d96`, `cmd30_nz=0`.
- `raw_out_sel (0x100072EC)` sweep values:
  - `0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0xA`
  - result: `status` unchanged (`0x04`), `cmd30_nz` always `0`, hash unchanged.
- After force + 120x burst polling (`20ms`):
  - `unique_hashes=1`, `nonzero_hits=0/120`
  - no transient non-zero window observed.

Interpretation:
- `raw_out_sel` simple sweep does not open event-plane output in this environment.

## Master vs Slave Event Read Check

Direct SPI opcode comparison:
- Master read opcode: `0xF3`
- Slave read opcode: `0xF5`
- Tested `cmd=0x30`, lengths `339/512/1024/2048`.
- Result:
  - both opcodes return all-zero payloads,
  - same SHA per length, indicating effectively identical zero plane.

Interpretation:
- Not a simple "wrong channel" issue between master/slave read opcodes for current setup.

## User-Touch Assisted Live Test

Question verified:
- "Could event plane be zero only because no one touched the screen?"

Method:
- On `192.168.1.75`, ran a 15s live capture loop while user continuously performed:
  - tap
  - swipe
  - multi-touch gestures
- Per-sample fields:
  - `status` (`0x900000A8`)
  - `handshake` (`0x900000AC`)
  - master/slave `cmd 0x30` (`0xF3`/`0xF5`) non-zero count + hash
  - `cmd 0x08` short read as control channel

Result:
- `status` stayed `0x04` for the entire 15s window.
- `cmd 0x30` (master/slave) stayed all-zero for all samples:
  - `cmd30_m_nz = 0`, hash unchanged
  - `cmd30_s_nz = 0`, hash unchanged
- `cmd 0x08` had rare hash/non-zero-count jitter (e.g. `19 -> 30`), but not accompanied by any `0x30` activation.

Interpretation:
- This is **not** a "no-touch stimulus" artifact.
- Touch gestures did not wake/enable the currently probed event plane.

## GPIO Activity Check During Touch

Method:
- 15s polling (`20Hz`) during user touch activity:
  - `gpioget -c gpiochip4 --numeric 175`
  - `gpioget -c gpiochip4 --numeric 99`
  - plus candidate lines `171/172` (returned error in this chip context)

Observed:
- `L175` stayed `0` (no toggles).
- `L99` stayed `1` (no toggles).
- `171/172` unavailable via this chip in current mapping (`E`).
- Total tuple changes during 15s: `0`.

Interpretation:
- No visible interrupt-line activity on the currently watched lines during touch gestures.
- Either:
  1) the real IRQ line is different from current probe lines, or
  2) interrupt/event path is not armed in current mode.

> Note: The above result came from `gpioget` polling and was later superseded by `gpiomon` edge monitoring (see "IRQ vs SPI Event-Plane Correlation Test" and "No-Touch Control"), which confirmed GPIO175 does toggle but mostly as background periodic activity.

## Updated Working Hypothesis

Current blockers are now better constrained:
1. We can sometimes force state/register transitions (including `status=0x05` in some sequences), but
2. event-plane payload at `cmd 0x30` remains zero under both idle and active touch,
3. and observed candidate GPIO lines show no edge activity.

So next debugging should prioritize:
- exact IRQ line mapping from DT/ACPI for current boot mode, and
- frame acquisition path equivalence to Windows `GetFrame` semantics rather than raw `0x30` reads alone.

## IRQ vs SPI Event-Plane Correlation Test

New synchronized capture script:
- `tools/touchscreen/irq_spi_sync_test.sh`

What it does (15s window):
1. Monitor IRQ edges on `gpiochip4 line 175` via `gpiomon`.
2. In parallel, repeatedly read SPI event plane (`0xF3 0x30`, 512-byte payload).
3. Report IRQ edge count and SPI payload non-zero/hash stats.

### Run A (normal state)
- `status_before = 0x00000004`
- `irq_edges = 37`
- `spi_samples = 265`
- `spi_nonzero_hits = 0`
- `spi_unique_hash = 1` (`5c3eb80066`)

### Run B (forced status=0x05 before capture)
- `status_before = 0x00000004`
- `status_after_force = 0x00000005`
- `irq_edges = 36`
- `spi_samples = 265`
- `spi_nonzero_hits = 0`
- `spi_unique_hash = 1` (`5c3eb80066`)

Interpretation (strong evidence):
- IRQ line is active during touch interaction.
- Even with IRQ activity and forced `status=0x05`, raw `0x30` reads remain constant all-zero.
- Therefore, current SPI raw read path (`F3/F5 + cmd 0x30`) is likely **not** equivalent to the effective frame path used by Windows (`GetFrame`/driver IOCTL stack), or additional mode gates are missing.

## No-Touch Control (Noise Check)

User hypothesis:
- GPIO175 edges might be background noise / periodic events rather than real touch IRQs.

Method:
- Two 15s captures with **no touch input** at all:
  1. normal state
  2. forced `status=0x05`
- Same synchronized script:
  - `irq_spi_sync_test.sh`

Results:
- No-touch / normal:
  - `status_before=0x00000004`
  - `irq_edges=35`
  - `spi_nonzero_hits=0`, `spi_unique_hash=1` (`5c3eb80066`)
- No-touch / force05:
  - `status_before=0x00000004`
  - `status_after_force=0x00000005`
  - `irq_edges=35`
  - `spi_nonzero_hits=0`, `spi_unique_hash=1` (`5c3eb80066`)

Comparison with touch runs:
- Touch runs produced `irq_edges` around `36~37` in the same window.
- Difference is negligible relative to no-touch baseline.

Conclusion:
- GPIO175 edge activity is dominated by background periodic events in current mode.
- It cannot be used as a reliable indicator of valid touch frame generation.

## Next Actions (Refined)

1. Build/verify a Linux-side `GetFrame`-equivalent path (driver/IOCTL semantics), instead of raw `0x30` reads.
2. Keep current scripts as preflight:
   - `spi_plane_probe.py` (health gate)
   - `hx_wakeup_matrix.py` (state transition check)
   - `irq_spi_sync_test.sh` (IRQ/data correlation)
3. If booting back into Windows is possible, prioritize dynamic capture of touch IOCTL traffic to bridge the semantic gap quickly.
