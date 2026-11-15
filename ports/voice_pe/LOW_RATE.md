# 16-to-48 kHz converter alternative — unfinished

**15 November update:** [the native 16 kHz pair](NATIVE_16K.md) now builds and
passes computer integration checks. It changes XMOS clocks and codec/ESP
configuration together. The matched pair is now installed and passes digital hardware/SC checks;
cold-power, physical IO and user listening checks pass. The converter design below is a separate,
unfinished alternative and is not selected by the native build.

This converter proposal targets the stock **48 kHz** XMOS link and has not
been installed. The now-tested native16 pair is a separate implementation
that changes XMOS clocks; Waveshare and XIAO retain their existing 44.1 kHz rate.

The current raw engine already passes a computer-only 440 Hz gated-sine check
at **16 kHz**, including the expected crossing count and envelope progression
(`python3 host/test_voice_pe_low_rate.py`). This does not enable a 16 kHz production
instrument, validate reverbs/models at that rate, or provide an output converter.

## Proposed converter implementation

Render Main **and** FX at 16,000 Hz, then apply a fixed, filtered 3:1 interpolator
to the final stereo stream for the existing 48,000 Hz physical I²S link. Keep the
XMOS master clocks, codec divider configuration, USB/SC transport and stored
source/graph format. SynthDef binary data does not encode a mandatory sample
rate, so most patches can be reused, subject to a fresh 16 kHz admission check.
A sample-rate mode belongs to the whole device pipeline, not to one graph.

The converter should be a small bounded polyphase FIR with its coefficients
stored in flash, no allocation or locks during rendering, and an explicit reset
at a faded/drained transition. Repeating samples or using an unfiltered linear
interpolator would introduce stronger spectral images. There is no reason to
modify or reflash XMOS just to offer a lower-rate synthesis mode.

## Costs and limits

- A second of audio requires 16,000 synth samples instead of 48,000. This is
  **66.7% fewer samples**, not a claim of 66.7% lower total device CPU usage.
  Block scheduling, state resets, USB/Wi-Fi, GPIO, LED updates, and conversion
  still cost time. The DAC still receives 48,000 frames per second.
- With the existing 64-frame engine block, the control period becomes 4 ms
  instead of 1.333 ms. Note timing and kr triggers have correspondingly coarser
  quantisation. Fades and envelopes must continue to use the DSP rate.
- Internal Nyquist is 8 kHz. The interpolation filter needs a transition band,
  so the clean passband will end below that. Aliasing already produced inside
  a nonlinear UGen cannot be removed by the output converter.
- Duration-based delay requirements become smaller, but power-of-two ring
  allocation means savings occur in steps. Fixed-capacity reverb/model state
  is not automatically reduced. Graph node, input and signal-workspace limits
  do not increase simply by selecting 16 kHz.
- Some existing model/reverb kernels have fixed tuning or 48 kHz constants.
  MiVerb/FreeVerb and the Rings models need explicit rate-behaviour tests before
  claiming that pitch, modulation and decay times retain their intended meaning.
  An integer-rate output converter cannot correct those internal assumptions.

## Integration work before enabling it

1. Distinguish DSP rate and physical output rate in firmware, HELLO, capture
   metadata, Studio resources and build provenance. Generalise admission to
   16/44.1/48 kHz and select it separately for each recipient in a mixed fleet.
2. Give the Voice PE a separate optional build configuration initially; retain
   48 kHz as the default. A later runtime setting needs a faded park, new memory
   admission for both graphs, converter reset and deterministic restart.
3. Extend the instrument/master wrappers, timebase, CPU deadline accounting,
   standalone pattern scheduler and control-bus cadence. Do not label a 16 kHz
   PCM capture as a capture of the resampled 48 kHz wire stream.
4. Include the converter's actual CPU time in reported busy/peak measurements.
   Current conversion occurs around the DMA write boundary; counting only the
   graph render would make the apparent CPU saving misleading.
5. Test DC/impulse response, passband/stopband, channel isolation, signed-16
   extremes, chunk boundaries, reset, invalid arguments and bounded capacities.
   Compare equal patches/seeds on the board at both rates, including delay,
   envelopes, random triggers, sustained DSP load and stop/reload transitions.

This is a concrete follow-up design, not a supported firmware option or a
completed quality/performance qualification. Grove work also remains deferred
until an actual sensor is available.
