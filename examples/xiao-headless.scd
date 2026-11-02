// Start Studio, connect its USB device selector to the XIAO, then evaluate:
ESP32.connect;
ESP32.alias(\xiao, "esp32-288485ba1e48"); // Replace with your board's ID.

// Save a named stereo definition. Deployment is silent.
(
SynthDef(\xiaoVoice, { |freq=220, amp=0.2, gate=0|
    var envelope=EnvGen.kr(Env.adsr(0.01,0.05,0.6,0.04),gate);
    Out.ar(0,SinOsc.ar(freq*[1,1.5])*envelope*amp);
}).sendESP32(\xiao);
)

// After "saved and verified", play notes over USB or paired Wi-Fi.
(
p=Pbind(
    \type,\esp32Note, \module,\xiao,
    \midinote,Pseq([48,55,60,62,67,64],inf),
    \amp,0.2, \dur,0.25, \legato,0.7
).playESP32;
)
p.stop;
ESP32.stop(\xiao);

// Global output level, 0..1. Does not change the SynthDef's amp control.
ESP32.module(\xiao,\volume,0.5);
ESP32.module(\xiao,\volume,1);

// BOOT button example: standard In.kr; no custom hardware UGen.
// Upload and start it, then hold/release BOOT while the board is running.
(
{
    SinOsc.ar([440,660])*Lag.kr(In.kr(10),0.01)*0.2;
}.playESP32(\xiao);
)
ESP32.request(\inputs,(target:\xiao)).onDone(_.postln);
ESP32.stop(\xiao);

// Autonomous sound for capturing without physical audio output.
(
{ |freq=220, amp=0.15|
    SinOsc.ar(freq*[1,1.5])*amp;
}.playESP32(\xiao);
)
// In a terminal, with Studio still connected:
// python3 host/capture.py --studio --output build/host/xiao.wav
ESP32.stop(\xiao);
