# Signal storage and expanded graph limits

The full ESP32 profile supports 256 UGen nodes, 512 logical output signals and
2,048 input references per graph. Temporary audio signals share a pool of 192
64-sample buffers. Scalar outputs have independent one-float storage. Delay
budgets, sample rate and block size are unchanged.

These are admission limits, not a guarantee that every admitted graph meets the
audio deadline. Host validation and ESP32 builds do not replace physical timing
checks with Main, FX, display and Wi-Fi active.

## Lifetime planning

The loader determines every logical output's final consumer after validating the
entire graph. It assigns an audio output to the first buffer whose previous
signal has already finished. It never shares an input and output during the
same UGen invocation, and simultaneous outputs of one UGen receive distinct
buffers. Unused outputs still get valid storage while their producer executes.
The renderer retains the original execution order, including side effects and
random-number draws.

Logical output IDs remain stable. UGen state, control smoothing, rate metadata,
initial-value caches, filter history and delay memory keep their existing
ownership. Only temporary sample addresses change. The audio thread performs
neither allocation nor a free-buffer search.

The graph stores an immutable logical-output-to-offset map. Every render uses
the supplied graph's map directly; there is no cached scratch binding that can
become stale when Main and FX or two voices share the same workspace.

Scalar outputs are packed into a separate bank and are not recycled in this
implementation. They cost four bytes each and cannot overlap audio vectors.
Cached initial-rate results are restored by the existing renderer before their
consumers execute; no per-voice state is kept in shared scratch.

The scalar bank supports all 512 logical outputs. The fixed workspace is
51,200 bytes: 192 audio buffers × 64 samples × 4 bytes, plus 512 scalar floats.
It is reserved once and shared serially. A graph may touch only a small portion
of it; the reported working sample bytes are not a smaller heap allocation.
Simply expanding the former dedicated-vector layout to 512 outputs would
reserve 131,072 bytes instead.

The full-profile ESP32 build measures 21,720 bytes per graph and 57,896 bytes per
voice. Four graph objects (active and staging for Main/FX), two voice objects
and shared scratch total 253,872 bytes, before delay arenas and other runtime
services. The primary voice remains in internal RAM; the full-profile graphs,
scratch and FX voice use PSRAM. This increases persistent metadata/state versus
the former limits even though it avoids expanding the audio-vector pool.
The build recorder now counts all four graph allocations; older reports counted
three and understated that particular total.

## Admission and compatibility

The loader rejects a graph whose simultaneous audio requirement exceeds 192,
even when its logical output count is below 512. The new limits preserve the
storage capacity of every previously admitted graph with at most 192 outputs.
Increasing logical limits does not increase delay storage or available CPU.

HELLO advertises `graph_limits` and `signal_reuse`. The host checks the connected
device before transferring an expanded graph. Older full-profile firmware that
does not advertise limits is conservatively treated as 160 nodes, 192 outputs
and 1,024 inputs. A firmware update is needed before those devices can accept
larger graphs. SynthDef file encoding and saved-package encoding are unchanged;
the execution plan is computed on load, not stored in the source file.

The browser/compiler inspection adds `audio_buffers`, `scalar_values` and
`signal_workspace_bytes`. The last field counts used sample storage; it excludes
graph metadata, persistent state and delay arenas. A graph with many logical
outputs may need few live audio buffers, but may still have substantial UGen
state or processing cost.

## Edge cases and evidence

`host/test_signal_reuse.py` generates both the planned implementation and an
independent dedicated-buffer comparison build. Both retain identical DSP
optimisations, capacities and 64-sample blocks; storage is the only difference.
The vendored upstream source remains unchanged.

The suite covers:

- All 1,444 pinned engine fixtures and the project examples.
- Generated chains and deterministic random branching DAGs.
- Duplicate inputs, multiple Out nodes, sibling multi-output signals and
  outputs with no consumers.
- Initial/control/audio rate mixtures and complete scalar banks.
- Two voices sharing scratch, with a different valid physical layout for the
  second graph; repeated prepare, reconstruction and changing controls.
- Poisoned scratch between renders, workspace guard words and an independent
  reference-count-based check of every live range.
- Exact node, logical-output, reference and physical-buffer boundaries,
  including explicit rejection just beyond them.
- Longer delay, reverb, Rings, Gendy, envelope and noise runs.
- Byte-identical samples, lifecycle flags, final voice state and delay memory.
  Process-local pointer addresses are removed from state comparisons.

