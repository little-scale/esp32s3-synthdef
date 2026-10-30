// Compile on the Mac; upload the resulting graph with this source attached.
// The controls share the factory patch's normalized pitch/level/time mapping.
SynthDef('mac-sine', { |freq=330, amp=0.5, gate=1,
    knob1=0.5, knob2=0.5, knob3=0.3939394, knob4=0.2346939|
    var pitch = freq * (2 ** ((knob1 - 0.5) * 2));
    var attack = 0.002 + (knob3 * 0.198);
    var release = 0.02 + (knob4 * 0.98);
    var env = EnvGen.ar(Env.asr(attack, 1, release), gate, doneAction: 2);
    Out.ar(0, Pan2.ar(SinOsc.ar(pitch) * env * amp * knob2, 0));
})
