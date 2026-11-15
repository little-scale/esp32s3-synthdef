// Paste into Studio as a Sound block. In SC, replace .play with
// .playESP32("YOUR_VOICE_PE_ID_OR_NAME"). No local audio input is used.
(
{
    var size = 12, env, sig, brightness;
    env = Decay.kr(Dust.kr(0.8 ! size), 0.5);
    sig = SinOsc.ar((60 + (0..(size - 1))).midicps) * env * 0.05;

    // Follow each audio voice before mixing it; one RGB triplet per LED.
    brightness = (Amplitude.kr(sig, 0.01, 0.25) * 20).clip(0, 1);
    Out.kr(3, brightness.collect { |level| [level * 0.5, 0, level] }.flat);

    Splay.ar(sig);
}.play
)
