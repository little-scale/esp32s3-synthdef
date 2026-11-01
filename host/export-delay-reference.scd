// Compare the same DSP body using ReplaceOut for SC's shared bus semantics.
(
var root=PathName(thisProcess.nowExecutingPath).pathOnly +/+ "..";
try {
    var text=File.readAllString(root +/+ "examples/master-delay.scd");
    var effect=thisProcess.interpreter.interpret(text.replace("Out.ar(0,", "ReplaceOut.ar(0,"));
    var producer=SynthDef('delay-test-input', { var signal=Impulse.ar(0,0,0.25); Out.ar(0,[signal,signal]); });
    3.do { |mode|
        var events=[

            [0,[\d_recv,producer.asBytes]], [0,[\d_recv,effect.asBytes]],
            [0,[\s_new,producer.name,1000,0,0]],
            [0,[\s_new,effect.name,1001,1,0,\time,if(mode==0,5,0.35),\feedback,if(mode==0,0.35,0.8),\wet,if(mode==0,1,0.5)]]
        ];
        if(mode==2) {
            events=events ++ [
                [68*64/44100,[\n_set,1001,\time,0.02,\feedback,0,\wet,1]],
                [137*64/44100,[\n_set,1001,\time,5,\feedback,0.8,\wet,0.25]]
            ];
        };
        // Free persistent delay units while their plugin is still loaded.
        events=events ++ [[12,[\n_free,1000,1001]],[12+(64/44100),[\c_set,0,0]]];
        Score(events).writeOSCFile(root +/+ "build/host" +/+ ("delay-reference-" ++ mode ++ ".osc"));
    };
    0.exit;
} { |error| error.reportError;1.exit; };
)
