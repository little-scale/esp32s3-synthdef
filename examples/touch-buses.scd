// Touch control bank, relative to hwBus:
// 0 = X: left to right, normalized 0..1.
// 1 = Y: bottom to top, normalized 0..1.
// 2 = gate: 1 while held, 0 on release.
// Use the right/bottom strips to scroll.

SynthDef(\TouchBuses, { |hwBus = 0|
    var touch = In.kr(hwBus, 3);

    // Horizontal position sets pitch.
    var frequency = Lag.kr(touch[0], 0.015)
        .linexp(0, 1, 110, 880);

    // Vertical position sets level.
    var level = Lag.kr(touch[1], 0.015);

    // Finger-up releases the envelope.
    var envelope = EnvGen.kr(
        Env.asr(0.01, 1, 0.12),
        touch[2]
    );

    var signal = SinOsc.ar(frequency)
        * level
        * envelope
        * 0.25;

    Out.ar(0, Pan2.ar(signal));
});
