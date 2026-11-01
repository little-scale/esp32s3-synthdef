# Memory budget

## Current FM1/cache instrument

The current image is recorded in `evidence/control-deltas-build.json`. Target
structure sizes and fixed placements are separate from runtime free-heap values:

| Allocation | Bytes | Placement |
| --- | ---: | --- |
| Three graph buffers | 40,860 | PSRAM |
| Main voice | 35,752 | Internal, with the documented allocation fallback |
| FX voice | 35,752 | PSRAM |
| Shared DSP scratch | 49,152 | PSRAM, reused serially |
| Main delay/state arena | 1,048,576 | PSRAM |
| FX delay/state arena | 1,048,576 | PSRAM |
| Remote-control state | 24,968 | Preallocated PSRAM, including 17 KiB of Main/FX stream baselines |
| Control status snapshot | 512 | Staging/mailbox state; serialization outside the audio owner |
| Package buffers | 393,216 | Preallocated PSRAM |
| Audio / console stacks | 16,384 each | Internal, reserved before display/network startup |
| UI task stack | 10,240 | Core 0 |
| LVGL fixed heap | 65,536 | Internal |
| UI draw buffer | 14,720 | Internal DMA memory |

A source-view model may use up to 393,221 PSRAM bytes; an old and replacement
model can coexist briefly. Network storage also prefers PSRAM. Large free PSRAM
does not imply sufficient internal/DMA memory; Wi-Fi startup and cache/IRAM
placement have separate constraints. Both renderers use preallocated buffers.

The 1 MiB arenas provide delay memory per stage, not one combined unrestricted
pool. A mono five-second float32 delay at 44.1 kHz rounds to 262,144 samples and
uses the whole 1 MiB arena. Stereo short CombC (50 ms maximum) uses two rounded
4,096-sample buffers, 32 KiB total. Other UGens share that stage arena; rounding,
interpolation padding and allocations determine admission. The compiler reports
actual arena demand. No per-sample bit-depth reduction is used.

Compact-control baselines add 17,408 bytes to the earlier 7,560-byte remote state.
The event queue remains 16 complete snapshots; expansion uses bounded stack
work, with no audio-task allocation. Cache recovery and queue-full rollback are
covered by portable and physical tests. See [SUPERCOLLIDER.md](SUPERCOLLIDER.md).

## Historical compact-profile measurements


These structure sizes were produced by Xtensa GCC 14.2.0, with the pinned engine,
and recorded by `host/record_build.py`. They are compile-time sizes, not free-heap
measurements. The app logs actual allocations/free memory after boot.

| Allocation | Bytes | Placement / lifetime |
| --- | ---: | --- |
| Two synth graph buffers | 16,152 | Internal; staging changes only after audio acknowledgement |
| Persistent master graph | 8,076 | Internal; embedded mono delay SynthDef |
| Synth voice state | 6,720 | Internal; one musical voice |
| Master effect state | 6,720 | Internal; persists between notes |
| Shared scratch | 8,192 | Internal; reused serially by synth and effect |
| Engine fixed total | 45,860 | Three graphs, two engine instances, one scratch |
| Master delay arena | 1,048,576 | PSRAM; cleared only at startup/parked maintenance |
| Audio task stack | 16,384 | Internal |
| Console/patch service stack | 16,384 | Internal |
| UI task stack | 10,240 | Internal |
| Package buffers | 393,216 | Preallocated PSRAM |
| LVGL fixed heap | 65,536 | Internal; includes synth, library and delay controls |
| Rendering kernel bodies | 31,988 plus literals/alignment | Internal instruction RAM |
| Adapter/effect hot bodies | 1,756 plus literals/alignment | Internal instruction RAM |
| Diagnostic results | 13,440 | Preallocated PSRAM |
| Diagnostic waveforms | 107,520 | Preallocated PSRAM; reused by sparse echo probe |
| UI draw buffer | 14,720 | Internal DMA memory |
| Event batch | 22 events | Audio stack; latest controls plus bounded note queue |
| I2S DMA | Six × 128 frames | Internal DMA memory; physical format driver-dependent |

The target voice is 6,720 bytes; host pointer/alignment differences make its size
slightly different. Use the target build record for allocations.

The selected target profile has 24 nodes, 32 signals, 256 input references and a
262,144-float arena limit per engine instance. Constants, controls and partials
retain their original capacities. `host/engine_profile.py` generates a target copy
with checked capacity macros, a precleared binding helper and the documented
Gendy3 closing-segment bounds fix. DSP precision and
vendored files stay unchanged. Parser, renderer and adapters share one header.

Capacity reduction alone changes the old two-graph/one-voice engine allocation
from 112,136 to 31,064 bytes, saving 81,072. Adding the persistent effect graph and
state uses another 14,796, giving 45,860 total: **66,276 fewer internal bytes than
before effects were added**. The long buffer comes from PSRAM separately.

The five-second `CombL` rounds its allocation to 262,144 float slots. Bounds are
checked before activation. Compact synth admission allows zero memory arenas;
only the embedded master effect owns this long buffer. No heap allocation occurs
in either renderer. The small immutable sine table remains in flash.

