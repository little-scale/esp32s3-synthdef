// A fundamental and third partial through a moving two-pole low-pass filter.
SynthDef('filtered', { |freq=330, amp=0.5, gate=1,
    knob1=0.5, knob2=0.4, knob3=0.04040404, knob4=0.13265306|
    var pitch = freq * (2 ** ((knob1 - 0.5) * 2));
    var signal = SinOsc.ar(pitch) + (SinOsc.ar(pitch * 3) * 0.5);
    var cutoff = (pitch * (1 + (knob2 * 12))).min(18000).max(40);
    var env = EnvGen.ar(Env.asr(0.002 + (knob3 * 0.198), 1,
        0.02 + (knob4 * 0.98)), gate, doneAction: 2);
    Out.ar(0, Pan2.ar(LPF.ar(signal, Lag.kr(cutoff, 0.1)) * env * amp * 0.35, 0));
})
