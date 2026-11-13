# Project status — 13 November 2026

## Published on main

- Studio can install and verify the bootloader, partition table and application
  on a fresh XIAO ESP32-S3 or Waveshare AMOLED 1.8 V2 over USB. A physical XIAO
  flash completed in Studio, followed by a successful USB connection.
  [Firmware installation](docs/STUDIO.md#install-firmware-on-a-usb-board)
- Studio displays the current average audio CPU load, the peak since reset,
  free internal RAM and PSRAM, and output volume in percent and dB gain.
  Updated firmware also reports linked program RAM and application flash usage.
  The live CPU and volume readouts were checked on the XIAO. Both firmware
  builds passed their audits, and the browser checks and 41 host and native
  SuperCollider tests passed. Hardware verification of the new program-memory
  fields is pending. [CPU and resources](docs/STUDIO.md#cpu-and-resources)
- SuperCollider's `ESP32.discovered.onDone(_.postln);` lists reachable modules,
  including the connected USB module. Module IDs and aliases can be stored in
  SuperCollider environment variables for later commands or patterns.
  [SuperCollider setup](docs/SUPERCOLLIDER.md#install-and-start)
- The user confirmed hardware testing on a XIAO with the NS4168 I²S DAC and
  speaker amplifier. [NS4168 test and wiring](docs/HEADLESS.md#ns4168-i2s-dac-and-speaker-amplifier)

- **Named groups** are available in Studio and SuperCollider. Studio stores
  membership by permanent module ID. Use `ESP32.group` for uploads, controls,
  Main/FX commands and patterns, and `ESP32.groups` to list saved groups.
  The user confirmed group targeting and SC group volume control on hardware
  on 11 November. Existing sessions need a Studio restart and SC class library
  recompile to load the new group methods.
- **Identify modules** in Studio's Groups view sends a dedicated `IDENTIFY`
  command for a half-second 440 Hz cue at half the current output setting, with
  fades and an activity indicator. AMOLED and XIAO firmware builds and audits,
  the offline PCM regression, browser checks, and host/native SC checks passed.
  Hardware listening verification is pending.
- **Module argument validation** now explains the target/setting/value order
  when a group is accidentally supplied as a setting name. Local regression
  checks cover malformed keys and valid module/group volume messages.

The Groups/Identify release passed 90 host and native SuperCollider tests,
the browser logic checks, the sanitized PCM cue regression, and both firmware
build audits. Release firmware build identity is `d1bf9ef3a7df`.

## In progress

- **Unattended pattern soak and restart fix:** build `2ae9176d1d48` supersedes
  the first pattern image on XIAO-3eeb84. It passes 3,000 notes at 50/s over
  one minute, short 100/s and 200/s runs, array controls, malformed-transfer
  recovery, work-budget failure/recovery and 48 rapid restart/stop cycles.
  The first run exposed stream-slot exhaustion at restart 29; onboard programs
  now reuse one identity after safe Main recreation. Native checks cover 64
  cycles and retain FX/stale/cancelled-command protection. Both target builds
  pass audits. Original sound, controls, generations and 0% volume are restored;
  no test program remains. [Results](evidence/pattern-soak-restart-fixed-xiao-20261113.json),
  [limits and measurements](docs/SUPERCOLLIDER.md#unattended-xiao-soak-and-restart-check).

- **Experimental standalone patterns:** host `ESP32Program` compilation/export,
  a bounded off-audio stream VM, Main-hash binding, event scheduling, two-bank
  program storage, SC start/stop/query methods and Studio controls are implemented.
  The initial supported subset includes Pbind, nested/concatenated sequences,
  random generators, arithmetic and Pbjorklund/Pbjorklund2; it is not the complete
  SC pattern library. Computer checks and both firmware build audits pass.
  XIAO muted functional checks pass, including gate=1 suppression, leading
  rests, seeded Brownian/exponential controls, deep nesting, Panic, reboot
  autostart and deletion surviving a second reboot. SPIFFS deletion now avoids
  its unsupported access() operation, covered by a native regression.
  This first qualification used build `9dcafb858f7a`, superseded by the
  restart fix above. Its SoundBlock, saved generations, live controls and
  original 0% volume were restored.
  The 92 SC-reference cases, targeted host/native tests, browser checks and both
  target build audits pass. The deep test leaves 6,280 bytes of control stack;
  no DSP/nonfinite/queue/write/DMA faults are reported. See the separate
  [device results](evidence/pattern-xiao-20261113.json). AMOLED physical checks,
  loaded-network scheduling and broader long-run qualification remain pending.
  [Authoring, supported classes, resource bounds and limitations](docs/SUPERCOLLIDER.md#standalone-pattern-programs-experimental).

- **USB reliability:** macOS/native-ESP opening updates DTR/RTS together,
  removing a reproduced unintended reset (68 earlier lifecycle passes, including
  50 consecutive reopens). Buffered console build `b06188c54dbe` now batches
  protocol replies and passes 60/300-second unread and closed-port checks,
  12 Main replacement cycles with FX/bypass, and the corrected Main/FX sequence
  on XIAO-3eeb84 at 5%. Both selected builds pass audits; only XIAO was flashed.
  The user confirmed clean audio including the tail; 112 host/native checks pass.
  Other boards/OSes, Wi-Fi load and the earlier entirely unresponsive symptom
  remain outside this qualification. [Results](docs/USB_RELIABILITY.md)
- **TDelay.ar/kr** is implemented in the shared AMOLED/XIAO engine, bringing
  the native type count to 155. Silent tests compare exact trigger timing
  against SuperCollider and an independent countdown oracle, with sanitizer,
  restart, shared-scratch and invalid-input checks. It uses existing node state
  and no delay arena. Six XIAO PCM timing cases now pass over 100,588 checked
  frames. Physical AMOLED verification remains pending; boards need new firmware.
  [Host evidence](evidence/tdelay-host.json). Both firmware builds passed their
  audits, with graph/scratch/voice structure sizes unchanged.
  [Build records](evidence/tdelay-builds.json), [XIAO timing captures](evidence/tdelay-xiao-3eeb84.json)
- **Selective DSP optimisations** for smoothing, Klang/Klank, delays and MiVerb
  passed the combined-image comparison on XIAO-3eeb84: 28 pinned graphs, three
  fixed-seed trials on each image, matching output hashes and final RNG. Musical
  workloads improve by up to 6.42%; unchanged isolated SinOscFB/Formant graphs
  have small absolute slowdowns, retained in the results. Physical AMOLED
  verification remains pending; the broader XIAO sweep is recorded below.
  [Combined XIAO comparison](evidence/dsp-combined-xiao-3eeb84-summary.json)

## Broader DSP sweep and mixer experiment — 13 November 2026

XIAO-3eeb84 completed 332 long diagnostic traces on `b06188c54dbe`, covering all
154 inherited native types and every unary/binary selector at initial/control/audio
rate. There are 309 waveform passes, 22 statistical passes and the unchanged
Klang strict-float exception (separate conversion check: at most one S16 step).
No renderer faults, nonfinite values or arena-guard failures were reported.
Eight sustained hotspot graphs then completed three fixed-seed profiles each.
The finite `m5_addy` profiling attempt is unavailable because its Line ends the
voice before the measurement window finishes; its numerical trace passes.

The new default-disabled Sum3/Sum4/Pan2 mixer candidate passes strict native
state/scratch comparisons over 174 four-rate edge graphs and 1,628 inventory
graphs. Same-board timing improves the 24-Sum3/24-Sum4 banks by 20.39%/25.66%
and four musical graphs by 1.33–4.11%, but the 24-Pan2 bank regresses 5.64%.
The combined candidate is therefore **not promoted**; separate its changes
before further qualification. Both standard board builds and the experimental
XIAO image pass audits. Final XIAO firmware is the standard candidate-off
`814e14cdfc6c`, with original Main/FX, generations and live controls restored,
saved volume 5%, and Studio connected at that checkpoint. Standalone pattern work
began afterward and is tracked separately above.
[Results and reproduction](docs/CURRENT_DSP_SWEEP.md),
[sweep summary](evidence/current-inventory-summary-20261113.json),
[mixer comparison](evidence/mix-xiao-comparison-20261113.json)

## USB pattern endurance completed — 13 November 2026

After reconnecting XIAO-3eeb84, 25 lifecycle checkpoints and the complete
600-second SC/Studio/USB soak pass at 5%. SC submitted 9,609 updates including
the prelude; 9,600 events applied within the observed soak boundaries. There are
no new audio-error, late or rejected-event counts, and cancellation leaves the
continuous sound playing with its parameter held. Repeated identical-pitch notes
also retrigger with empty 32-byte deltas (52 acknowledged events in that capture).

Sampled average CPU was 64.0–66.0%, with a retained 102.1% reporting-window peak.
Internal free memory was unchanged at 81,711 bytes; PSRAM was 16 bytes lower,
within the 1 KiB test tolerance. Original Main/FX, generations and controls are
restored, 5% is saved, and Studio is connected; the boot did not change. Firmware
remains `b06188c54dbe`. All 118 host/native checks pass. Physical AMOLED and Wi-Fi
pattern/load tests remain separate work.
[Completed evidence](evidence/usb-patterns-xiao-3eeb84-resumed-20261113.json),
[test details](docs/USB_PATTERN_TESTS.md)

## Earlier paused USB pattern run — 13 November 2026

Real sclang/Studio/USB tests passed 23 lifecycle checkpoints on XIAO-3eeb84 at
5%: silent definition/creation, 8/16 Hz notes, overlapping retriggers, replay,
finite release, future-note cancellation, ownership handoff, Panic, stale-graph
protection, restart and the ESP32 CmdPeriod hook. The step marker measured
64–65-sample retrigger gaps; short-window gate-period errors stayed below 1.55 ms.
One expected stale-pattern warning occurred during replacement, without a flood.

The 16 Hz Comb Cloud/MiVerb control soak was paused at the user's request after
**149.78 seconds of clean sampled windows**. The 600-second run and its final
stop/hold assertions remain **incomplete**. Sampled average CPU was 64.6–66.3%;
one reporting-window peak reached 103.2%, with no new observed error counters.
Original Main/FX, generations and live controls are restored, 5% is saved and
Studio reconnected. That run was paused; the later completed run is recorded above.
[Details and resume requirements](docs/USB_PATTERN_TESTS.md)

## Buffered USB requalification — 13 November 2026

The selected source build is **`b06188c54dbe`**, retained on the XIAO after the
corrected tests. The original bytewise buffered candidate remains withdrawn;
its protocol throughput and tail-test timing were addressed in the new build.
A 0.1-second capture/download fell from 1.224 seconds to about 0.391 seconds in
three batched trials; this is a transfer measurement, not a DSP speed-up.

All four 60/300-second unread/closed cases retain the same boot, graph, controls
and 5% volume, with fresh nonzero PCM, stable memory and zero new diagnostic
counts. Twelve Main uploads, six temporary FX uploads and six bypass selections
also pass with unchanged saved generations. The final 30-second soak sent
**196 controls**, then passed the three sound fixtures, tail after Main Stop
(with a 50 ms exclusion window) and Panic silence. The user confirmed clean
sound, including the tail. Original Main/FX and live controls are restored,
**5% is saved**, and Studio is connected.

The real transport C checks exercise packet boundaries, backpressure, timeout,
short/invalid writes, resynchronization and USB-enabled/disabled startup. The
full host/native suite passes **112 tests**. Both profiles cross-build and pass
audits with unchanged DSP structure sizes; only the XIAO was physically tested.
AMOLED and Wi-Fi-under-load follow-up remain pending.
[Requalification summary](evidence/usb-buffered-requalification-xiao-3eeb84-20261113.json)

## Earlier USB and regression follow-up — 13 November 2026

The retained firmware is `5b23fabbfe7f`, with the macOS reconnect fix active in
Studio. Both selected firmware images were regenerated and audited after the
buffered-console experiment was withdrawn. No DSP equations or graph limits
changed. The corrected Main/FX test passed a 30-second soak, 197 controls,
three sound fixtures and digital tail/Stop/Panic assertions. The original
Main/FX, generations and live controls are restored; **5% volume is saved** and
Studio is connected. The retained host/native SC set passes 89 tests.

Two harness errors were corrected: command-stream reuse between runs, and soak
FX left enabled during the subsequent Main fixtures. The latter also caused an
over-budget failure on the retained image, so earlier buffered-image failures
cannot be attributed solely to its console driver. That candidate remains
unqualified; long-idle console/audio reliability is still open.
[Session summary](evidence/usb-reliability-xiao-3eeb84-summary-20261113.json)

## DSP hardware follow-up — 12 November 2026

XIAO-3eeb84 now has the selective DSP/TDelay firmware. Comb Cloud KR uses 6.42%
less DSP time; the six targeted smoothing graphs improve 52.60–62.51%, Klang
29.24%, Klank 25.48%, and the nine delay graphs 6.88–8.12%. The eight-saw patch
improves 1.51%; unchanged isolated Formant/SinOscFB graphs are slightly slower.
All 28 graphs retain matching fixed-seed output/RNG across images. These are
fixture-specific figures, not universal speed-ups.

A final 30-second Main/FX check at **5% volume** sent 199 controls with stable
free memory and no new fault, DMA-overflow, clipping or invalid-number counts.
Digital tail/stop/Panic assertions passed. Initial setup DMA events, an early
failed counter comparison and USB reconnects remain documented; the longer
soak and broad inventory sweep remain pending. Original Main/FX packages,
generations and live controls are restored, the empty FX slot remains empty,
and **5% volume is saved**. Studio is connected again. The user confirmed clean
playback, including the separate reverb tail, at 5% on 12 November; this is
recorded separately from the digital checks.
[Detailed results](docs/DSP_COMBINED_XIAO.md),
[final checks and restoration](evidence/dsp-combined-xiao-3eeb84-final.json).

## DSP qualification and standalone controls — 4 November 2026

A [selective production update](docs/QUALIFIED_DSP_UPDATE.md) is prepared on
`codex/qualified-dsp-defaults`, using the measured smoothing, Klang/Klank and
delay/MiVerb binding bodies. Native regression covers 369,393,664 samples plus
217 interleaved shared-scratch cases. Both board profiles and the XIAO rollback
configuration cross-built and passed audits. New image build **`49e3918de282`**
adds about 3.6 KiB of flash with unchanged graph/voice/scratch storage. No board
was accessed or flashed for this preparation; the combined-image hardware
check remains pending. The connected XIAO was last restored to `d627eccb77a7`.

The [fixed-seed follow-up](docs/DSP_SEEDED_PROFILING.md) completed on XIAO-ba1e48:
28 pinned graphs, 14 timing records and 240 normal/instrumented pairs passed.
The six eight-UGen smoothing graphs used 53–63% less DSP time; 16-partial Klang
and Klank graphs used 30% and 26% less. Narrow delay/reverb binding saved 7.6–8.8%
in the nine delay graphs and 3.4% in modulated MiVerb. Other core results were
mixed, including a Formant regression. Whole-graph figures are scoped to these
layouts; no candidate was promoted. See `evidence/dsp-seeded-xiao-summary.json`.

After that session, the XIAO was restored to standard build **`d627eccb77a7`**, all experimental
switches off. Original Main/FX packages, active instance settings, FX bypass and
saved **15% volume** were verified, with nonzero PCM after restoration. Studio
was running on its existing local address. The earlier interrupted USB attempt
is retained separately, and fixed profiling now borrows Studio's existing USB
connection. The optimisation register links the target results and regressions.

Studio output volume now displays percentage and gain in dB relative to 100%
volume (0.0 dB); mute displays −∞ dB. Browser tests and the live 20% / −14.0 dB
readout passed without changing device volume or firmware. This is a gain
readout, not measured signal-level dBFS. Extended checks cover all 101 levels,
native audio scaling under sanitizers and all 37 Studio host tests. A live keyboard
check stepped 15% → 14% → 15%, saved and refreshed the restored setting.
See `evidence/studio-volume-db.json`.

Function `.playESP32` now saves autonomous Main/FX blocks, including their initial
arguments; Main blocks restart automatically at boot. Function `.sendESP32` and
literal SynthDefs keep definition/instance semantics. Native SC simulator and
existing end-to-end pattern regressions pass. The current XIAO Function was
backed up and resent via the new path, then observed active/prepared with PCM
after a new boot without a play command. The user also confirmed automatic
playback after unplugging and reconnecting power without BOOT; see
`evidence/function-autoplay-xiao.json`. Recompile the
SC IDE Class Library once to load the extension change.

Studio now retains **Peak since reset** from every received CPU report and has
a **Reset peak** button. It clears the host measurement, excludes a potentially
straddling report and waits for a fresh full window. Host/browser tests and live
XIAO UI checks pass; no firmware update or audio-control command is used by reset.
See `evidence/studio-peak-reset.json` and `docs/STUDIO.md`.

The [first hardware session](docs/DSP_HARDWARE_RESULTS.md) completed on XIAO-ba1e48
with PCM5102A. All 50 selected replay cases matched baseline for both all-candidate
and delay/reverb-only variants. Three-run timing was mixed: the narrow variant
used 7.34% less DSP time in Comb Cloud KR and 1.37% less in eight-Saw, but 1.90%
more in triggered harmonics. Stochastic start states were not fixed across images,
so small differences need a controlled follow-up. No candidate was promoted.
Listening was confirmed clean, including the reverb tail.

At the end of the first qualification, the XIAO was on standard headless build
**`7afd20139b45`**, all new candidates
off and the large replay pack excluded. Final stereo/gate capture passed, and
saved Main/FX, instance states, 25% volume and FX bypass were restored at the end
of qualification. The user subsequently set volume to 100%; the autoplay update
above preserved that setting and the separate FX bypass. The
[timeboxed plan](docs/DSP_HARDWARE_TEST_PLAN.md) retains the unrun broader sweep,
soak and AMOLED checks. This session covers selected layouts of 42 native types
and 16 binary selectors, not the full supported inventory.

Studio now has a computer-tested **Audio resources** panel: average/peak audio
deadline usage and free internal/PSRAM from cached USB diagnostics. Polling reads
the host cache only; no device request or firmware change is added. Per-field
ages, unavailable Wi-Fi-only data and module identity guards prevent stale
readings being presented as live. After hardware qualification, Studio was
restarted with its session token and SC bridge port retained, reopened in Chrome
and connected to XIAO-ba1e48; the live resource panel was observed in the browser.
See [Studio](docs/STUDIO.md#cpu-and-resources) and `evidence/studio-resources-host.json`.

The computer-only optimisation review covers all 154 native UGens, 33 unary
and 40 binary selectors. The register records enabled project work, existing
FM1 block/initial-rate paths and experimental candidates, with desktop timings
including regressions. No supported entry remains unreviewed. This does not
claim that every candidate is faster or ready for the board.

All seven candidate switches remain **disabled by default**. Their combined
renderer matches production across 2,451 graphs plus 896 edge graphs at four
rates: 254,959,616 output samples, recursive state, RNG and arenas, with raw
scratch checked too. A composed negative-zero floor→atan2 test found a scalar
optimisation regression; the final implementation retains the pinned accumulation
path for those inputs. The corrected operator measurements supersede the initial
prototype records. Undefined/bounds/float-cast sanitizer checks pass. The optional
AddressSanitizer runtime stalls before main on this Mac; it is recorded as
unavailable, not a passing check.

The combined unlinked Xtensa object grows by 11,035 text bytes; public graph,
voice and scratch structures do not grow. Candidate functions' stack costs are
recorded separately from whole-call-stack qualification. Default compact/FM1
compiled DSP sources remain unchanged from `368d267`. No ESP32 or audio device
was accessed, flashed or tested during this pass. See the
[review and remaining hardware work](docs/DSP_OPTIMIZATIONS.md#complete-computer-only-review--4-november-2026).

Default source build **`eaf9cd626f8a`** cross-builds and passes the existing
compile/profile/instruction-placement audit for AMOLED and XIAO. All candidate
switches remain off in these images; neither was flashed. Their application
sizes are 1,680,384 and 1,337,728 bytes respectively. Records are
`evidence/dsp-review-amoled-default-build.json` and
`evidence/dsp-review-xiao-default-build.json`; installed firmware below remains
a separate baseline.

The [optimisation register](docs/OPTIMIZATION_REGISTER.md) now covers all 154
native types, 33 unary and 40 binary selectors. It distinguishes enabled project
changes, inherited FM1 paths and host-only candidates, with separate
implementation, host and hardware evidence. The packed MiVerb experiment remains
explicitly disabled. `python3 host/document_optimizations.py --check` validates
inventory coverage, record/link consistency and the generated page; it does not
perform a new hardware qualification.

## Installed baseline — 3 November 2026

The previous board-tested source build **`cd9fc38336ae`** has separately audited AMOLED V2
(16 MB flash, mono onboard audio) and XIAO ESP32-S3 headless (8 MB flash,
stereo I²S) images. It is installed and physically checked on XIAO-ba1e48;
the AMOLED image is cross-built but has not been flashed/listened to on this
revision. Records are `evidence/dsp-kernels-*-build.json`,
`evidence/dsp-kernels-xiao-final.json` and `evidence/main-transition-xiao-final.json`.
Earlier `33f68d0b61fb` installations are retained under
`evidence/amoled-8d50*-install.json` and `evidence/current-xiao-install.json`.
Firmware updates preserve saved Main/FX and settings. Fresh volume defaults to
20%; saved preferences take precedence.

Dedicated filter, Lag and unary kernels preserve float32 equations and sample
order. The four-rate differential test matched 26.2 million samples across 100
graphs; a wider 1,500-graph run matched another 6.1 million. Only otherwise-unused
new cache fields are normalized when comparing persistent voice state. Measured
XIAO rendering time decreased by 59% in the filter fixture, 60% in Lag, 64% in
cached-control unary math and 10.7% in the eight-saw/Resonz/MiVerb fixture. A
bit-exact packed MiVerb memory experiment was slower on the chip and is disabled.
See [DSP changes](docs/DSP_OPTIMIZATIONS.md).

Maintenance now fades output down/up for about 5 ms and holds it at zero through
the DMA drain/load, including preserved FX. Physical PCM capture confirmed 220
falling and 215 rising quantized frames, no new audio faults, preserved-FX zero
hold and inactive definition-only uploads. Saved Main/FX, instances, bypass and
25% user volume were restored. One final timing attempt lost USB acknowledgements;
a physical reconnect restored the original setup and a fresh run completed.
The failed run and recovery remain separate evidence. The user subsequently
confirmed that switching sounds cleaner; this listening result is separate
from digital PCM verification and an instrumented analogue measurement.

Signal storage now uses loader-planned audio-buffer reuse and independent
scalar values. Each Main/FX graph admits up to 256 nodes, 512 logical outputs,
2,048 input references and 192 simultaneously live audio buffers. Blocks remain
64 float32 frames. Host numerical/boundary/fuzz tests and physical capacity/load
records are separate: maximum accepted graph sizes are not a real-time promise.
See [signal-buffer design and evidence](docs/SIGNAL_BUFFERS.md).

The AMOLED's fixed 64 KiB LVGL pool is now in PSRAM, leaving internal RAM for
Wi-Fi and audio. Managed definitions can be triggered by touch without losing
SC control ownership; autonomous blocks remain independent of touch. The XIAO
PCM5102A temporary DAC passed left/right and Comb Cloud/MiVerb listening checks.
Standard commissioning installs the autonomous eight-saw test at 20% with
separate master FX bypassed; BOOT gating is an optional example.

Studio now has a live 0–100% output slider for the connected USB/Wi-Fi module.
Dragging coalesces writes; release saves the level across reboots. Browser
identity/error/coalescing checks, 34 Studio tests and XIAO command/save readbacks
passed. Existing global-volume firmware needs no update for the browser slider.

A stale retained SC pattern player was diagnosed in the real IDE: `isPlaying`
was true while `wasStopped` was also true and the device received no events.
`playESP32` now clears that state and starts a fresh remote stream. The fix was
loaded into the IDE, the user's pattern restarted and non-silent PCM confirmed;
the user confirmed hearing the pattern. Native tests cover the injected observed
state, cached-player replay, live-player reuse and existing lifecycle/cleanup.
See `evidence/xiao-sc-ide-player-recovery.json` and
`evidence/sc-player-restart-host.json`. This host-side fix requires no firmware
change.

## Earlier publication baseline — 2 November 2026

The following descriptions and test counts retain the scope of that earlier run.

The board runs **FM1 compatibility firmware `8b4cc4a9955a`**
(1,674,528 bytes), configured for 240 MHz, with internal Rings code
and 32 KiB instruction / 64 KiB data caches. Saved sound and master selections,
original source and global output volume survive updates.

The public-repository update now includes a README quickstart, current build/flash
instructions, refreshed browser/UI/storage/memory guides and the SC examples.
The documented fresh build matches all measured SDK configuration values and
passes profile/IRAM/strict-FP checks; see evidence/publication-build.json. The
full Studio/network/control/native-SC suite passes 70 tests both locally and from a clean staged checkout, and the 12 documented
portable suites pass. README SC snippets compile without executing or sending
messages. New raw logs and private setup/browser captures remain local; public
summaries and safe UI previews are retained. No additional firmware flash was
performed for the documentation/publication pass. See evidence/publication-checks.json.

The display now shows a green receive dot beside the battery (140 ms after
valid upload/control frames), plus Wi-Fi RSSI in dBm, sampled once per second.
Status/schema queries do not keep the dot lit; repeated valid frames still
signal reception. Controls shows the friendly module name and permanent ID.
Network sampling and display updates run outside the audio task. Real LVGL
snapshots check the layout, active green pixels, idle/offline states and module
labels; all 21 network/control regressions pass. The physical board's RSSI,
quiet queries, repeated frames and malformed-frame rejection were checked;
Main/FX packages, original source, live controls and the current output level
were retained.
Physical visual confirmation is still separate from the rendered layout checks.
See evidence/network-ui-device.json and evidence/network-ui-build.json.

SC module settings now use `ESP32.module(target, \volume, 0.5)` for 50% global
output, including aliases, groups and `\all`. The existing one-argument module
handle is retained. Calls reuse the firmware's smoothed `VOLUME` command and
update the Controls slider; no firmware update is required. Values are 0–1,
rounded to 1% resolution, and are live rather than saved to flash. Invalid
settings are rejected before transmission; concurrent recipient results report
individual failures, and module commands from each SC connection retain order.
All 30 bridge/network/control tests pass, including actual sclang against two
HTTP modules. See evidence/module-volume-host.json and docs/SUPERCOLLIDER.md.
Actual SC → running Studio → physical module volume changes also pass (25%,
then restored to its current 50%). Main/FX packages and instance state remained
unchanged. The updated class library is loaded in the IDE; its reload stopped
previous SC patterns. See evidence/module-volume-device.json.

The SC connection cleanup now catches failed sends, stops affected patterns
once, and keeps cancel/stop from throwing on a dead socket. Failed explicit or
automatic connection attempts return failed jobs; reconnect is safe from late
old-socket callbacks. All 33 bridge/network/control regressions pass, including
native send/cancel failure, real peer shutdown and refused-connection tests.
The running uploader and board were not restarted for this fix. The updated
extension is installed; the user's active local SC synth session was left
running, so the IDE will load it on the next class-library recompile.
See evidence/connection-cleanup-host.json.

Control-value compression is now automatic on firmware advertising
`control_deltas: 1`. The host sends changed float32 pairs, while the node expands
full per-stream/per-stage snapshots before queueing: other writers and out-of-order
future timestamps cannot alter a note's intended arguments. First events, changed
field sets, new revisions/reboots and idle gaps send full packets. Explicit cache
misses allow one full resend; uncertain acknowledgements never retry. Old firmware
receives full packets. Fixed baseline storage adds 17 KiB of PSRAM (remote state
24,968 bytes; status snapshot remains 512 bytes), with no audio-task allocation.

All 37 bridge/network/control regressions pass, including native SC with mixed
firmware recipients, repeated pitches, another writer, baseline recovery and
uncertain ACKs. Portable full/delta audio is byte-identical with interleaved future
events; trigger replay, field removal, queue rollback and stage invalidation pass,
alongside the existing 300 real EnvGen retriggers. The physical board passed muted
SC note tests: 52/37/32/37-byte payloads instead of 52 bytes each, no late/rejected
commands, zero queued events after completion, and correct values after an
interleaved direct set. The current packages, controls and 20% output are retained.
See evidence/control-deltas-build.json, control-deltas-host.json,
control-deltas-device.json and remote-control-host.json. Existing patterns need
only be restarted; no SC syntax change or class-library reload is needed for
compression. The previous SC-only disconnect fix still loads at the next class
library recompile, which was left to the user to preserve local SC synths.

Adjacent note releases/attacks now preserve a gate-low audio block. Previously,
when release and the next attack shared one tick (for example default legato
0.8 × dur 0.125 = delta 0.1), both changes could collapse to gate-high before
EnvGen rendered, losing the retrigger. The portable test renders 300 actual
EnvGen rising edges across gaps, exact joins and overlaps. Control state remains
7,560 bytes, with a 512-byte status snapshot; no new allocation is required.
The physical original degree pattern (dur 0.125 / delta 0.1) ran for 30 seconds
with the saved MiVerb master: 298 applied notes, zero rejected/late commands,
and no queued events after stop. Listening was confirmed consistent. The Main
ADSR also needed its named gate connected to EnvGen; the latest user upload
retains that correction. See evidence/note-join-device.json.

## SuperCollider sending and routed patterns

SC Function/String/literal SynthDef `.sendESP32` now saves a definition without
creating an instance. `ESP32.play(target, args)` creates Main with arguments set
before constructors; `ESP32.stop(target)` frees it. Stage handles support the
same Main/FX lifecycle. Function/SynthDef `.playESP32` combines upload and creation.
The first esp32Note can create Main; subsequent notes still reuse one voice.
Definition-only startup is persisted in package metadata without editing the
compiled graph. Literal bytes were verified identical on both test devices and
the physical board. Reboot retained Main/FX definitions inactive and unprepared,
including a gate=1 definition. Older saved packages retain their previous startup
behaviour; a new definition package boots silently until explicit creation.

All 60 host/native tests, portable lifecycle/FX/300-envelope-edge tests, storage
parser tests and the instrument adapter regressions pass. Physical Main/FX
creation, stop, initial-rate args, first-note creation and bypass recovery pass.
The user's original packages, source, live controls and volume (17%) were restored.
See evidence/definition-lifecycle-device.json and definition-lifecycle-build.json.

The installed SC extension adds Function/String `.sendESP32(target, args:, stage:)`,
selected-code sending (including a small `ESP32.gui` picker), ID/alias/IPv4/group/
`\all` targets, live named `.set`/`.setn`, and Main/FX helpers. It uses a private
loopback OSC/TCP bridge in the existing uploader, then the paired HTTP device
transport. Source/graph jobs are chunked above 30 KiB because SC's OSC builder
has a fixed message limit; nonempty blob prefixes avoid its empty-blob corruption.
Original source is retained and initial args are saved in the graph default table.

`Pbind` event types `\esp32Set` and `\esp32Note` route `\module` values from
Pseq/Prand. `.playESP32` installs stop/CmdPeriod cleanup and fresh IDs on replay.
The reply listener now survives CmdPeriod, which previously silently freed it
while leaving TCP connected and caused subsequent requests to time out. Pending
request deadlines are rearmed after clock clearing without extending them.
Native SC regression tests cover this failure, a stalled request across CmdPeriod,
and the five-second all-module pattern across schema/clock refresh.
Pattern cancellation now belongs to the player rather than inherited event
cleanup, so Pbindef source edits do not cancel the whole stream. Named proxies
reuse their ESP32 player and support normal Pbindef.stop. Requests retain FIFO
order per stream; delivery failure stops further device submissions from that
run, and stale callbacks cannot stop a replay or print a warning storm. Native
tests cover source-key edits, duplicate play, named stop, delayed failures,
natural note completion and deadline expiry without device submission.
The firmware applies transactions at audio boundaries, schedules finite note
releases, protects ownership, and rejects stale boot/activation revisions. State
uses preallocated PSRAM (portable host sizes: 7,560 bytes plus 512-byte snapshots);
no live updates write flash. Pattern lookahead defaults to 250 ms; this is control-
rate timing, not sample-locked multi-board playback or a scsynth voice pool.

All 33 Studio and 18 existing network tests pass, plus parameter/default tests,
portable control lifecycle tests and real sclang integration with two simulated
HTTP modules. Physical muted tests verified sending, initial/live args, ID/alias/
IP routing, Pseq/Prand, note release/stop and FX updates. Reboot restored initial
values rather than temporary live values and rejected an old-boot packet. Original
Main/FX/source, master selection and volume were restored afterward.

The current user patch has **eight Saws / 47 UGens**, a different graph from the
older two-Saw optimisation measurement. Its restored playback averaged **90.27%**
audio CPU, with no new DMA events or faults over 20.03 seconds, 15,847 minimum
internal free bytes and 4,204 bytes free control stack. This is not a matched
before/after CPU comparison. See docs/SUPERCOLLIDER.md, supercollider/examples.scd,
evidence/ide-device.json and evidence/ide-controls-steady.json.

## Main + FX and Omni Wi-Fi

Current firmware has one writable Main package and one writable FX package with
protected bypass. Main restores on boot; FX/bypass and output volume restore
independently. Legacy slots 2–8 remain archived and inaccessible. CONTROLS replaces
the numbered touchscreen library; the white code/play page is retained.

The uploader has fixed Main/FX destinations, separate drafts, Restart Main and
FX bypass. Single-module Wi-Fi and Omni mode share the checked package protocol.
Omni compiles once, concurrently uploads the exact graph/source to reviewed paired
online modules (up to eight simultaneous connections, 64 recipients), and reports
verification/errors per node. Starts are not sample-synchronised. Frozen
identities/generations and one-use, ten-minute reviews prevent recipient drift.

All 33 Studio tests and 18 real HTTP simulation tests pass. The two-module suite
checks concurrency, identical bytes, partial failure, stale destinations,
Main/FX isolation and exclusion of offline/unpaired nodes. Browser logic passes
with a DOM adapter; real LVGL play/scroll, volume, Main restart and FX controls
pass with 44,408 bytes of the 64 KiB widget heap free. Physical results are in
`evidence/main-fx-device.json`; multi-board RF timing is not established.
New Main and FX code saved and read back correctly on the physical board in
single-module Wi-Fi and Omni modes. A reset restored Main, continuous mode, FX
bypass and volume; original Main/FX graph/source and the original FX selection
were restored after testing. Only one physical module was available.
See docs/STUDIO.md and evidence/main-fx-build.json. Older slot histories below
refer to the previous library layout.

## Saw / Pulse crossfade optimisation — installed

The generated band-limited oscillator uses exact multiplication by 1/64 for its
sample crossfade fraction, with the original zero fraction in one-sample passes.
Tables, harmonic-count changes, singularity handling, phase rounding and memory
layout are unchanged. The two Saws in the same saved graph measure **197.81 →
169.28 µs** per block (14.42% less); normal whole-graph DSP measures **862.55 →
833.97 µs** (3.31% less), medians of three muted runs per image.

Normal playback averages **60.66%** audio budget (62.0% maximum one-second mean)
with Wi-Fi/display enabled, no new DMA events or faults across 20.03 measured
seconds, 15,775 minimum free internal bytes and 4,196 bytes free control stack.
The host regression passes 20,971,520 bit-identical samples/full voice state for
Saw/Pulse/Blip cases across four rates. Before/after 11.89-second fixed-seed board
traces match all 5,120 captured floats, peak/RMS and guard/fault checks. All 31
Studio tests pass. See docs/SAW_OPTIMIZATION.md and evidence/saw-crossfade-*.json.

## MiVerb clamp optimisation — installed

The generated target replaces two min/max calls per delay write with ordered
comparisons after the existing finite-value guard. Delay precision/layout,
quantisation, soft clipping and memory allocation stay the same; vendored source
is untouched. After the MiVerb change alone, the same 24-UGen Saw / Resonz / MiVerb graph averaged **62.24%**
audio budget (63.0% maximum one-second mean), with no additional DMA events
across 20.03 measured seconds. Minimum internal free RAM is 15,759 bytes and
control-stack headroom is 4,196 bytes.

Three matched muted profiles per image show median MiVerb time **777.58 →
454.40 µs** (41.56% less) and whole-graph DSP **1,174.42 → 864.14 µs**
(26.42% less). The host comparison passes 8,388,608 bit-identical output samples
and 400,000 quantiser probes. Fixed-seed board traces match all 5,120 captured
floats across 11.89 s with identical full-duration peak/RMS and no faults,
nonfinite values or canary failures. All 31 Studio tests pass.

See docs/MIVERB_OPTIMIZATION.md and evidence/miverb-clamp-*.json.

## Dynamic bank support

DynKlank and DynKlang compile to native Ringz/SinOsc banks. Both audio/control
outputs, changing parameters, nil defaults and mixed-rate inputs pass 12 SC NRT
comparisons (maximum sample error 1.28858e-5). The loader now admits the valid
mixed-rate Ringz/SinOsc parameter cases; DSP equations are unchanged. Two negative
rate checks and all 31 Studio tests pass. Four muted 11.89-second board traces
match native C within 1.24216e-7 and restore the original sound, volume, saved
library and master selection. Examples and scope: docs/DYNAMIC_BANKS.md.
The local uploader was refreshed with its existing session and draft retained.

## Current volume, CPU and random-start work

- SLOTS has a fixed white-on-black output volume slider, 0–100%, default 100%.
  It scales after master FX, uses a 20 ms gain ramp and saves on release. A muted
  save preserves source/FX state. The user confirmed smooth operation and chose
  30%; that setting survived the kernel firmware update.
- The corrected Comb cloud remains in slot 7. Measured average audio CPU fell
  from 57.86% to 49.76% after exact kernel optimizations; recent peaks fell from
  78.1% to 66.9%. Per-UGen profiling identified Decay2, Dust and SinOsc costs.
- The user's control-rate Dust/Decay2 variant is saved in slot 8: 29.02% average,
  43.4% recent peak, still 56 nodes / 60 signals and a 32 KiB delay arena. The
  user confirmed similar, clean sound. Oscillators and CombC remain audio-rate.
- Slot 6 now holds the five-mode Klank cloud, replacing Sound block with user
  permission. It is one mono resonator bank duplicated to both outputs. The
  fixed-table version used about 10% CPU (user observation), four nodes and no
  delay arena. Its source remains in examples/klank-cloud-fixed.scd.
- The revised Klank source uses 15 initial-rate Rand UGens, choosing frequencies,
  amplitudes and ring times at start. Normal sound loads receive fresh hardware
  seeds; note starts advance a per-load seed sequence. Maintenance and pending
  constructor retries preserve the active seed. Diagnostics remain seed zero.
  Array.rand still behaves as SC language code: its compiled numbers are fixed.
  Three hardware reloads chose distinct seeds with the same graph hash; the
  Rand-based slot 6 measured 10.62% mean / 17.0% recent peak and zero audio errors.
  Other saved sound slots and both master packages/selections were unchanged.
- Native tests cover 46,137,344 bit-identical samples across 14 graphs, plus
  4,194,304 for the KR block, with identical RNG sequences and delay memory.
  Thirty Studio tests, volume/seed lifecycle tests and LVGL slider tests pass.
  Local AddressSanitizer hangs during runtime startup; undefined-behaviour and
  bounds checks completed. Hardware counters were zero in recorded audio checks;
  recent-window peaks are not lifetime maxima or a worst-case qualification.
- See docs/PERFORMANCE.md, docs/STUDIO.md, evidence/comb-kernel-equivalence.json,
  evidence/comb-ugen-profile-after.json, evidence/comb-kr-live.json and the
  random-starts evidence. Earlier measurements below retain their image identity.

## Continuous blocks, master slots and host Studio

- The local browser accepts named SynthDefs, compiled files and anonymous
  `{ sound }` / `({ sound }.play)` blocks. Blocks start on load without touch;
  there is no added envelope or gain. Panic stays stopped until reload.
- Continuous maintenance preserves a running block. Removed a second Panic at
  the final parking transition that had erased its resume state.
- Sound block occupies slot 6 (77 nodes / 86 signals). Comb cloud occupies slot 7
  (56 nodes / 60 signals, 32 KiB delay arena). Each oscillator gets one Rand;
  Decay2's slow time modulation uses control rate, as required by the loader.
- Separate master bank: protected Bypass 0 plus uploadable FX 1, initially blank
  stereo In/Out code. Master selection and saved generations are independent of
  sound slots. Both the browser and device library select the master route.
- Current firmware advertises atomic INSTALL: activate and save form one console
  transaction, preventing queued screen selection from saving another patch.
  Studio verifies graph, source and metadata after installation.
- Thirty Studio tests, continuous lifecycle emulation, master routing and LVGL
  library checks pass. Browser/device verification saved and read both master FX
  and Comb cloud. Existing sound slots 0–6 and 8 were retained.
- Comb cloud's 5 Hz delay LFO changed from audio to control rate: board average
  audio budget fell from 76.32% to 57.72%; recent peaks from 93.8% to 72.7%.
  These are five one-second windows per version under the same blank master,
  not whole-chip utilisation or lifetime maxima. The user confirmed about 57%.
  Sample rate, float32 precision, gain and cubic delay interpolation are unchanged.
  Audio error/clipping/nonfinite counters were zero in captured windows.
- See [STUDIO.md](docs/STUDIO.md), `evidence/master-slots-build.json`,
  `evidence/master-slots-live.json` and `evidence/comb-cpu-optimization.json`.

## Dark slots view

- Both top titles now start 28 pixels from the left after the additional
  eight-pixel adjustment. The approved battery position remains 20 pixels from
  the right. Subtitle positions are unchanged. See evidence/title-inset-device.json
  and title-inset-build.json.
- The slots header/list now use a black background with white text and outlined
  rows. Empty slots are dimmed; the battery adapts to the dark header while
  retaining its low-battery warning. The white code screen and light footer
  containing CODE, CPU/status and PANIC retain their existing appearance.
- Existing native gesture checks pass. Actual device captures verify both
  pages and default code startup. Saved library, selection and FX settings
  are unchanged, with no new output errors. The board is left on SLOTS, slot 5,
  after Panic. See evidence/slots-dark-device.json and slots-dark-build.json.
- App: 884,880 bytes; fixed UI heap free: 38,704 bytes. Audio code is unchanged.

## Audio CPU display

- Both screens now show CPU percentage in the footer, above READY/PLAYING.
  This is the latest one-second average audio processing budget, excluding
  I2S waits. A recent block at 70% turns the label amber; at 100% it turns red.
  Missing telemetry displays CPU --. It is not total utilisation of both cores.
- Native LVGL checks and actual panel snapshots pass. Silent board checks
  verified the percentage calculation for every captured window, with about
  15.7% for Touch buses running at gate zero and 10.6% after Panic. Saved slots,
  selection and FX settings remain unchanged; no new output errors were reported.
- App: 884,512 bytes (704 more); fixed UI heap free: 40,344 bytes (352 fewer).
  Timing counters reuse existing block measurements; division/formatting and
  drawing stay off the audio task. See evidence/cpu-meter-device.json and
  evidence/cpu-meter-build.json. That check left code open on slot 5 after Panic.

## Code-first instrument and control buses

- Two screens: original source/play by default, and a scrollable SLOTS library.
  Occupied rows load and return to code; startup restores the saved selection.
  Battery remains top right and PANIC bottom right. Body/header flick selection,
  the separate pad/sliders and the DELAY page are removed from the touch UI.
- Code plays X/Y/gate. Separate 48-pixel right and 40-pixel bottom strips scroll
  vertically/horizontally. Touch ownership persists across region boundaries;
  scrolling never posts notes or updates X/Y. Coordinates are scroll-independent.
- Added 32-channel In.kr input to the generated target engine; vendored sources
  remain unchanged. X/Y/gate occupy 0/1/2. Bus-driven patches run at load with
  gate low and retain state across touches; legacy patches keep their controls.
- Added Touch buses to the previously empty slot 5, with original source and
  a verified source/graph pair. All five original saved packages/generations
  and delay settings are unchanged. The source has 29 lines to try both strips.
- Real LVGL tests pass for playing, region ownership, scrolling, list loading,
  busy/Panic, source ownership and 64 KiB documents. Fixed UI heap free: 40,696
  bytes (25,304 more than the preceding layout; still within the reserved pool).
- Host bus bounds/lifecycle checks pass under sanitizers. The 28,672-frame SC
  comparison peaks at 1.576e-5 error. Four muted board windows differ from
  native C by at most 9.314e-8. Seven legacy voice/operator matrices (1,960
  cases) and master-delay comparisons through five seconds pass again.
- Before the CPU meter, FM1 app: 883,808 bytes; compact app: 883,360 bytes. Voice state grows by eight
  target bytes for the bus pointer/count; bus values use 128 bytes per instrument.
  DSP float precision and existing equations/tables are unchanged.
- Actual panel snapshots and restart logs verify both pages and restoration of
  slot 5 into code. The user confirmed playing, release, scrolling without
  sound and slot selection returning to code on 1 November 2026. See
  evidence/code-slots-user-confirmation.json,
  evidence/code-slots-device.json, code-slots-regression-device.json,
  code-slots-final-state.json and [TOUCH_BUSES.md](docs/TOUCH_BUSES.md).

## Touch-controller investigation — 1 November 2026

- Added diagnostic `q`: park/mute audio, disable the normal touch reader and
  capture raw controller registers for 60 seconds, then resume in CODE.
  No touch/power configuration registers or saved patches are changed.
- Device ID bytes are `B7 41 02`. During the user's confirmed one- and two-
  finger sequence, 3,000 reads completed without I2C errors. Raw register 0x02
  reported only 0 or 1 contacts, before the driver clamps the count.
- Reliable two-finger scrolling cannot be based on this observed output.
  The implemented code-first redesign uses dedicated scroll strips beside and
  below the XY area; it does not rely on two-finger recognition.
- At capture time, saved selection (Phase FM, slot 2), library generations and
  delay settings were unchanged. USB needed one physical reconnect after flashing.
  See `evidence/touch-probe-run3.json` and `host/probe_touch.py`.

## Swiping across code and pad

- Switching was previously restricted to the title bar. Quick left/right
  flicks now also work across the code body and play pad, using the existing
  queued loader and preserving CODE after selection.
- A flick travels at least 88 pixels predominantly horizontally and releases
  within 500 ms. Vertical drags and slower/held drags retain source scrolling
  and pad pitch/level control. The pad releases its note before switching.
- Real LVGL pointer tests cover both body directions, missing release
  coordinates, slower/held/vertical drags and all existing header/busy/page
  behaviour. Native UI heap free: 15,392 bytes. FM1 application: 910,096 bytes.
- Board package/source switching checks and screenshots are recorded in
  `evidence/body-swipe-device.json`. Those use USB selection diagnostics;
  physical touch confirmation is separate. DSP math/tables are unchanged.

## Battery and PANIC placement

- Live AXP2101 battery icon at the top right, with gauge percentage, charging,
  USB/no-battery and unavailable states. Read-only telemetry polls every five
  seconds from the control task; power/charger configuration is untouched.
- One PANIC button stays at the bottom right across all four pages, including
  busy states. PLAY fits PATCHES/CODE/DELAY alongside it; CODE has a shorter
  viewport and bounded line/column footer so text stays clear of the button.
- Native LVGL checks pass with 15,400 bytes free in the fixed 64 KiB UI heap.
  The FM1 application is 909,728 bytes. Board screenshots and navigation
  results are in `evidence/battery-layout-device.json`; build records are
  `battery-layout-build.json` and `battery-layout-compact-build.json`.
  DSP math/tables are unchanged.

## Title swipes

- Swipe left/right on the title bar in PLAY or CODE for the next/previous
  occupied saved slot, wrapping around the library and including factory 0.
  The pad and source body retain their drag controls; CODE stays open after
  switching. Previous sound is stopped through the existing patch loader.
- Native LVGL gesture tests cover sparse slots, wraparound, pending/busy/
  rejected requests and CODE retention. Fixed LVGL heap free: 15,352 bytes.
- Board checks cover ten queued selections, exact graph/source/metadata
  identity, CODE display and recovery from an upload rejecting navigation.
  Device selection uses USB diagnostics; a physical finger swipe is still a
  manual check. No saved patch writes are made.
- FM1 application: 908,896 bytes; compact UI: 908,592 bytes. Source lexer and
  package tests pass again. DSP calculations and tables are unchanged.
  See `evidence/swipe-device.json` and [CODE_VIEW.md](docs/CODE_VIEW.md).

## Original-source CODE page

- White background, Monaco-style DejaVu Sans Mono, requested syntax colours,
  line numbers and two-axis drag scrolling. No source editing/recompilation on
  the board. Strings and backslash symbols stay green; classes/UGens/Patterns
  blue; ~globals orange; arg/var red; numeric/built-in literals purple.
- Active package source is copied into owned PSRAM. Factory source is bundled
  with a verified graph/source pair. Missing text is identified explicitly.
- Lexer guard-page/sanitizer tests, real LVGL interaction and 64 KiB edge cases
  pass. Actual device snapshots verify source switching and all colours.
- Three held-note/scrolling tests report zero new output errors; seven muted
  matrices plus master-delay echo checks pass. Saved packages are unchanged.
- That source-view image (`cabbeb035d5b`) is 908,032 bytes; audio results in this
  section were captured on it. Its compact UI build also compiles. See [CODE_VIEW.md](docs/CODE_VIEW.md) and
  `evidence/source-device.json` for exact scope and measured memory/timing.

## Earlier optimization follow-up

- Removed duplicate whole-buffer clearing from bound Rings construction while
  preserving standalone initialization and all float32 calculations/tables.
- Fixed startup fragmentation by reserving large allocations and task stacks
  before display/NVS setup, with safe PSRAM fallback for the optional arena.
  Fixed the LVGL task's overly restrictive allocation request as well.
- Compared code placement, a 66 KiB internal arena and larger caches. The
  selected caches preserve more memory and improve original Rings 2/5/6 steady
  costs by **27–28%**. The optional arena is disabled by default.
- **26 muted matrices / 7,280 cases** pass within one S16 step of native C.
  **24 long guarded runs** pass; every captured stereo window matches exactly.
  Master-delay echo windows through five seconds also match exactly. The full
  1 MiB synth arena passes normal start/release and early cancellation.
- Nine 30-second control/display/master-delay exercises report zero new output
  error events. Existing voices reach **738 / 663 / 731 µs** (Filtered Tone /
  Phase FM / Harmonic Mix), all below the **1,016 µs** margin target.
- Moving-control Rings 2/5/6 still reach **1,578 / 1,644 / 1,606 µs**, exceeding
  the **1,451 µs** block deadline at some settings. Only Rings 3's tested musical
  graph meets the 70% margin. No Rings graph was promoted to the catalog.
- The selected live tests retain at least **47,715 internal bytes**, a
  **38,912-byte** largest free block and **8,280 / 11,760** unused audio/control
  stack bytes. Both full 1 MiB PSRAM arenas remain available.

See [the optimization report](docs/RINGS_OPTIMIZATION.md) and
[evidence/rings-optimization.json](evidence/rings-optimization.json) for the
configuration comparisons, grades and reproducible commands. The earlier
startup failures and the dedicated-arena Rings 6 DMA overflow remain recorded;
the selected cache configuration passes the repeated output checks.

## Earlier broad UGen testing


- **338 long hardware graph runs** cover all **154 UGen types**, all **258
  type/rate combinations observed in the fixture set**, and every **33 unary /
  40 binary selector at initial, control and audio rate**. Each run checks
  11.89 seconds of output and memory guards, with 40 captured stereo windows.
- Grades remain separate: **315 waveform-limit matches**, **22 statistical-only
  matches**, and **one Klang strict-float mismatch** which stays within one
  S16 output step. No long run reported a renderer fault, nonfinite output or
  damaged arena guard. Statistical consistency is not trajectory identity.
- The Gendy3 64-point audio-rate and slow control-rate failures reproduce with
  the original pinned engine and pass after the fix. Sixty-second host
  regressions cover five sample rates and five explicit seeds. Both failing
  cases now capture identically on the board. The independent host Gendy state
  oracle still passes 2,795,520 samples / 707,707 distribution inputs.
- The fixed-source **1,444-fixture SuperCollider reference suite** and a fresh
  **1,560,000-input sanitizer fuzz run** pass. Longer independent SC recordings
  add waveform and statistical evidence, described in the report below.
- **24 thirty-second rounds / 12 minutes** of reduced-level playback and UI
  stress, plus **60 patch activations**, completed without reported output,
  numerical, clipping, queue or 70%-margin faults. Eighteen rounds were on the
  pre-fix diagnostic image; six repeated on the fixed image.
- The final fixed-image maxima were **939 µs Filtered Tone, 918 µs Phase FM and
  952 µs Harmonic Mix**, against a 1,451 µs block. At least 113,691 internal
  bytes, a 63,488-byte largest internal block and 8,316 unused audio-stack bytes
  remained during those exercises.
- Muted cost profiling separates constructor and live-block work. **Rings
  models 2/5/6 need performance work**: their tested live blocks alone took
  approximately 1.4–1.6 ms before the master effect. Dense all-operator banks
  also exceed the audio deadline. Numerical support does not certify arbitrary
  graph combinations for real-time use.

See [docs/EXTENDED_TESTS.md](docs/EXTENDED_TESTS.md) for methods, grades, the bug,
CPU costs and limitations, [docs/UGEN_SUPPORT.md](docs/UGEN_SUPPORT.md) for the
per-UGen/operator ledger, and
[evidence/extended-validation.json](evidence/extended-validation.json) for the
machine-readable summary. Hardware testing and sound were explicitly authorized
by the user; the preceding computer-only stage is retained in its own evidence.

## Implementation and scope

The optional FM1 profile accepts the full pinned renderer set with 160 nodes,
192 signals and 1,024 references. Graphs and scratch live in PSRAM; voice states
remain internal. One musical voice and the persistent master effect render
serially at requested 44.1 kHz / 64-frame blocks. There is a separate 1 MiB synth
arena and 1 MiB five-second master-delay arena. The synth clears in 4 KiB chunks,
with a constructor block; full-arena preparation is approximately 373 ms by
calculation, not an external latency measurement. Earlier hardware tests verify
full-arena startup, early cancellation and release.

Ordinary voices require live `freq`, `amp`, `gate`; bus-driven graphs and marked
continuous blocks have separate admission paths. Master uploads accept stereo
bus-0 input/output independently of the voice controls. Arbitrary multi-node
server routing and multiple musical voices are not implemented. Compact
mode retains its narrower sine-family/exact-catalog policy; catalog entries stay
candidates for changed source. Its qualification is separate from this FM1
profile's numerical and workload evidence.

The vendored snapshot at `00ac338904304e87845477808e598ef973f49b52` remains
byte-identical. The audited target generator changes checked capacities, adds
precleared binding, corrects Gendy3 closing-segment bounds and removes redundant
bound Rings clearing. Main DSP remains
float32, with existing compensated accumulators and strict compiler settings;
there is no additional precision reduction or fast-math change.

The current target record is
[evidence/source-view-build.json](evidence/source-view-build.json):
908,032-byte application, 71,488 bytes of fixed internal engine state,
90,012 bytes of fixed PSRAM engine state and two 1,048,576-byte arenas.
Stacks, caches, UI, package buffers and drivers are separate. The earlier
broad-sweep image remains in `evidence/fm1-gendy-fixed-build.json`. The muted
long diagnostic uses a temporary additional guarded arena while codec/DMA are
parked. Build records distinguish source IDs, selected configuration and binary
hashes.

## Remaining work

Further CPU work is needed for moving-control Rings 2/5/6 and dense operator
graphs. Longer continuous soak,
wider parameter domains, external clock/latency/continuity measurements and an
identical-state hardware oracle for divergent generators remain open. The earlier
intermittent USB reset problem is not claimed fixed. Sequencing, a second musical
voice, motion and microphone processing remain later milestones.

Earlier stages remain recorded in [docs/HARDWARE_HISTORY.md](docs/HARDWARE_HISTORY.md),
`evidence/fm1-device-smoke.json`, `fm1-device-synth-memory.json` and the
`delay-*` evidence. The older interrupted delay-image repeat remains explicitly
incomplete; it has not been overwritten by the new independent tests.

## Wi-Fi uploader — verified on the board

The uploader provides USB / Wi-Fi selection, discovery and manual-IP fallback,
permanent MAC-based module IDs, and USB-only setup/pairing. Station + HTTP startup
now succeeds after moving the 35,752-byte master voice to PSRAM and reducing the
control stack to 8 KiB; the instrument voice/audio stack remain internal.

The physical module `esp32-2884853ad390` joined the selected 2.4 GHz network. Sound
slot 1 compiled from its saved source, uploaded and read back over HTTP in 4.75 s;
its graph hash remained identical. The master FX bank also saved/read back over
Wi-Fi without changing the sound. Competing writers, wrong IDs/keys and immediate
client handoff were checked on the real receiver. The original test selection
(factory slot 0, stopped) and volume (100%) were restored.

Before the clamp optimisation, the 111-UGen MiVerb test averaged 94.94% audio budget, with 95.3% maximum one-second
mean and 139% recent peak. DMA event warnings reached 54 around installation /
initial settling, then stayed unchanged across 22.03 measured seconds of steady
playback. No synthesis faults, nonfinite samples, clipping or failed/partial
writes were reported. This patch has little timing margin; the test does not
qualify every graph or prove that Wi-Fi has zero overhead.

Twelve network/identity tests and 31 existing Studio tests passed. Evidence:
`network-build.json`, `network-device.json`, `network-live.json`,
`network-master-live.json`, `network-host.json`, `network-connected.jpg`.