`fm_bind_delay` clears its arena, so the master is initialized once and stays
active across note starts/releases. Panic suppresses its output at the next audio
boundary. The owner then stops DMA and clears the arena during maintenance before
acknowledging resume; patch changes and saves also clear echoes. A measured full
clear takes around 46 ms and is not placed inside a rendering deadline.

The UI snapshot temporarily uses 329,728 PSRAM bytes after stopping notes.
Older free-heap figures in historical reports refer to different configurations;
use the final delay-session telemetry for current heap and stack margins.

The partition map reserves 3 MiB for a factory application and the remaining
12.94 MiB for SPIFFS patch storage, after NVS/PHY data. Flash writes occur only
after the audio owner parks and DMA stops. No OTA layout is claimed.
`evidence/fm1-compact-build.json` records the current compact image and
configuration hashes. Historical free-heap observations do not measure the new
source or optional FM1 profile.

## Earlier FM1 compatibility-profile measurements

`CONFIG_SYNTHDEF_FM1_COMPAT=y` restores 160 nodes, 192 signals and 1,024 input
references. Its measured target structure sizes are 13,620 bytes per graph,
35,744 per voice and 49,152 for shared scratch. Three graphs and scratch occupy
90,012 PSRAM bytes; two voice states occupy 71,488 internal bytes. The fixed
engine total is 161,500 bytes. Compared with compact mode, that uses 25,628 more
internal bytes and 90,012 more PSRAM bytes.

A separate 1,048,576-byte synth arena joins the master's 1,048,576-byte arena.
Both are allocated at startup; actual graph requirements are validated before
activation. There is no heap allocation on note-on. The synth arena clears at
most 4 KiB per audio block and gets a separate constructor block; a full arena
adds approximately 373 ms of preparation at 44.1 kHz. Release/Panic cancels it.
The master continues independently. This bounds the amount of clearing work,
but does not establish ESP32 execution time or audio deadlines.

These figures are cross-compiler measurements, not runtime free-memory results.
The optional image was flashed and passed short checks: startup reported
114,187 internal and 5,657,760 PSRAM bytes free; live exercises retained at least
113,747 internal bytes and 11,924 unused audio-stack bytes. The full synth arena
also passed a hardware matrix and normal incremental start/cancellation/release.
These observations do not establish all possible graph workloads. See `evidence/fm1-compat-build.json` and
[UGen support](UGEN_SUPPORT.md) for software evidence and limits.

The selected optimization image (`3afda820448b`) keeps **16,665 bytes of Rings
code** in instruction RAM before literals/alignment, with 32 KiB instruction /
64 KiB data caches and 64-byte data lines. The optional **67,584-byte internal
voice arena is disabled by default**: its small speed gain did not justify the
heap cost. Both full 1 MiB PSRAM arenas remain available.

Task stack sizes stay at 16 KiB each, reserved before display/NVS startup;
their two static control blocks total 680 bytes. The display task explicitly
requests internal byte-addressable RAM, allowing IDF's reserved internal pool.
This fixes the allocation failure exposed by larger caches.

The selected image retained at least **47,715 internal bytes free**, a
**38,912-byte largest block**, **8,280 unused audio-stack bytes** and **11,760
unused control-stack bytes** over nine live exercises. The dedicated-arena
trial retained only 26,459 internal bytes. The selected full synth arena passed
its hardware comparison, early cancellation and normal start/play/release;
master-delay echoes through five seconds match native C exactly. These runtime
figures belong to `evidence/rings-cache-build.json` and the corresponding device
reports, separate from the older measurements above. See
[RINGS_OPTIMIZATION.md](RINGS_OPTIMIZATION.md).

## Historical size probe

`evidence/proposed-capacity-sizes.json` records the earlier size-only experiment.
Those node/signal/reference capacities are now selected and checked in the target
build. The expanded arena bound adds no fixed structure bytes.

The extended fixed-image exercises retain at least 113,691 internal bytes free
and 8,316 unused audio-stack bytes. The muted long-capture diagnostic temporarily
allocates an additional 1 MiB plus two guard floats, frees it before live audio
resumes, and reports guard integrity. See [EXTENDED_TESTS.md](EXTENDED_TESTS.md).

## Wi-Fi image — 1 November 2026

The current network image keeps the 35,752-byte instrument voice internal and
places the 35,752-byte master-effect voice in PSRAM. The audio stack remains
16 KiB; the control stack is 8 KiB (prior runtime high-water measurement used
about 4 KiB). These changes release 43,944 internal bytes relative to the initial
Wi-Fi build. The master arena remains a separate 1 MiB PSRAM allocation.

Wi-Fi station/HTTP initialization now succeeds with about 15.8 KB internal heap
free and a 10,752-byte largest block. Nearby-network scans work. Sound and master-slot LAN uploads now pass; a 111-UGen instrument / MiVerb graph
ran at about 95% audio budget with no additional DMA events across 22.03 measured
seconds after settling. Rich master-effect graphs and worst-case control-stack
margin still require their own measurement.
