# Recorded evidence

Reports cover development from 30 October through 4 November 2026. They retain
the source/build IDs and test scope from their own runs. An old timing or board
measurement does not automatically qualify a newer image or another graph.
[STATUS.md](../STATUS.md) identifies the latest installed image and open limits.

The publication checks are summarized in `publication-checks.json`, including
a fresh build (`publication-build.json`), clean-checkout tests, README syntax and
relative documentation links.

## Current workflow and compact controls

The 4 November computer-only review adds these records. No ESP32 connection or
write occurred. All candidate switches remain disabled; native timing gains and
regressions retain their fixture/compiler scope.

| Records | Scope |
| --- | --- |
| `studio-volume-db.json`, `studio-volume-db-preview.jpg` | Percentage and output-gain dB formatting, browser regressions and live readout; no volume write or firmware change |
| `dsp-seeded-host.json`, `dsp-seeded-xiao-*.json` | Deterministic profiler tests, audited images, 28-graph / 240-pair XIAO qualification and verified restoration; the interrupted USB attempt is retained separately |
| `function-autoplay-host.json`, `function-autoplay-xiao.json` | Native SC Function autoplay/default persistence/single activation with literal-definition compatibility; current XIAO block active with PCM after an observed new boot, physical confirmation tracked separately |
| `studio-peak-reset.json`, `studio-peak-reset-preview.jpg` | Host peak accumulation/reset, whole-window waiting, cache/identity races, fake-device HTTP tests and live XIAO UI reset observation; no firmware reset or audio-control mutation |
| `dsp-qa-xiao-summary.json`, `dsp-qa-pack.json` | First bounded physical session: 50-case replay identity/coverage, mixed timing results, clean listening and final standard firmware/restoration; not the full inventory |
| `dsp-qa-xiao-{baseline,all,selected}.json` | Baseline plus full/narrow candidate float/state/scratch/arena digest streams; both comparisons match, including the expected fault-domain case |
| `dsp-qa-xiao-*-timing.json` | Three 1,024-block normal/probed trials for four matching graph hashes; live stochastic snapshots differ across images, so smaller differences need fixed-seed confirmation |
| `dsp-qa-xiao-*-build.json` | Per-image configuration/profile/compile/IRAM audits; `restored-build` is the final standard image, while `final-build` is a compiled-only narrow non-QA image |
| `dsp-qa-xiao-listening.json`, `dsp-qa-xiao-final-smoke.json` | User-confirmed clean PCM5102A sequence/tail; separate final standard-image 330/660 Hz stereo and gate-release checks, original saved setup restored |
| `studio-resources-host.json` | Cached CPU/RAM panel; simulated USB/Wi-Fi/disconnect identity checks, field-age expiry and browser rendering logic; no module accessed or firmware changed |
| `studio-resources-xiao.json` | Read-only live Chrome observation of the connected XIAO's new resource panel after Studio restart; current-user-state readings, not candidate timing evidence |
| `dsp-review-summary.json` | Complete 154/33/40 review, all results references, source-default audit against `368d267`, unlinked code costs and known limits |
| `dsp-review-amoled-default-build.json`, `dsp-review-xiao-default-build.json` | Default build `eaf9cd626f8a`, candidates disabled; both images cross-built and audited for compile settings, loader inventory, table bytes and configured instruction placement; neither flashed |
| `dsp-operators-final-host.json` | Corrected scalar/shared paths and 36 audio binary specialisations, signed-zero compositions, independent switches, four rates and native bank timing |
| `dsp-binding-host.json`, `dsp-routing-host.json`, `dsp-chaos-host.json`, `dsp-core-host.json` | Individual and cumulative numerical/state/arena comparisons, per-type native measurements, Xtensa object/stack costs; regressions retained |
| `dsp-all-host.json` | All seven candidates versus production; 2,451 graphs plus 896 four-rate edge graphs, 254,959,616 samples, constructor/raw scratch and recursive state/RNG/arena identity |
| `dsp-signed-zero-regression.json` | Reproduced audible floor→atan2 difference and corrected fallback witness; initial operator records are superseded |
| `dsp-address-runtime.json`, `dsp-address-runtime-investigation.json` | Optional AddressSanitizer initialization failure before main, also reproduced with an empty C program; sampled startup stack and stopped-probe scope retained; not a passing DSP run |
| `dsp-chaos-initial-benchmark-rejected.json`, `dsp-core-initial-host.json` | Initial harness/cache comparison rejection and earlier prototype scope; not current performance guarantees |

