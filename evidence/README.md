# Recorded evidence

All results are from the initial local implementation session on 30 October
2026. `STATUS.md` explains which results meet prototype checks and which release
gates remain open.

| Record | Meaning |
| --- | --- |
| `compatibility.json` | Compiled enum/loader reconciliation, upstream profile discrepancies and host structure sizes |
| `upstream-tests.log` | Complete successful upstream `make test` output |
| `reference-check.log`, `reference-results.json` | Filtered sine reference comparison and scale catalog check |
| `host-adapter.json` | Portable adapter checks and actual sanitizers used |
| `esp32-build.json`, `esp32-build.log` | Final cross-build identity, hashes, target sizes and verified flags |
| `sdkconfig.esp32s3` | Exact normal-firmware configuration snapshot |
| `board-rom.txt`, `board-check.log` | ROM identification and official board boot/PSRAM check |
| `codec-tone*.log` | Vendor codec tests; low level inaudible, V2 level loud/distorted per user |
| `offline-capture.log`, `target-numerical.json` | Full target float capture and passing numerical comparison |
| `realtime-controls.log` | Initial 15-second note/pitch/amplitude/release/panic test |
| `realtime-high-amplitude.log` | Longer note; user confirmed audible but quiet |
| `realtime-final.log`, `realtime-summary.json` | Final 30-second control run, PCM peaks and one conservative timing-margin violation |
| `m2-baseline/` | Archived M2 build, configuration, numeric and timing records |
| `realtime-optimized.log`, `realtime-optimized-summary.json` | Optimized audio-only hardware run: 631 µs worst combined block, zero 70% violations |
| `touch-reference.json` | Four-control patch versus SuperCollider, including live changes |
| `ui-host.json`, `ui-*-preview.png` | Actual LVGL widget simulation and host layout previews |
| `esp32-ui-build.json`, `sdkconfig.ui.esp32s3` | Corrected touchscreen image build/configuration, restored to the board |
| `ui-boot.log` | Initial UI image booted; physical screen reported black |
| `ui-screen-capture.log` | Failed snapshot while diagnosing the initial display integration; not a successful screen capture |
| `ui-fixed-recovery-boot.log`, `ui-restored-boot.log` | Successful corrected UI startup, zero startup DMA-event overflows |
| `ui-fixed-screen-capture.log`, `ui-device.png` | Complete actual device snapshot and decoded image |
| `realtime-ui.log`, `realtime-ui-summary.json` | Audio with requested 25 Hz redraw stress: maximum 759 µs / 52.30%, zero margin violations or reported output/numerical failures |
| `touch-target-capture.log`, `target-touch-numerical.json` | Passing 22,080-frame ESP32 comparison of the touch patch |
| `board-state.json` | Final restored playable build identity and user confirmation |

The capture build predates the final gain/control telemetry changes. Its exact
binary/configuration/source build IDs are in `target-numerical.json`; the pinned
DSP engine is unchanged. The original M2 build identity is archived under
`m2-baseline/`. Latest compile records and every hardware log carry their own
source build IDs; a new compile is not proof that it was flashed. Hardware outputs
are mono; numerical capture is stereo float before sink conversion.

Recovery provenance is in `../recovery/backup.json`; the full original flash is
kept locally beside it and excluded from Git. No firmware image or source was
published. Raw logs are retained so reported counters can be independently checked.
