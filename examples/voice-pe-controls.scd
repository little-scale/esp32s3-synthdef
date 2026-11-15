// Voice PE: button 0, dial 1, mute sense 2; RGB 3..38; shared RGB 39..41.
// Upload as a Sound block in Studio. Keep module volume low for first listening.
(
{
    var button = In.kr(0);
    var dial = In.kr(1);
    var position = dial * 11;
    var hz = dial.linexp(0, 1, 110, 880);

    Out.kr(39, [0, 0.1, 0]);
    12.do { |i|
        var weight = (1 - (position - i).abs).clip(0, 1);
        Out.kr(3 + (i * 3), [button * 0.4 * weight, 0.1, weight * 0.4]);
    };

    SinOsc.ar(hz, 0, 1) * Lag.kr(button, 0.01) ! 2
}.play
)
