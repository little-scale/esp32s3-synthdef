# Recorded evidence

Reports cover development from 30 October through 2 November 2026. They retain
the source/build IDs and test scope from their own runs. An old timing or board
measurement does not automatically qualify a newer image or another graph.
[STATUS.md](../STATUS.md) identifies the latest installed image and open limits.

The publication checks are summarized in `publication-checks.json`, including
a fresh build (`publication-build.json`), clean-checkout tests, README syntax and
relative documentation links.

## Current workflow and compact controls

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
