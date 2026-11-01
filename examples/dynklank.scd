(
{
    var size = 5;
    var frequencies = Array.fill(size, { Rand(220, 2200) });
    var ringTimes = Array.fill(size, { Rand(0.2, 2) });
    var levels = Array.fill(size, { Rand(0.04, 0.1) });
    var frequencyScale = SinOsc.kr(0.13).range(0.8, 1.2);
    var decayScale = SinOsc.kr(0.17).range(0.5, 1.5);
    var levelScale = SinOsc.kr(0.11).range(0.4, 1);

    DynKlank.ar(
        `[frequencies, levels * levelScale, ringTimes],
        Dust.ar(1) * 0.05,
        frequencyScale, 0, decayScale
    ) ! 2;
}.play
)
