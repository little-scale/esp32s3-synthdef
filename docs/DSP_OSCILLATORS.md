# Saw and Impulse candidates — 15 November 2026

These are optional optimisations of the existing float32 algorithms, not new
oscillator models. Both are **disabled by default**. The initial work was
computer-only; the subsequently authorised Voice PE session is recorded below.
The measurements below used Voice PE at 48 kHz. A later matched
[native-16k build](../ports/voice_pe/NATIVE_16K.md) explicitly enables both
candidates and has separate computer, hardware and listening evidence. Standard
Voice PE, AMOLED and XIAO builds retain their existing rates and candidate-off
defaults.

## Implementation

`host/dsp_oscillators.py` transforms the generated engine; vendored FM1 source
is unchanged. The independent generator switches are `candidate_saw=True` and
`candidate_impulse=True`, or `--candidate-saw` / `--candidate-impulse`.
Experimental firmware builds accept `SYNTHDEF_DSP_CANDIDATES=saw,impulse`.
This does not enable them in the standard 48 kHz Voice PE or 44.1 kHz
AMOLED/XIAO images; the native-16k wrapper explicitly selects them.

Saw caches its harmonic count and scale when frequency is unchanged, and its
exact integer phase step by effective frequency. During a descending harmonic
transition the old, higher frequency is still used for that block; the next
block must refresh the step even though the requested frequency is unchanged.
Steady and harmonic-crossfade loops are separate, with phase and integrator
state held locally until the loop ends. The same sine/cosecant tables,
singularity handling, compensated setup arithmetic and integration remain.
Pulse is unchanged.

Only the otherwise-unused Saw `b1` and `total` words become a cache. There is
no additional voice, scratch, table or delay allocation. Restarting a voice
clears the cache. Sample rate is fixed for a voice's lifetime, as in the
existing API; a new rate requires `fm_start`.

Impulse binds its input once and chooses constant-, control- or audio-frequency
loops outside the sample loop. Control interpolation retains operation order
and uses an exact binary reciprocal for 64 frames, or one for constructor and
control passes. Compensated phase, previous-increment wrapping, negative/zero
frequency behaviour and constructor resets remain unchanged. The actual input
rate must be retained: the general binding helper can classify a zero control
as scalar, which would incorrectly skip a transition to zero in Impulse.
The oracle test caught this during development; the final implementation
explicitly restores the source rate.

## Computer validation

Run from the repository root:

```sh
python3 host/test_dsp_oscillators.py --with-supercollider
python3 -m unittest discover -s host -p 'test_oscillator_selection.py'
python3 host/prepare.py --check
python3 host/document_optimizations.py --check
```

The optional SuperCollider flag compiles the user's complete twelve-voice
Dust/Decay/LED/Splay patches silently. No server is booted and no upload occurs.
Without that flag the test uses binary fixtures and needs no SC installation.

The primary 48 cases cover 8,000, 44,100, 48,000 and 192,000 Hz, with 2,048
blocks and three starts per case/rate. Audio/control oscillator rates, literal,
initial-random, changing-control and permitted audio-frequency inputs are
covered. Tests include held frequencies, adjacent floats at harmonic
boundaries, descending transitions, very low Saw frequencies, invalid Saw
inputs, signed zero, negative and multi-wrap Impulse increments, six initial
phase cases, implicit/explicit/idempotent preparation and live signal reuse.

Each configuration compares **150,994,944 stereo sample values**, full scratch
and voice state byte for byte, excluding only Saw's two documented cache words.
RNG and faults are included. Saw-only, Impulse-only and both with broad input
binding also pass the same cases. Undefined-behaviour, bounds and float-to-int
sanitizers are enabled. The broader corpus passes **1,454 graphs** at 48 kHz,
including 933 matching fault blocks. These tests establish equivalence to the
existing engine, not additional SuperCollider feature compatibility.

Desktop timings are medians of three paired runs at 48 kHz / 64 frames, each
with a 512-block warm-up and 131,072 measured blocks per version. End-state,
scratch and final output are compared after each timing pair.

| Workload | Change in processing time |
| --- | --- |
| Twelve fixed-pitch Saw oscillators | 21.69% less |
| Twelve fixed-pitch Impulse oscillators | 5.95% less |
| User's complete twelve-Saw LED/Splay patch | 14.04% less |
| User's complete twelve-SinOsc LED/Splay patch | 0.90% more |

The sine routine is unchanged. Its small measured regression is retained in
the results rather than claimed as a gain. Desktop timings are **not ESP32 CPU
predictions** and do not establish that the reported 118% hardware load will
fall below the deadline.

The ESP32-S3 offline compiler also accepts both candidates. Its renderer object
is 1,635 bytes larger in this comparison, with unchanged data/BSS. No software
double-arithmetic calls occur in the inspected oscillator functions. Division
relocation counts are static code observations, not dynamic cycle counts.

