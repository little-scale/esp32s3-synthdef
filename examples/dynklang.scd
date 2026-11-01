(
{
    var frequencies = [110, 220, 330, 440, 550];
    var levels = [0.06, 0.05, 0.04, 0.03, 0.02];
    var frequencyScale = SinOsc.kr(0.13).range(0.8, 1.2);
    var levelScale = SinOsc.kr(0.17).range(0.4, 1);
    var phases = SinOsc.kr([0.07, 0.09, 0.11, 0.13, 0.15]) * 0.3;

    DynKlang.ar(
        `[frequencies, levels * levelScale, phases],
        frequencyScale
    ) ! 2;
}.play
)
