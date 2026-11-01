(
{
    arg freq = 330;
    var copies = 5;
    var frequencies = Array.fill(copies, { |i|
        freq * (i + 1) * Rand(0.99, 1.01)
    });
    var decay = SinOsc.kr(0.1, 270.degrad).range(0.1, 2);
    var excitation = Decay2.ar(Dust.ar(1!copies), 0.01, decay);
    var sound = Splay.ar(excitation * SinOsc.ar(frequencies));
    CombC.ar(sound, 0.05, SinOsc.ar(5).range(0.049, 0.05), 5) * 0.5;
}.play
)
