// Evaluate this block with SynthDef Studio running.
// It uploads the precompiled example, then starts a note pattern on your module.
// No MiRings1 class-library installation or recompile is needed for this demo.
// Change target for another module, an alias, or \all.
(
var target = "esp32-2884853ad390";
var root = PathName(ESP32.filenameSymbol.asString).pathOnly +/+ "..";
var source = File.readAllString(root +/+ "examples/mirings1.scd");
var graph = File.use(root +/+ "examples/miRings1.scsyndef", "rb", { |file|
    file.read(Int8Array.newClear(file.length));
});

if(~miRings1Pattern.notNil) { ~miRings1Pattern.stop };
ESP32.connect;
ESP32.request(\deploy, (
    target: target, stage: \main, name: "MiRings1", definition: true
), source, graph).onDone({
    ~miRings1Pattern = Pbind(
        \type, \esp32Note,
        \module, target,
        \midinote, Pseq([48, 55, 60, 62, 67, 64], inf),
        \amp, 0.35,
        \bright, Pwhite(0.4, 0.8),
        \structure, 0.25,
        \damp, 0.65,
        \pos, Pwhite(0.2, 0.8),
        \dur, 0.5,
        \legato, 0.35
    ).playESP32;
}).onError({ |error| error.warn });
)

// Stop the pattern (select and evaluate this line separately):
// ~miRings1Pattern.stop;
// The resonator's remaining tail will continue. To free Main immediately:
// ESP32.stop("esp32-2884853ad390");
//
// To edit/recompile the source SynthDef later, add the project's
// upstream/fm1-synthdef/synthdef-engine/sc/Classes directory to SC's
// included library paths, save the configuration, and recompile the library.
