(
{
	arg freq = 220;
	var size = 5, trig, amps, decays, freqs, randamp = 10000, rate = 2;
	trig = Dust.kr(rate);

	freq = TChoose.kr(trig, [70, 60, 67, 63, 86].midicps);

	freqs = (1..size) * freq;
	amps = Array.fill(size, {TExpRand.kr(1, randamp, trig)});
	decays = Array.fill(size, {TRand.kr(0.01, 1 * (1 / rate), trig)});

	Splay.ar(SinOsc.ar(freqs, 0, amps.normalizeSum) * Decay.kr(trig, decays)) * 0.2;
}.play
)
