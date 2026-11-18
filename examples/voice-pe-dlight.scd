// Voice PE + M5Stack DLight: 42 = normalised (0..1000 lux), 43 = lux.
// Studio: compile/upload this Sound block. In SC, replace .play below with
// .playESP32("VoicePE-0697d4"). This example uses both buses and needs no touch.
(
{
    var light = Lag.kr(In.kr(42), 0.2);
    var lux = In.kr(43);
    var hz = Lag.kr(lux.clip(0, 1000).linexp(0, 1000, 110, 880), 0.2);

    Out.kr(39, [0, light * 0.2, light * 0.1]);
    SinOsc.ar(hz, 0, 0.1) ! 2
}.play
)
