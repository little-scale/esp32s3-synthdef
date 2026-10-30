# Project status — 31 October 2026

## Current outcome

The optimized one-voice instrument now has three richer SuperCollider examples
saved alongside Mac Sine. **Phase FM is in slot 2, Harmonic Mix in slot 3 and
Filtered Tone in slot 4.** Factory slot 0 and Mac Sine slot 1 remain available.
Saved graph, source and UI metadata read back byte-identically. The automated
checks finished with Mac Sine selected and silent, before manual listening review. The user subsequently confirmed all three new
sounds are clean and stop on touch release.

Current source build: `3793e0b3753c31eef80933b34ebc2d40e888d65d214be433494f1d689cedbdbb`.
Verified application: 880,080 bytes. Image/configuration hashes,
compiler flags and checked instruction placement: `evidence/esp32-ui-build.json`.
Observed port: `/dev/cu.usbmodem101`. See `evidence/board-state.json`,
`docs/PATCHES.md`, `docs/PERFORMANCE.md` and `evidence/optimization-summary.json`.

## Optimization and execution

- The pinned GPL C99 engine remains unmodified at
  `00ac338904304e87845477808e598ef973f49b52`. Synthesis runs on the ESP32;
  SuperCollider 3.14.1 compiles source on the Mac. One voice, 64-frame blocks,
  requested 44.1 kHz and a bounded mono ES8311 sink remain selected.
- Control indices are cached at activation. Live events retain finite/range
  checks, and initial-rate aliases are rejected before audio ownership changes.
  Cached and name-lookup adapters produce bit-identical PCM over 1,400 cases /
  268,800 mono samples.
- Rendering kernels and the small audio adapter use internal instruction RAM.
  Adapter bodies consume 1,470 bytes plus literals/alignment. Math flags, table
  contents and PCM rounding are unchanged. The sine table remains in flash.
- The earlier kernel placement fixed the reproduced 1,818 µs interaction overrun.
  The new filter exposed a smaller remaining issue: 1,019 µs and one 70% margin
  violation with the adapter in flash. Internal adapter placement reduced its
  three-round maximum to 813 µs with zero violations. Failed runs remain recorded.
- `catalog-voice-v2` retains the generic `simple-voice-v1` sine family and adds
  only the exact three measured graph hashes. Candidates require a diagnostic
  build; rejected graphs remain blocked. This is not blanket admission for all
  154 compiled UGen types or arbitrary FM/filter graph variants.
- Filter cutoff uses 100 ms control-rate smoothing. The unsmoothed candidate
  clipped on extreme jumps and was excluded; clipping tolerances were unchanged.

## Verification

Each new graph passed a SuperCollider float reference comparison, the expanded
ESP32 matrix and three 30-second UI exercises on the qualification image. The
final image repeated all five numerical matrices plus one 30-second exercise per
saved patch. Its maxima were:

| Patch | Slot | Combined maximum | Fraction of block | Margin violations |
| --- | ---: | ---: | ---: | ---: |
| Phase FM | 2 | 675 µs | 46.51% | 0 |
| Harmonic Mix | 3 | 800 µs | 55.12% | 0 |
| Filtered Tone | 4 | 792 µs | 54.57% | 0 |
| Mac Sine | 1 | 588 µs | 40.52% | 0 |

All final output, numerical and queue-failure counters were zero. The five muted
matrices cover 280 cases each / 268,800 mono samples total and agree with the Mac
within one PCM step. They include extreme frequencies and first/live/release
blocks. The audible UI exercise uses compiled base-frequency defaults, four
controls at 25 Hz, seven pitch positions and five note starts per second. This is
workload-specific evidence, not a realtime guarantee for every continuous value.

The final check also saved/reloaded all new entries, compared graph/source/UI
metadata, and rejected a renamed catalog binary with a valid digest while
retaining the current patch. Portable adapter, 262,136 nearest/even PCM oracle
cases, package corruption/truncation tests and normal/diagnostic catalog-admission
checks pass. Historical M2/M3/M4 and timing evidence retain their own identities.

## Ownership, memory and remaining gates

The audio owner alone mutates voice state. Parsing uses an inactive graph and
activation requires an acknowledgement before reuse. Save/load fades and drains
silence, parks rendering, stops DMA and verifies codec mute before flash writes.
Two checked generations per slot, compiled factory recovery, no blanket NVS erase
and no automatic formatting after provisioning remain in place.

Selected engine allocations remain 112,136 internal bytes for two graphs, one
voice and scratch. Retained kernel bodies total 29,614 bytes plus literals;
adapter bodies add 1,470. Final exercises retained at least 77,703 internal free
bytes, a 31,744-byte largest block and 12,848 bytes of audio stack margin.
Diagnostic result/waveform storage uses 120,960 preallocated PSRAM bytes.

A target size probe for 24 nodes / 32 signals / 256 input references would reduce
engine allocations to 31,064 bytes, saving 81,072 internal bytes. **That profile is
not implemented or selected.** It needs a consistent target ABI and fresh
compatibility/numerical/timing checks. Original engine capacities remain intact.

- A 30-minute release soak remains open. Driver counters do not prove
  uninterrupted physical audio. External
  recording, end-to-end latency, actual clock accuracy and battery transitions
  still need measurement.
- New-slot physical power-cycle and flash power-cut tests remain separate from
  checked file readback/reload. Two SPIFFS files cannot guarantee recovery from
  every filesystem-wide corruption or brownout.
- Earlier native USB lock-up recovered through a physical reconnect. No fix for
  that separate reset issue is claimed. USB responded throughout these checks.
- A second voice, a master effect, sequencing, motion and microphone processing
  remain later work. This completes the one-voice example step of M5 only.
- Apple AddressSanitizer deadlocks before main on this Mac; no ASan pass is claimed.
  Working sanitizers and pinned-source warning exceptions remain documented.

Original flash and earlier/current application backups remain under `recovery/`,
excluded from Git. The public source repository is
[github.com/little-scale/synthdefs-for-esp32-s3-touch-amoled-1.8](https://github.com/little-scale/synthdefs-for-esp32-s3-touch-amoled-1.8).
