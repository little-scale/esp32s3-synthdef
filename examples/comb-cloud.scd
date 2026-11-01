(

{
	arg freq = 330;
	var copies = 5;
	CombC.ar(Splay.ar(Decay2.ar(Dust.ar(1!copies), 0.01, SinOsc.ar(0.1, 270.degrad).range(0.1, 2)) * SinOsc.ar((1..copies) * freq * {Rand(0.99, 1.01!10)})), 0.05, SinOsc.ar(5).range(0.049, 0.05), 5)  * 0.5;
}.play
)
