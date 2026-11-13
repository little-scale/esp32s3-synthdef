// Compile and upload this whole expression in Studio's Main editor.
// In the SC IDE append .sendESP32("your-module-name") to ESP32Program(...).
// Tempo is beats per second; the saved program restarts on power-up.
(
ESP32Program(
    {
        arg freq = 440, amp = 0.1, gate = 0, release = 0.15;
        SinOsc.ar(freq) *
        EnvGen.kr(Env.asr(0.005, 1, release), gate) * amp ! 2
    },
    Pbind(
        \degree, Pseq([0, 2, 4, 7, 9, 7, 4, 2], inf),
        \dur, Pseq([0.25, 0.25, 0.5], inf),
        \amp, Pwhite(0.04, 0.1, inf),
        \legato, 0.7
    ),
    tempo: 2, autostart: true, seed: 12345
)
)
