// Compile the exact source without opening an audio server.
(
var root = PathName(thisProcess.nowExecutingPath).pathOnly +/+ "..";
var definition;
try {
    definition = thisProcess.interpreter.executeFile(root +/+ "examples/touch-buses.scd");
    if(definition.isKindOf(SynthDef).not) { Error("Expected a SynthDef").throw };
    definition.writeDefFile(root +/+ "examples");
    0.exit;
} { |error| error.reportError; 1.exit };
)