The 3 November update adds the following scoped records:

| Records | Scope |
| --- | --- |
| `dsp-candidates-host.json`, `dsp-candidates-defaults.json` | Computer-only six-UGen/twenty-binary candidate comparisons, independent switches, wider graph regression, native throughput and offline Xtensa object size; production switches remain off, no board access or hardware timing |
| `dsp-kernels-summary.json`, `dsp-kernels-xiao-before.json`, `dsp-kernels-xiao-final.json` | Three-run physical rendering-cost comparison; exact graph hashes, restored packages/settings and configured 240 MHz conversion |
| `dsp-kernels-host.json`, `dsp-kernels-inventory.json`, `dsp-kernels-reuse.json` | Four-rate exact kernel comparisons, wider 1,500-graph check and shared-scratch/lifetime regression |
| `dsp-kernels-xiao-packed.json`, `miverb-packed-host.json` | Numerically equivalent packed MiVerb experiment; target timing regressed, so disabled by default |
| `main-transition-xiao-final.json` | Actual upload/restart PCM fades, zero hold through preserved FX, inactive definition-only behavior and saved-state restoration; analogue listening separate |
| `dsp-kernels-xiao-final-interrupted.json`, `dsp-kernels-usb-recovery.json` | Failed USB handoff, physical reconnect and private-backup restoration; not counted as a successful timing run |
| `signal-reuse*.json` | Buffer lifetime/aliasing comparisons, inventory, fuzz/boundary checks and separate physical XIAO/AMOLED admission and timing records; see [signal buffers](../docs/SIGNAL_BUFFERS.md) for limits and failed overload fixtures |
| `current-headless-build.json`, `default20-amoled-build.json` | Current source build `33f68d0b61fb`, separately compiled for XIAO stereo and AMOLED mono hardware |
| `current-xiao-install.json`, `amoled-8d50*-install.json` | Matched physical identities, image verification and startup scopes; private full-flash backups remain excluded |
| `current-xiao-autoplay-check.json`, `amoled-*-audio-check.json` | Standard autonomous listening block, separate FX bypass, timing and reported faults; listening confirmation is recorded separately |
| `managed-touch-*.json` | Managed definition touch/remote gate ownership, startup and physical press/release scopes; aborted tool attempts are retained as such |
| `studio-volume-host.json`, `studio-volume-xiao.json` | Browser gesture coalescing/identity guards, HTTP tests and physical volume/save acknowledgements; not an analogue gain-ratio measurement |
| `xiao-sc-ide-player-recovery.json`, `sc-player-restart-host.json` | Stale retained-player diagnosis, actual IDE note/PCM recovery and isolated native restart regressions |
| `xiao-pcm5102a-*.json` | Temporary external DAC listening tests, channel checks and source-specific load; the initial CPU-percentage guard is retained separately |

Earlier counts and installed-image descriptions below describe their own runs,
not an automatically repeated qualification of the latest source.

