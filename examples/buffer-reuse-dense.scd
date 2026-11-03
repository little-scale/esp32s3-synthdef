// Expanded-limit example: compile/upload as a Main definition, then start Main.
// Requires the signal-reuse firmware; the original 160-node/192-output build
// rejects this graph. This file does not start the computer's audio server.
(
SynthDef(\Dense64, {
    Out.ar(0,
        Splay.ar(SinOsc.ar(Array.series(64, 80, 7)), 1, 0.05)
    );
});
)
