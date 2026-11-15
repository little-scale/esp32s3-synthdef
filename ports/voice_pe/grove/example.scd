// Proposed Grove bus contract; no Grove firmware support is implemented yet.
// Defines a graph only: does not add, deploy or play it.
SynthDef(\GroveLight, { |groveBus = 16, groveValidBus = 24|
    var light = In.kr(groveBus, 1);
    var valid = In.kr(groveValidBus, 1);
    var freq = Lag.kr(light, 0.1).linlin(0, 1, 110, 880);
    Out.ar(0, (SinOsc.ar(freq) * Lag.kr(valid, 0.02) * 0.03) ! 2);
});