| Record | Scope |
| --- | --- |
| `control-deltas-build.json` | Installed firmware `8b4cc4a9955a`; compiler/profile/IRAM checks and image/configuration hashes |
| `control-deltas-device.json` | Muted physical SC→host→Wi-Fi note test, repeated pitch, interleaved set, baseline recovery and original-state restoration |
| `control-deltas-host.json` | Native SC against modern/legacy HTTP simulators; exact transmitted payload sizes and other-writer semantics |
| `remote-control-host.json` | Portable full/delta PCM identity, trigger/field/queue/stage cases, lifecycle and 300 actual EnvGen retriggers |
| `connection-cleanup-host.json` | Native failed send/cancel, peer shutdown, refused connection and safe reconnect regressions |
| `module-volume-host.json`, `module-volume-device.json` | Targeted/group/all module output scaling; native SC and physical checks kept separate |
| `definition-lifecycle-build.json`, `definition-lifecycle-device.json` | Saved definitions versus instances, raw literal bytes, initial-rate creation and inactive reboot behaviour |
| `ide-host.json`, `ide-device.json`, `ide-pattern-lifecycle.json`, `ide-cmd-period-device.json` | SC compilation/routing, large sources, patterns, cancellation, CmdPeriod and physical delivery scopes |
| `note-join-build.json`, `note-join-device.json` | Gate-low block at adjacent release/attack boundaries and physical pattern test |
| `main-fx-host.json`, `main-fx-build.json`, `main-fx-device.json` | Fixed Main + FX layout, concurrent upload simulation and physical node checks |
| `network-host.json`, `network-device.json`, `network-live.json`, `network-master-live.json` | Pairing/identity/error handling and actual single-node LAN transfers |
| `network-ui-build.json`, `network-ui-device.json` | RX activity, RSSI, Controls identity and preservation checks; physical visual confirmation is separately labelled |
| `ui-host.json`, `ui-*-preview.png` | Real LVGL/widgets with simulated input; screenshots are host layout previews, not panel photographs |

The latest host bridge/network/control run passes 37 tests. The broader Studio/bridge/network/control publication
suite passes 70 tests. Host simulators do not establish
multi-board RF timing, maximum router capacity or sample-synchronized starts.
The compact-control physical test is muted: it establishes protocol/state and
queue behaviour, not a listening-quality certification.

## DSP coverage and optimization

| Records | Scope |
| --- | --- |
| `fm1-validation.json`, `fm1-fixed-reference.json`, `extended-validation.json` | Pinned UGen/operator coverage, SC references and explicit statistical/drift classifications |
| `fm1-hardware-validation.json`, `fm1-extended-device.json` | Physical execution/numerical scopes; consult per-rate/parameter results |
| `dynamic-banks-host.json`, `dynamic-banks-device.json` | DynKlank/DynKlang composite expansion and dynamic-rate traces |
| `comb-kernel-equivalence.json`, `comb-kr-kernel-check.json`, `comb-ugen-profile-*.json` | Exact kernel comparisons, control-rate variants and source-specific profiles |
| `miverb-clamp-host.json`, `miverb-clamp-device.json`, `miverb-optimization-analysis.json` | Clamp equivalence, target implementation and measured savings |
| `saw-crossfade-host.json`, `saw-crossfade-device.json`, `saw-optimization-analysis.json` | Cached interpolation-scale equivalence and target profiles |
| `rings-optimization.json`, `rings-target-oracle.json`, `rings-regression-device.json` | Internal Rings paths, allocation recovery and remaining moving-control overruns |
| `gendy-boundary-regression.json` | Closing-segment boundary regression and fix |
| `delay-host-reference.json`, `delay-device-functional.json`, `delay-device-final.json` | Delay interpolation, echo windows, long state and restoration |

[UGEN_SUPPORT.md](../docs/UGEN_SUPPORT.md) is the readable rate/evidence ledger;
[EXTENDED_TESTS.md](../docs/EXTENDED_TESTS.md) explains waveform, statistical and
precision-drift grades. Hardware output is mono; some numerical capture compares
stereo floats before sink conversion. Rendering-cost measurements and numerical
agreement are separate claims.

## History and local-only captures

Earlier build, tone, display, library, memory and interaction reports remain as
historical evidence. `m2-baseline/`, compact-profile configs and numbered-slot
records predate Main/FX, Wi-Fi, source viewing or current optimizations. Failed
experiments are labelled in their reports rather than counted as passing checks.

New bulky raw trace logs, serial screen dumps and browser/network-setup captures
are kept locally and ignored by Git. Summary JSON may refer to such local log
paths; those paths are not promises that every raw capture is published. Selected
safe UI previews/device snapshots remain in the public repository. Earlier
already-published raw logs are retained for history.

Build directories, private session/pairing descriptors, Wi-Fi credentials and
complete device flash backups are excluded. The original backup's provenance is
in `../recovery/backup.json`; no complete flash image containing NVS is shipped.
Source examples, native tests and diagnostic scripts provide the reproducible
inputs; build hashes distinguish their exact measured images.
