# Exact DSP block kernels and upload transitions

The AMOLED and headless XIAO builds use the same generated DSP implementation.
`host/engine_profile.py` applies audited transformations to the pinned engine;
the vendored upstream files remain unchanged. These changes retain float32
arithmetic, 64-frame blocks, UGen execution order and the SynthDef file format.

## Filters

`Resonz`, `Ringz`, `LPF`, `HPF`, `RLPF`, `RHPF`, `BPF` and `BRF` have dedicated
block loops. Inputs bind once, and filter type dispatch occurs outside the
sample loop. The existing coefficient cache still updates when frequency or
the second parameter changes.

The old renderer recalculated the same interpolated coefficients for each of
three adjacent samples. The new loop calculates that group once, then applies
the unchanged recurrence to each sample in order. The last sample of a 64-frame
block is its own group. The division by 21 is retained: replacing it with a
reciprocal would change rounding. One-sample constructor/control calculations
retain their original rules, including the Resonz constructor's zero output
and Ringz's offset-zero sampling of audio-rate coefficient inputs.

## Lag and unary operators

`Lag` and `LagUD` cache independently unchanged up/down time coefficients.
`LeakDC` uses the same bound-input block path. Recurrences and interpolation
order remain unchanged; division by the power-of-two block size is an exact
reciprocal multiplication.

Pure unary operators evaluate a scalar input once per block and retain a
bitwise input/result cache across blocks. Signed zero is distinguished. Audio
inputs still evaluate each sample; common unary selectors dispatch once per
block. No lookup approximation replaces exponential, pitch, log or trig math.

Caches reuse fields otherwise unused by those node types. Graph, voice and
scratch allocations do not grow. Reconstruction clears the caches with the
voice. They belong to the voice, not recycled scratch or a global singleton.

## MiVerb packed memory

**Experimental and disabled by default.** It matched samples/state on the host
but regressed on the XIAO: the measured MiVerb node cost increased from about
462 to 687 µs per block. The full patch rose from 1,181 to 1,405 µs. Production
retains the existing byte-wise access and ordered clamp optimization.

In the opt-in comparison variant, packed Q1.15 delay data is unchanged. Little-endian targets transfer a
16-bit word through `memcpy` rather than two byte operations. Float arena slices
are aligned and every byte offset is even. The alignment hint enables native
halfword instructions without violating C's aliasing rules. Other byte orders
retain explicit byte assembly. Quantisation, saturation, freeze, random state
and float processing remain unchanged.

The generator has independent comparison switches for filters, Lag, unary and
packed MiVerb. Production defaults must be justified by both differential
checks and ESP32 measurements; desktop timing alone is not target evidence.

## Main replacement fade

All maintenance transitions now use a separate 5 ms stereo output gate after
master FX and before user volume/PCM conversion. At 44.1 kHz the ramp contains
221 frames with exact endpoints. It has no sample-processing cost at steady
unity. The old Main remains rendered throughout fade-out, then output stays
zero through twelve 64-frame blocks to drain six 128-frame DMA buffers before
the audio owner acknowledges parking. Loading/reconstruction occurs while
parked. The next actual Main render or audible FX output starts fade-in.

The gate also suppresses preserved FX during the drain. Previously the final
PCM was faded for two blocks, but a preserved master could then reappear at full
level before DMA stopped. Existing maintenance rules still decide whether FX
state is retained or reset; this change does not add a second Main instance or
a crossfade. Loading/storage can produce a longer silent gap between ramps.

User volume is unchanged, and definition-only uploads remain uninstantiated.
Panic still stops Main/FX directly; it does not wait for a transition ramp.
Normal per-note envelopes and the existing short instance-onset fade are retained.
The gate operates on float stereo before either the AMOLED mono sink or XIAO
stereo sink, so both board targets receive the same transition behavior.

## Validation

`host/test_dsp_kernels.py` compares the optimized implementation with the original
general loops and byte-wise MiVerb memory: 100 graphs, four sample rates and
26,214,400 bit-identical samples, including changing coefficients, independent
lag times, legal scalar excitation of audio kernels, all supported unary selectors, signed zeros, constructors, repeated
prepare and voice reconstruction. Mathematical fault cases must match too.
Whole recursive voice state, RNG and delay memory are compared; only the
documented new, otherwise-unused cache fields are normalized.

The wider differential run covers 1,500 previously accepted graphs at 44.1 kHz
for 32 blocks each, including 6,144,000 additional samples. The MiVerb-specific
test covers 8,388,608 samples and 400,000 private quantiser/readback probes, with
complete voice/arena identity. Undefined-behavior, bounds and float-to-integer
sanitizers are enabled. See `evidence/dsp-kernels-host.json`,
`dsp-kernels-inventory.json` and `miverb-packed-host.json`.

`host/test_audio_transition.py` tests endpoints, monotonic ramps, stereo pairing,
interrupted fades, zero hold and bit-identical steady unity at four rates.
`host/qualify_transition.py` captures actual post-volume PCM while Main is
replaced, checks preserved-FX restarts and definition-only silence, and restores
the user's Main/FX packages, instance state, bypass and volume. This verifies
digital behavior; analogue DAC/codec clicks still require listening.

Physical timing uses `host/qualify_dsp_kernels.py`: three runs of the same graph
per fixture, 128 warm-up blocks and 1,024 timed blocks per run. The diagnostic
compares instrumented and normal renderer hashes/state, while the normal render
time excludes per-node probes. Tests are muted, run on the audio owner, and
restore saved packages/settings. These are rendering-cost measurements, not
whole-chip or worst-case real-time guarantees under arbitrary RF/display load.

The final XIAO build `cd9fc38336ae` measured:

| Fixture | Before, µs/block | After, µs/block | Less time |
| --- | ---: | ---: | ---: |
| Eight filter types | 672.88 | 277.64 | 58.7% |
| Lag/LagUD bank | 1,311.85 | 527.27 | 59.8% |
| Repeated unchanged control-rate pitch math | 364.63 | 132.99 | 63.5% |
| Eight-saw/Resonz/MiVerb block | 1,287.98 | 1,150.18 | 10.7% |

The fixtures' graph hashes match between runs. Rendering times are cycle counts
converted at the configured 240 MHz. Stochastic/oscillator state may differ
between installations. `evidence/dsp-kernels-summary.json` gives the comparison;
the before/final/packed records retain all three timing trials and per-node
results. The packed experiment is excluded from the final default.

On the final firmware, actual Main replacement capture measured a 220-frame
fall, 1,898-frame zero interval and 215-frame rise, with at most five PCM counts
between adjacent samples at the test level. Preserved-FX restart held zero for
805 frames, with a maximum seven-count step. Definition-only upload remained
inactive and silent. No audio diagnostic counters increased. These low-level
test signals and output settings are restored afterwards; they do not measure
the analogue DAC transient. An interrupted USB timing attempt required a
physical reconnect; the original package was recovered and the final run
repeated successfully. See `dsp-kernels-xiao-final-interrupted.json` and
`dsp-kernels-usb-recovery.json` for that scope.

After the final firmware was installed, the user confirmed that switching sounds
cleaner. This is listening confirmation of improvement, not a measured analogue
noise floor or a claim that every DAC/codec transition is artifact-free.
