(
var root = thisProcess.nowExecutingPath.dirname.dirname;
var dir = root +/+ "examples";
var def = (dir +/+ "touch-sine.scd").load;
var score = Score([
    [0, [\d_recv, def.asBytes]],
    [0, [\s_new, def.name, 1000, 0, 1]],
    [0.1, [\n_set, 1000, \knob1, 0.75]],
    [0.2, [\n_set, 1000, \knob2, 0.3]],
    [0.25, [\n_set, 1000, \gate, 0]],
    [0.51, [\g_freeAll, 1]], [0.52, [0]]
]);
def.writeDefFile(dir);
score.writeOSCFile(dir +/+ "touch-sine.osc");
"Touch sine exported".postln;
0.exit;
)
