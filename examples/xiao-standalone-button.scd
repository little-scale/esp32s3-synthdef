(
{
    var held = Lag.kr(In.kr(10), 0.01);
    SinOsc.ar([440, 660]) * held * 0.2;
}.play
)
