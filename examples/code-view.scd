// A silent export; creating a Pattern does not play it.
(
var definition;
~root = 330;
"Original source text";
Pbind(\degree, Pseq([0, 2, 4], inf));
nil; 0x29A; 16rA.B;

definition = SynthDef(\CodePreview, {
    arg freq=330, amp=0.5, gate=1,
        knob1=0.5, knob2=0.5,
        knob3=0.1, knob4=0.2;
    var sound, envelope;
    sound = SinOsc.ar(freq);
    envelope = EnvGen.ar(
        Env.asr(0.01, 1, 0.15), gate,
        doneAction: 2
    );
    Out.ar(0, Pan2.ar(
        sound * envelope * amp * 0.2
    ));
});
definition
)
