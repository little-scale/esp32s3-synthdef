(
{
    var trigger = Dust.kr(2);
    var frequency = TChoose.kr(trigger, [48, 60, 67, 72].midicps);
    var sound = SinOsc.ar(frequency) * Decay2.kr(trigger, 0.005, 0.5) * 0.2;
    sound ! 2;
}.play
)
