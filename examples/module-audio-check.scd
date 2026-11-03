(
{
    arg freq = 440, dev = 50, slide = 1;
    MiVerb.ar(Resonz.ar(Splay.ar(Saw.ar(Lag.kr(freq, slide) + {Lag.kr(LFNoise2.kr(1/slide, dev), slide)}!8, 0.1)), SinOsc.kr(0.1).range(55, 880), 0.1, 5), 0.99, 1, 0.01);
}.play
)
