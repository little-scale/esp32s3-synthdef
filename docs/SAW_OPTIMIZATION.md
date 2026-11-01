# Saw optimisation analysis — 1 November 2026

The crossfade-fraction optimisation is now installed and measured on the board.
The other candidates remain unimplemented. The vendored engine is unchanged.

## Current cost

After the MiVerb clamp change, the two Saws in the saved Saw / Resonz / MiVerb
patch take about 200 microseconds per 64-frame block, approximately 23% of the
instrumented node time. They use the SuperCollider band-limited impulse
recurrence, with interpolated sine/cosecant tables, singularity handling and
harmonic-count crossfades. This is not the inexpensive LFSaw ramp algorithm.

## Best first candidate

The shared Saw/Pulse loop evaluates `t = (float)j / count`. The renderer calls it
with 64 samples for normal audio and one sample for construction or lower-rate
evaluation. Replacing that expression with `j * (1.0f / FM_BLOCK)` is exact for
the audio blocks; for a one-sample call, j is zero in both expressions.

The generated Xtensa code currently contains software division in the sample
loop. Compiling the isolated candidate with the actual ESP32 flags reduces the
shared function's static division-call sites from ten to eight (compiler paths
can duplicate a source expression). Other divisions and the singularity fallback
remain intact. This count is not a measured cycle saving.

The candidate passes **20,971,520 bit-identical output comparisons**, including
complete voice/random state, under undefined/bounds/float-cast sanitizers:

- Saw and Pulse with changing controls;
- Saw and Pulse with control-rate frequency/width modulation;
- Blip as a shared-helper regression case;
- 8 / 44.1 / 48 / 192 kHz;
- 8,192 blocks per case, with frequencies at and immediately around harmonic
  boundaries, including near Nyquist and the admitted maximum harmonic count;
- Pulse widths at zero, one, one-half and near the extremes.

The original isolated prototype and assembly: `build/host/saw-analysis/`. Evidence:
`evidence/saw-optimization-analysis.json`.

## Other candidates

1. Resolve the Saw/Pulse and harmonic-crossfade modes outside the sample loop,
   and measure selective inlining of `blip_ratio`. This may reduce helper-call
   and branch overhead, but code-size/cache tradeoffs need target measurement.
2. Cache harmonic count, scale and phase increment for unchanged frequency.
   The current Lag/LFNoise patch changes frequency almost every block, so this
   mainly benefits steady-pitch patches. The cached increment must track the
   *effective* frequency: during a harmonic-count change, the implementation
   uses the maximum of old/new frequencies. Reusing that step on the following
   descending-frequency block would be incorrect.
3. Investigate lookup-table locality after those smaller changes. The two
   8,193-float tables occupy about 64 KiB together, exceeding the current free
   internal heap. Moving them wholesale into internal RAM is unsuitable for
   the current Wi-Fi image.

Preserve the existing tables, near-zero-denominator treatment, phase rounding
correction, integrator coefficient and crossfade trajectory initially. Replacing
Saw with LFSaw or a different oscillator algorithm changes its aliasing and sound.

## Implemented result

`host/engine_profile.py` applies the exact reciprocal substitution in the generated
target copy. The permanent regression is `python3 host/test_saw.py`; its reference
uses the pinned Saw/Pulse routine with every other engine adaptation held fixed.

Three muted audio-owner profiles per image used the same saved 24-UGen graph,
240 MHz clock, 44.1 kHz / 64-frame blocks, Wi-Fi and display enabled:

| Median metric | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Two Saw nodes | 197.81 µs | 169.28 µs | 14.42% |
| Normal whole-graph DSP | 862.55 µs | 833.97 µs | 3.31% |

Per-node probes have overhead; the normal renderer timing measures the overall
change independently. Normal playback averaged 60.66% audio budget versus the
previous image's 62.24% observation, with no additional DMA events, synthesis
faults or failed writes during 20.03 measured seconds after settling. Individual
recent peaks reached 100.1%; this is not a universal worst-case deadline guarantee.

Fixed-seed board traces cover 8,192 blocks (11.89 seconds) per image. All 5,120
captured float samples match bit-for-bit; full-duration peak/RMS match and no
faults, nonfinite samples or canary failures were reported. Host regression:
20,971,520 bit-identical outputs and full voice state under undefined/bounds/
float-cast sanitizers; 31 Studio tests pass.

Evidence: `saw-crossfade-host.json`, `saw-crossfade-device.json`,
`saw-crossfade-build.json` and `saw-crossfade-steady.json` under `evidence/`.