A [real 64-oscillator Splay example](../examples/buffer-reuse-dense.scd) compiles
to 173 nodes and 236 logical outputs. It exceeds both old graph limits and uses
21 audio buffers: 5,376 bytes of working samples within the reserved pool.
Its [512-block comparison](../evidence/signal-reuse-dense-example.json) matches
the dedicated-buffer engine exactly. This is correctness evidence, not an ESP32
CPU measurement or recommendation to run arbitrary dense graphs without timing
checks.

The separate inventory/fuzz run covers 154 UGen types, 33 unary operators,
40 binary operators and 1.56 million mutated/truncated inputs under undefined
behaviour, bounds and float-cast sanitizers. The host platform's existing
AddressSanitizer startup issue remains outside this validation; the suite uses
the listed working sanitizers and explicit workspace checks.

Run silently from the repository root:

```sh
python3 host/test_signal_reuse.py
python3 host/test_fm1_parity.py --fuzz --prefix signal-reuse
```

Reports are [baseline storage comparison](../evidence/signal-reuse-baseline.json),
[expanded comparison and boundary tests](../evidence/signal-reuse.json),
[type inventory](../evidence/signal-reuse-inventory.json) and
[malformed input fuzzing](../evidence/signal-reuse-fuzz.json). These are host
results; the physical checks below have a separate scope.

## XIAO hardware qualification, 3 November 2026

