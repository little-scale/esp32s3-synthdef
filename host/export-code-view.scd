// Export without opening a server or audio device.
(
var root = PathName(thisProcess.nowExecutingPath).pathOnly +/+ "..";
var output = root +/+ "build/host/code-view";
var definition;
try {
    File.mkdir(output);
    definition = thisProcess.interpreter.executeFile(root +/+ "examples/code-view.scd");
    if(definition.isKindOf(SynthDef).not) { Error("Expected a SynthDef from code-view.scd").throw };
    definition.writeDefFile(output);
    0.exit;
} { |error| error.reportError; 1.exit; };
)
