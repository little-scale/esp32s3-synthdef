// Run with the pinned sc/Classes directory in sclang's includePaths.
// No server or audio device is opened.
(
var root = PathName(thisProcess.nowExecutingPath).pathOnly +/+ "..";
var output = root +/+ "build/host/rings-voices";
try {
    File.mkdir(output);
    thisProcess.interpreter.executeFile(root +/+ "examples/rings-benchmarks.scd")
        .do { |definition| definition.writeDefFile(output) };
    0.exit;
} { |error| error.reportError; 1.exit; };
)
