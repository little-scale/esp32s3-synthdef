// Build the candidate graph files and deterministic SuperCollider NRT scores.
(
var root = PathName(thisProcess.nowExecutingPath).pathOnly +/+ "..";
var rate = 44100;
try {
    ["phase-fm", "additive", "filtered"].do { |name|
        var def = thisProcess.interpreter.executeFile(root +/+ "examples" +/+ (name ++ ".scd"));
        var score;
        def.writeDefFile(root +/+ "examples");
        score = Score([
            [0.0, [\d_recv, def.asBytes]],
            [0.0, [\s_new, def.name, 1000, 0, 0]],
            [68*64/rate, [\n_set, 1000, \knob1, 0.75, \knob2, 0.7]],
            [137*64/rate, [\n_set, 1000, \knob1, 0.13, \knob2, 0.2]],
            [172*64/rate, [\n_set, 1000, \gate, 0]],
            [345*64/rate, [\c_set, 0, 0]]
        ]);
        score.writeOSCFile(root +/+ "examples" +/+ (name ++ ".osc"));
    };
    0.exit;
} { |error| error.reportError; 1.exit; };
)
