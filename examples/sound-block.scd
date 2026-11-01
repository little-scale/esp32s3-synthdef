(
{
	arg freq = 220;
	var copies = 10;
	Splay.ar(Decay.ar(Dust.ar(1!copies), 2) * SinOsc.ar((1..copies) * 220 * {Rand(0.99, 1.01)})) * SinOsc.ar(220);
}.play
)
