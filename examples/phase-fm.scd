// Phase modulation with a 2:1 modulator; all four controls are normalized.
SynthDef('phase-fm', { |freq=330, amp=0.5, gate=1,
    knob1=0.5, knob2=0.35, knob3=0.04040404, knob4=0.13265306|
    var pitch = freq * (2 ** ((knob1 - 0.5) * 2));
    var modulation = SinOsc.ar(pitch * 2) * (knob2 * 4);
    var env = EnvGen.ar(Env.asr(0.002 + (knob3 * 0.198), 1,
        0.02 + (knob4 * 0.98)), gate, doneAction: 2);
    Out.ar(0, Pan2.ar(SinOsc.ar(pitch, modulation) * env * amp * 0.4, 0));
})
