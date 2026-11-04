// Planned hardware qualification FX. Compile/upload as Master FX, not Main.
// No host sound is started by this expression.
SynthDef(\qaMasterReverb, {
    arg time = 0.85, wet = 1, damping = 0.5;
    Out.ar(0, MiVerb.ar(In.ar(0, 2), time, wet, damping, 0.05));
});
