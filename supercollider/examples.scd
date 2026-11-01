// After starting SynthDef Studio and recompiling the SC class library:
ESP32.connect;
ESP32.scan.onDone(_.postln);

// Use the permanent ID shown by the uploader. Aliases are optional.
ESP32.alias(\amoled, "esp32-2884853ad390");

// Global module output volume, after Main + FX. Updates Controls; 0..1 = 0..100%.
ESP32.module(\amoled, \volume, 0.5);
ESP32.module(\all, \volume, 0.5);
// Live volume changes are not saved to flash; use the physical slider to save.

// A Function compiles in this language session. Upload runs asynchronously.
(
{
    arg freq=440,dev=20;
    MiVerb.ar(
        Resonz.ar(
            Splay.ar(Saw.ar(freq + {Lag.kr(LFNoise2.kr(1,dev),1)}!2,0.1)),
            SinOsc.kr(0.1).range(110,1720),0.1,4
        ),0.99,1,0.01
    );
}.sendESP32(\amoled,args:[\freq,440.0]).onDone(_.postln);
)
// After saved-and-verified, create Main:
ESP32.play(\amoled);
ESP32.stop(\amoled);
// Or use Function.playESP32 / SynthDef.playESP32 to upload and create together.
// Use .sendESP32(\all) to compile once and upload identical bytes to paired online modules.
ESP32.set(\amoled,\freq,330.0,\dev,5.0);
ESP32.module(\amoled).main.info.onDone(_.postln);

// Start Main explicitly before parameter automation:
ESP32.play(\amoled);
// Parameter automation does not gate or restart the continuous sound.
(
p=Pbind(
    \type,\esp32Set,
    \module,Pseq([\amoled],inf), // Pseq/Prand can contain aliases, IDs, IPs, groups or \all.
    \freq,Pseq([220,330,440,660],inf),
    \dev,Prand([2.0,5.0,10.0,20.0],inf),
    \dur,0.5
).playESP32;
)
p.stop;

// A gate-controlled Main for note patterns. Wait for deployment inside a Routine.
(
Routine({
    {arg freq=440,amp=0.1,gate=0;
        (SinOsc.ar(Lag.kr(freq,0.01))*amp*EnvGen.kr(Env.asr(0.01,1,0.1),gate))!2;
    }.sendESP32(\amoled).wait;
    p=Pbind(
        \type,\esp32Note,\module,Prand([\amoled],inf),
        \midinote,Pseq([60,64,67,72],inf),\amp,0.12,\dur,0.25,\legato,0.8
    ).playESP32;
}).play;
)
p.stop; // Cancels queued future events and releases only this pattern's held notes.

// Saved stereo master FX. Main and FX are independent destinations.
(
{arg wet=0.3;
    var input=In.ar(0,2);
    FreeVerb2.ar(input[0],input[1],wet,0.8,0.4);
}.sendESP32(\amoled,stage:\fx);
)
// After the FX upload is verified:
ESP32.module(\amoled).fx.play([\wet,0.5]);
ESP32.module(\amoled).fx.bypass(true);
ESP32.module(\amoled).fx.bypass(false);

// Select a complete { ... }.play block, then invoke from a bound shortcut:
// ESP32.sendSelection(\amoled);
// A String of source also supports .sendESP32(target).

// Literal SynthDef uploads preserve authored Out.ar routing and stay silent:
(
d = SynthDef(\literalTone, { arg freq=440, amp=0.1, gate=1;
    Out.ar(0, (SinOsc.ar(freq)*amp*EnvGen.kr(Env.asr,gate))!2);
});
d.sendESP32(\amoled);
)
// After verification:
ESP32.play(\amoled,[\freq,330]);
ESP32.stop(\amoled);
