// Four normalized controls for the first touchscreen instrument.
SynthDef('touch-sine', { |freq=440, amp=0.5, gate=1,
    knob1=0.5, knob2=0.5, knob3=0.04040404, knob4=0.13265306|
    var pitch = freq * (2 ** ((knob1 - 0.5) * 2));
    var attack = 0.002 + (knob3 * 0.198);
    var release = 0.02 + (knob4 * 0.98);
    var env = EnvGen.ar(Env.asr(attack, 1, release), gate, doneAction: 2);
    Out.ar(0, Pan2.ar(SinOsc.ar(pitch) * env * amp * knob2, 0));
})
