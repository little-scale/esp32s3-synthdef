// MiRings1: one fixed-model modal resonator, with its internal exciter.
// Requires the project's upstream/fm1-synthdef/synthdef-engine/sc/Classes
// directory in SC's included class-library paths. Save that configuration,
// then choose Language > Recompile Class Library once before evaluating.
// This class is for compilation to the ESP32; it is not a desktop DSP plugin.
//
// Evaluating this file returns the SynthDef. It does not upload or play it.
// Send with .sendESP32(target), then use an esp32Note pattern to strike it.
// gate starts at zero: each positive edge excites the resonator once.
// Note-off rearms the trigger; the resonator's natural tail continues.
// structure, bright, damp and pos accept 0..1. Larger damp gives longer tails.
(
SynthDef(\miRings1, {
    arg freq = 220, amp = 0.35, gate = 0,
        structure = 0.25, bright = 0.55, damp = 0.65, pos = 0.25;
    var sound;

    sound = MiRings1.ar(
        in: 0,
        trig: gate,
        // The fixed-model wrapper adds a 12-semitone tonic internally.
        pit: freq.cpsmidi - 12,
        struct: structure,
        bright: bright,
        damp: damp,
        pos: pos,
        intern_exciter: 1
    );

    Out.ar(0, sound * amp);
})
)