Build `0916d722b9e292b8f2a8d5d2590c495398a06c6a776872660e9e30656f3a0ac7`
was installed on `esp32-288485ba1e48`, a 240 MHz XIAO ESP32-S3 with 8 MB PSRAM.
The AMOLED was not changed. Wi-Fi was unconfigured; captures inspect the actual
post-volume PCM handed to I²S. No external DAC, electrical I²S measurement or
analogue listening check was performed during those capacity tests. A later
[basic PCM5102A listening test](../evidence/xiao-pcm5102a-listening.json) on the
same build produced clean left/right tones according to the user. A later
[Comb Cloud KR + MiVerb listening test](../evidence/xiao-pcm5102a-cloud.json)
also sounded clean, including its tail; it reached 70.0% maximum sampled average
load with a 126.3% FX-startup peak and no reported DMA overruns or write failures.
This does not establish strict per-block deadline compliance. See
[DAC wiring/testing](HEADLESS.md#temporary-pcm5102a-test-dac).

The [three-minute Main/FX qualification](../evidence/signal-reuse-xiao-after.json)
passed 1,440 changing control events, four concurrent PCM captures, stereo CombN
echo spacing/feedback, a four-second delay consuming the full Main arena,
MiVerb tails after Main stops, Panic and stale-control recovery. All reported
fault-counter deltas were zero. Maximum sampled average audio load was 70.2%,
with an 84.7% sampled peak. Free internal RAM stayed at 141,055 bytes; free PSRAM
stayed at 5,204,128 bytes. The [older-build baseline](../evidence/signal-reuse-xiao-before.json)
reached 67.3% / 79.0% over 60 seconds. Different durations and random excitation
prevent treating those maxima as a controlled speed comparison. This change
expands graph storage capacity; it does not demonstrate a CPU speedup.

The [expanded-capacity checks](../evidence/signal-reuse-xiao-capacity.json) tested
the boundaries separately; they do not imply one graph reached every limit:

| Fixture | Hardware result | Maximum sampled average / peak audio CPU |
| --- | --- | --- |
| 256-node control/audio chain | Rendered correct silence | 41.4% / 42.4% |
| 512 scalar outputs | Rendered correct silence | 9.1% / 10.2% |
| 2,048 input references | Rendered correct silence | 7.2% / 7.8% |
| 16-oscillator Splay | Nonzero, unclipped stereo PCM | 34.8% / 45.1% |
| 32-oscillator Splay | Nonzero, unclipped stereo PCM | 66.0% / 79.5% |
| 48 / 64-oscillator Splay | Loaded inactive; playback skipped by projected CPU budget | Not qualified |
| Eight audio oscillators plus deep control-rate phase modulation | Rendered 193 nodes / 200 outputs, beyond both old limits; 11 audio buffers and 168 scalars | 44.6% / 52.6% |
| Main/FX stereo swap with cached initial-rate amplitude | Expected 660 / 330 Hz, expected level, then silent Panic | Routing/state check |

No new diagnostic faults occurred in that completed suite. Exactly 192 live
audio buffers were admitted without playback, and the
[native loader rejected 193](../evidence/signal-reuse-xiao-native-admission.json)
without changing the active package or saved generations.

An earlier attempt to play the deliberately wide 192-buffer fixture
[exceeded the real-time budget](../evidence/signal-reuse-xiao-wide-budget.json):
maximum combined work reached 2,270 microseconds against a nominal 1,451-microsecond
block period, and 209 DMA-event overruns accumulated. The guard stopped playback
and restored the saved patch; the board remained responsive. This is a recorded
CPU failure, not successful real-time qualification of the memory boundary.

Both original saved Main/FX packages were restored byte-for-byte, with FX bypass
and 100% module volume. A [restart check](../evidence/signal-reuse-xiao-restart.json)
confirmed saved packages, autonomous Main activity and settings survived; fresh
fault counters were zero. Storage generations advance during these tests.
AMOLED display/touch timing, active Wi-Fi timing and instrumented analogue
measurements remain to be qualified on the expanded build.

With Studio already connected to the exact headless device, repeat using:

```sh
python3 host/qualify_signal_reuse.py \
  --device-id esp32-288485ba1e48 \
  --report build/host/signal-reuse-device.json
```

The runner privately backs up both packages, restores them with ownership
checks, and refuses to use a different board. It admits the wide memory fixture
without starting it and stages dense playback using the preceding CPU result.

## AMOLED installation and UI memory correction

The UI memory correction was first installed in headed build
`3e502895350ec52850f53257b8e5afe781a5fbb038ae577d3874104359d257c1`.
Its [build record](../evidence/signal-reuse-amoled-psram-ui-build.json) and
[installation record](../evidence/signal-reuse-amoled-install.json) distinguish it
from the earlier XIAO-qualified build. The DSP profile, graph limits, float32
math and audio storage placement are unchanged. The change uses LVGL's existing
allocation hook to place the fixed 64 KiB UI heap in PSRAM. This resolves the
Wi-Fi internal-memory allocation failure seen on the first expanded AMOLED boot.

A complete private 16 MiB flash backup was taken before updating only the
application on `esp32-2884853ad390`. The initial application write preserved
the boot/settings region and complete saved-storage region exactly, verified
by flash checksums. Before the corrected application was written, saved Main/FX
packages and settings were also backed up through USB; exact package equality,
FX selection and 12% module volume were checked after restart. The saved patches
are MiRings1 and MasterFX. Startup audio counters were clear and Wi-Fi reached
normal connection attempts without a memory error; the saved network was not
found. The user also confirmed that the code screen looks correct and the
controls page opens correctly with the PSRAM UI heap. These are installation,
startup and user interface checks, not a loaded DSP/network timing qualification.
The XIAO firmware was not changed.

The subsequent headed build
`b29f4796f4c67816a97e1beb60f488aa23db76f74212ee0666ba430ce1ba053e`
adds [managed SynthDef touchscreen triggering](UI.md). Its
[build record](../evidence/managed-touch-amoled-build.json),
[host checks](../evidence/managed-touch-host.json) and
[installation record](../evidence/managed-touch-amoled-install.json) are separate.
It retains the expanded DSP profile and PSRAM UI pool. Upload/boot of a managed
definition remains silent; touch can create/trigger its instance, and SC notes
retain their lifecycle and release ownership. Autonomous sound blocks still
start independently of touch, including after a rapid same-block tap.

The image was written/verified on the AMOLED and booted with the temporary
MiRings1 definition inactive. The initial bounded windows recorded no physical
press, and an automated local-UI exercise was interrupted by a host-script format
error and USB disconnection. After reconnection, the
[physical touch check passed](../evidence/managed-touch-amoled-physical.json):
four rising gate edges, each followed by release, were observed; the user heard
a MiRings1 strike on each press. Audio fault counters did not increase. This
confirms the real code-area input path as well as the host regression checks.
The separate automated UI exercise was not completed and is not claimed as a pass.

The user's [standard automatic test](COMMISSIONING.md) was restored and verified,
with master FX bypass and their selected 51% output volume. The XIAO remains on
its previously tested firmware.

Headed build `33f68d0b61fb7cfd7b2dd7254e13db27765608ac1b566fd70e0b329254039e9f`
retains those changes and makes unsaved startup volume and the initial slider
20%. Its [build record](../evidence/default20-amoled-build.json),
[volume regression](../evidence/default20-volume-host.json) and
[fresh-module installation](../evidence/amoled-8d5054-install.json) are separate
from the earlier boards' results. Existing saved volume levels are retained.
See the [new-module check](COMMISSIONING.md) for the clean, user-confirmed standard
test on AMOLED-8d5054 at 20%, with separate master FX bypassed.
