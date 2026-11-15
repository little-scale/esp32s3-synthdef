# Integration map and acceptance gates

This document retains the original architecture and acceptance plan. Shared
Main/FX integration, USB deployment, actual-rate admission, physical control/LED
buses and speaker playback are now implemented. See the [current port status](README.md)
and [native 16 kHz results](NATIVE_16K.md) for completed tests and remaining work.
The isolated commissioning probe remains available as a separate build. The
future-facing requirements below are acceptance criteria, not a statement that
those implemented components are still absent.

## Product goal: a fully equal production target

Voice PE is intended to become a first-class target in the existing SC SynthDef → ESP32-S3 system, alongside Waveshare and XIAO. The separate silent probe is a commissioning tool, not the final application architecture or definition of completion.

The final target should use the shared production application, engine, Main/FX lifecycle, storage services and host protocol. Board selection should supply audio, physical controls, capabilities and build settings through explicit adapters. Keep one SC extension and one Studio workflow; selecting a Voice PE module should not require a separate compiler, deployment format or reduced UGen profile.

### Definition of parity

| Area | Required outcome before calling Voice PE an equal supported target |
|---|---|
| SC authoring and deployment | Existing Function and literal SynthDef workflows, `.sendESP32` / `.playESP32`, initial arguments and source readback work with the same semantics. |
| Engine | Same supported UGen/operator profile, graph limits and Main/FX features; rate-dependent behavior and admission use the target's actual sample rate. |
| Main and master FX | Independent definitions and instances, FX bypass, replacement fades, tails, volume, Panic and restart behave consistently. |
| Live control and patterns | Named scalar/array controls, note/gate lifecycle, scheduled events, cancellation and existing pattern routing pass the shared regression suite. |
| Studio and transport | Existing USB deployment and paired Wi-Fi workflows, discovery, permanent identity, aliases/groups and multi-module operations work through the shared host tools. |
| Persistence | Saved graph/source, initial arguments, documented boot behavior, module identity, network settings and output volume survive restart and supported updates. |
| Diagnostics | Actual rate, build/profile identity, CPU load, memory, faults and stereo PCM capture are exposed accurately; no board-specific assumptions leak into host tools. |
| Physical interface | Encoder/button and LED ring get explicit documented mappings. Features requiring absent hardware, such as a touchscreen or battery, are declared as capabilities rather than simulated. |
| Grove parameter inputs | Qualified modules expose normalized 0–1 read-only control buses through the shared Main/FX snapshot and normal SC/Studio configuration, with stable assignments, calibration, validity, stale-data behavior and Panic handling. Unsupported sensors are reported honestly. See [Grove design](GROVE.md). |
| Maintenance and release | Named production build, shared regression checks, board-specific commissioning evidence, recovery documentation and inclusion in the normal release/support workflow. |

Parity means equal software support and workflow semantics. It does not promise identical CPU headroom, analogue output, physical controls or bit-identical audio across different sample rates. Keep target-specific measurements and report genuine resource limits. Microphone/voice-assistant features are optional extensions beyond the existing synth workflow, not prerequisites for synth target parity.

### Original preparation plan

Refactor explicit board selection and shared capabilities; carry target sample rate through Main/FX, admission, protocol metadata and host inspection; add shared host tests at both rates; compile all production targets; and prepare the Voice PE audio/control adapters with playback gated. Preserve existing target defaults and regression evidence throughout. Hardware arrival gates clock/codec qualification, listening, sustained real-time tests and recovery validation—not this software integration work.

The parity items above are acceptance requirements, not a claim that the current scaffold implements them. Until they pass, label Voice PE experimental. The project is complete only when it can be selected and used through the normal SC/Studio workflow with recorded board validation.

## Current starter status

This scaffold deliberately avoids a deceptive one-line `44100 → 48000` change. A complete audio port remains pending. The production instrument and its existing hardware evidence retain their original rates and targets.

## Current repository architecture

