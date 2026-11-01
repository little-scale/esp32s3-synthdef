// FM1-profile performance fixtures, exported by host/export-rings.scd.
// Each fixed model has a live pitch, structure, brightness and damping control.
// These are temporary diagnostic voices until their timing is qualified.
[
    MiRings1, MiRings2, MiRings3, MiRings4, MiRings5, MiRings6
].collect { |model, index|
    SynthDef(("rings-" ++ (index + 1)).asSymbol, {
        |freq=330, amp=0.5, gate=1,
        knob1=0.5, knob2=0.4, knob3=0.6, knob4=0.7|
        var pitch = freq * (2 ** ((knob1 - 0.5) * 2));
        // The fixed-model wrapper includes a +12-semitone tonic.
        var midi = Lag.kr(pitch.cpsmidi - 12, 0.03);
        var structure = Lag.kr(knob2, 0.03);
        var brightness = Lag.kr(knob3, 0.03);
        var damping = Lag.kr(knob4, 0.03);
        var signal, envelope;
        RandSeed.ir(1, 12345);
        signal = model.ar(0, gate, midi, structure, brightness, damping,
            0.25, 1, 0, 0);
        envelope = EnvGen.ar(Env.asr(0.005, 1, 0.15), gate, doneAction: 2);
        Out.ar(0, signal * envelope * amp * 0.18);
    })
}
