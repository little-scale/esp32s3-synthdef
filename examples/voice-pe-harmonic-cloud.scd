// Studio: compile this as a Sound block for a Voice PE.
// SC IDE: replace .play with .playESP32("YOUR_VOICE_PE_ID_OR_NAME").
// The three anchors are MIDI notes. Random voice settings are chosen at compile
// time; BrownNoise pitch changes continue on the module. Separate FX can be
// bypassed because this block includes its own reverb and echo.
(
{
    arg amp = 0.2;
    var size = 12, lfo_rate = 0.01, randomness = 0.01;
    var anchors = [72, 67, 88], changeRates = [1, 0.25, 0.125];
    var majorFloor = [0, 0, 2, 2, 4, 5, 5, 7, 7, 9, 9, 11];
    var offsets, notes, roots, lfo, blue, brightness, frequencies;
    var sig, pulse;

    // Symmetric, bounded pitch offsets; each line changes at its own rate.
    offsets = Latch.kr(BrownNoise.kr([3, 4, 6]), Impulse.kr(changeRates)).round;
    notes = anchors + offsets;
    notes = Select.kr(notes % 12, majorFloor) + ((notes / 12).floor * 12);
    roots = Lag.kr((notes - 12).midicps, 0.25);

    // Independent, full-depth slow sweeps; positive frequencies throughout.
    lfo = LFPar.kr(
        lfo_rate * ({ rrand(1 - randomness, 1 + randomness) } ! size),
        { 4.0.rand } ! size
    );
    blue = LFPar.kr(lfo_rate).range(0.1, 0.7);
    brightness = lfo.range(0, 1);
    Out.kr(3, brightness.collect { |level| [level, 0, blue] }.flat);

    frequencies = Array.fill(size, { |i|
        roots[i % anchors.size] * rrand(1 - randomness, 1 + randomness)
        + (lfo[i] * 0.25)
    });
    sig = Saw.ar(frequencies) * lfo.range(0.45, 0.95);
    sig = RLPF.ar(sig, lfo.range(80, 5500), { rrand(0.2, 0.8) } ! size);

    // Shape the source before reverb so effect tails remain uninterrupted.
    pulse = Decay2.kr(Impulse.kr(2), 0.01, 1, 0.8) + 0.2;
    sig = Splay.ar(sig) * pulse;
    sig = MiVerb.ar(sig, 0.92, 0.55, 0.5, 0.1);
    sig = sig + (CombN.ar(sig, 0.5, 0.375, 5) * 0.25);

    // Remove DC and constrain the signal before its final output scale.
    LeakDC.ar(sig).softclip * amp.clip(0, 1);
}.play
)