| Layer | Current code | Voice PE change needed |
|---|---|---|
| Board selection | `host/xiao.sh`, environment `SYNTHDEF_BOARD`, `firmware/CMakeLists.txt`, `main/CMakeLists.txt`, `board_audio/CMakeLists.txt` | Introduce an explicit third target and matching Kconfig guards. Unknown selectors currently fall through to Waveshare; never rely on that for Voice PE. |
| Audio sink | `board_audio.c` is Waveshare/ES8311 mono; `board_audio_i2s.c` is XIAO master stereo S16 | New slave S32 sink + AIC3204 control + fail-closed start sequence. Preserve the existing byte-count contract of `board_audio_write`. |
| Controls/display | `main.c` branches on `CONFIG_SYNTHDEF_HEADLESS`; `headless_io` is XIAO-specific | Reuse headless UI/service concepts, not pin handling. XIAO GPIO21 activity writes would corrupt WS2812 data; its analog GPIOs are also unsuitable. New encoder/button handler outside the audio task. |
| DSP | `synthdef_engine/CMakeLists.txt` runs `host/engine_profile.py`, using pinned portable C plus established project transforms | Core accepts a supplied rate. Keep candidate DSP switches off. The scaffold uses this same FM1 generator, not a substitute oscillator. |
| Main/FX | `main.c` uses `SAMPLE_RATE=44100`; `instrument.c` accepts 44100 or 48000; `master_delay.c` rejects other rates than 44100 | Centralize rate per board and pass through Main, FX, fades, event timing and diagnostics. Retest delay, feedback, envelopes and reset/panic at both rates. |
| Admission/storage | `patch_format.c` evaluates delay requirements at 44100; patch service mounts storage and initializes settings | Make validation take actual target rate. Audit factory/OTA/filesystem partition choices before mounting anything. Avoid format-on-mount-failure on inherited stock partitions. |
| Host/protocol | `patch_service.c` INFO reports literal 44100; `host/studio_probe.c` and `host/inspect_graph.c` inspect at 44100 | Report actual rate, make host admission target-aware and retest package/PCM capture metadata. Update profile fingerprints/capabilities through the existing generator. |
| Diagnostics | `diagnostics.c`, `dsp_qa.c`, `trace_probe.c` have 44100 assumptions | Parameterize or explicitly exclude these from a 48 kHz target. Never label 44.1 kHz traces as 48 kHz evidence. |

The existing 64-frame block is 1.451 ms at 44.1 kHz and 1.333 ms at 48 kHz. This means 8.84% more DSP blocks per second, before any codec/DMA costs. CPU and memory results from XIAO do not qualify Voice PE. Fixed sample arenas represent shorter durations at higher rates; power-of-two allocation means individual patches may cross capacity boundaries. The checked master-delay fixture happens to require 262,144 samples at both rates, but that does not generalize to all graphs.

## Proposed output contract

Keep interleaved stereo through Main → FX/bypass → final volume. Initially retain the existing S16 quantization and pack to MSB-aligned S32 using `voice_pe_pack_s16`; do not reinterpret S16 memory as S32. A future `board_audio_write` receives frames of S16 stereo and must report **input bytes consumed**, not the doubled wire-byte count; otherwise the current main loop will report false partial writes. Handle partial I²S writes in whole stereo frames and preserve a bounded timeout.

Retain independent L/R at the jack; determine the internal speaker mix from schematic and bench tests rather than prematurely folding to mono. Amplifier low mutes only the internal speaker path, not the headphone outputs. The physical side switch cuts microphones; it is not a synthesizer emergency mute.

Choose native 48 kHz as the initial integration direction. An explicit quality-tested 44.1→48 kHz resampler is an alternative if exact existing-engine rate behavior is required, but simple sample re-labeling changes pitch and timing. Neither a resampler nor full 48 kHz production integration is implemented here.

## Implement next, in order

1. **Read-only board identity and recovery:** record stock versions, memory, flash map, ESP MAC/security state and two matching dumps. Confirm native USB ROM entry before replacing anything. Follow RECOVERY.md.
2. **Silent probe:** match memory sizes and inspect raw input levels. Scope/logic-analyzer checks are optional until clocks become relevant; no inference of debouncing/direction from the 1 Hz input log. Keep the mic switch muted and external audio disconnected.
3. **Clock and codec bring-up, still muted:** add narrowly addressed I²C operations at 0x18/0x42, no broad writes and no DFU code. Establish whether stock XMOS boots and supplies clocks without control commands; record version and 48 kHz WS/3.072 MHz BCLK. Do not drive GPIO9. Port the AIC3204 page/reset/clock/input/output sequence with explicit error checking, bounded delays and digital mute kept on. Reject absent clocks or failed transactions.
4. **Silent DMA:** install slave TX; preload zeros before enabling; count underflows, partial writes, timeouts and overruns; verify actual clock polarity/Philips one-bit delay and 32-bit channel alignment. On any fault, mute codec, hold amplifier low and stop streaming. Missing external clocks must not cause a permanent task wait.
5. **One bounded tone:** after explicit bench enable, use a few seconds of a 440 Hz sine at very low digital level with a ramp, first into a low-volume line-input monitor. Check left and right separately, then the speaker. Physical gain depends on codec/amp routing: a software amplitude is not an SPL guarantee. Test mute, Panic, unplug/replug jack and cold/warm restart before arbitrary patches.
6. **Main/FX integration:** centralize rate, validate memory admission at target rate, add safe storage layout and identity, then enable existing USB uploads. Exercise transitions, long delays, envelope durations, FX tails, rollback/restart, watchdog behavior and capture byte counts. Test loaded Wi-Fi only after wired control and output are stable.

Do not combine production instrument startup with the silent probe: production startup mounts storage, restores patches and starts DMA. The supplied project is useful precisely because those paths are absent. Steps 3–6 describe the original commissioning sequence. Their completed portions and remaining qualification limits are recorded in the current port status; the retained probe is not the shared application.
