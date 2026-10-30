// Exact source of upstream fixtures/fm1_voice.scsyndef; name retained for reproducibility.
SynthDef(\fm1_voice, { |freq=440, amp=0.1, gate=1, pan=0|
    Out.ar(0, Pan2.ar(SinOsc.ar(freq)*EnvGen.ar(Env.adsr(0.01,0.08,0.5,0.15),gate,doneAction:2)*amp,pan))
})