An isolated Voice PE candidate firmware build also passes the normal build audit:
48 kHz, 1,254,128-byte application, graph/voice/scratch sizes unchanged at
21,720 / 58,064 / 51,200 bytes, pinned sine-table bytes and precise math flags
verified. It has not been installed. See the
[candidate build audit](../evidence/dsp-oscillators-voice-pe-build-20261115.json).

Detailed evidence: [host comparisons](../evidence/dsp-oscillators-host-20261115.json).

## Hardware qualification

### Voice PE fixed-seed follow-up

The user authorised hardware testing on VoicePE-0697d4 (ESP MAC
`10:20:ba:06:97:d4`). Main and FX packages, instance controls/activity, FX
selection and the user's 16% volume were backed up privately. Measurement
images were installed with the guarded app-only updater; output was muted
and the persisted mute retained over test reboots. Bootloader, OTA metadata,
PHY, NVS and app1/storage hashes were checked around each application write.
XMOS was not written.

Baseline and combined candidate used the same source tree, 48 kHz / 64 frames,
240 MHz and qualified kernel settings, with diagnostic instrumentation in both
images. The optional oscillator flags were the only DSP selection difference.
Ten exact compiled graphs ran three times per image with seed 12345, 128 warm-up
blocks and 1,024 measured blocks. Normal and instrumented renderer passes agree
on audio, voice/scratch/arena digests within each image; warm and measured audio
SHA256 hashes and final RNG state also agree between images and repeated trials.

| Whole graph | Baseline µs/block | Candidate µs/block | Less DSP time |
| --- | ---: | ---: | ---: |
| User's twelve-Saw LED/Splay block | 1,389.66 | 1,268.26 | 8.74% |
| Equivalent twelve-SinOsc block | 555.17 | 554.63 | 0.10% |
| Twelve held Saw oscillators | 774.44 | 644.52 | 16.78% |
| Twelve changing Saw oscillators | 1,208.18 | 1,113.51 | 7.84% |
| Twelve literal-frequency Impulse.ar | 513.19 | 368.67 | 28.16% |
| Twelve initial-random-frequency Impulse.ar | 588.10 | 372.36 | 36.68% |
| Twelve control-frequency Impulse.ar | 1,064.12 | 474.41 | 55.42% |
| Twelve audio-frequency Impulse.ar | 933.86 | 720.47 | 22.85% |
| Twelve Impulse.kr | 132.77 | 124.21 | 6.45% |
| Pulse regression graph | 1,661.13 | 1,626.45 | 2.09% |

These are median whole-graph timings, not isolated UGen cycle reductions. Pulse
is unchanged: its small observed shift is retained as a layout/timing comparison,
not a claimed Pulse optimisation. A 48 kHz rate check was added to Studio's
fixed-seed collector; the existing 44.1 kHz validation remains covered.

Live windows of the restored twelve-Saw patch, outside the parked diagnostic,
measure approximately **117.8% baseline vs 108.5% diagnostic candidate**; the
final lean candidate averages about **109.2%** in five further windows. This includes
streaming control/PCM work beyond the raw graph timing, and still exceeds the
1,333.33 µs audio deadline. Historical peak and DMA backlog counters include
intentional diagnostic pauses and are not treated as fresh real-time failures.

The normal Studio image defaults remain unchanged. The exact connected Voice PE
is returned to a lean image with both candidates enabled for listening; its
original Main/FX packages and volume are restored. The user confirmed this
twelve-Saw block sounds clean at 16% volume with FX bypassed. This listening
result applies to the restored user patch; separate listening qualification
of every Impulse fixture is not claimed. XIAO/AMOLED target timing and longer
stress tests remain separate qualification.

Evidence: [baseline](../evidence/dsp-oscillators-voice-pe-baseline-20261115.json),
[candidate and numerical comparison](../evidence/dsp-oscillators-voice-pe-candidate-20261115.json),
[hardware summary and restoration](../evidence/dsp-oscillators-voice-pe-summary-20261115.json),
[exact compiled test plan](../evidence/dsp-oscillators-voice-pe-plan-20261115.json),
[baseline diagnostic build](../evidence/dsp-oscillators-voice-pe-baseline-qa-build-20261115.json),
[candidate diagnostic build](../evidence/dsp-oscillators-voice-pe-candidate-qa-build-20261115.json).

### Additional board qualification

Use a baseline and candidate build of the same board application, same rate,
64-frame blocks, fixed random seed, Main/FX state and volume. Time Saw-only,
Impulse-only and combined candidates separately. Start with the user's two
12-voice patches, then test held/changing frequencies, descending harmonic
boundaries and positive/negative/zero Impulse transitions. Compare DSP time,
peak/deadline misses, faults, clipping and captured PCM, then listen briefly at
the user's chosen volume. Restore the original patch and volume, and return to
an audited non-diagnostic application after diagnostic runs.

Table placement and a different PolyBLEP/wavetable model remain separate
experiments. Neither was introduced here.
