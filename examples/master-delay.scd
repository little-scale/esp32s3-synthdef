// Persistent mono bus effect. One instance follows the summed synth mix.
SynthDef('master-delay', { |time=0.35, feedback=0.35, wet=0.25|
    var input = In.ar(0, 2).sum * 0.5;
    var seconds = Lag.kr(time.clip(0.02, 5.0), 0.05);
    var repeats = Lag.kr(feedback.clip(0.001, 0.8), 0.03);
    var amount = Lag.kr(wet.clip(0, 1), 0.02);
    var decay = (-6.907755278982137 * seconds) / repeats.log;
    // Normalize the injection, keeping old echoes bounded when feedback changes.
    var echo = CombL.ar(input * (1 - repeats), 5.0, seconds, decay);
    var output = (input * (1 - amount)) + (echo * amount);
    Out.ar(0, [output, output]);
})
