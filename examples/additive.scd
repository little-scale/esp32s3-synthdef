// Three harmonic partials; HARMONICS blends in the upper two partials.
SynthDef('additive', { |freq=330, amp=0.5, gate=1,
    knob1=0.5, knob2=0.5, knob3=0.04040404, knob4=0.13265306|
    var pitch = freq * (2 ** ((knob1 - 0.5) * 2));
    var upper = (SinOsc.ar(pitch * 2) * 0.5) + (SinOsc.ar(pitch * 3) * 0.25);
    var signal = SinOsc.ar(pitch) + (upper * knob2);
    var env = EnvGen.ar(Env.asr(0.002 + (knob3 * 0.198), 1,
        0.02 + (knob4 * 0.98)), gate, doneAction: 2);
    Out.ar(0, Pan2.ar(signal * env * amp * 0.3, 0));
})
