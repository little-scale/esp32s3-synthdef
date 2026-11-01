// Included inside the compiler's try block, after evaluating a bare Function.
// SynthDef.wrap preserves the Function's argument names and defaults.
if(def.isKindOf(Function)) {
    var sound = def;
    def = SynthDef(if(autoPlay) { \SoundBlock } { \MasterFX }, {
        var signal = SynthDef.wrap(sound).asArray;
        var mode = if(autoPlay and: { definitionOnly.not }) { NamedControl.ir(\__esp32_autoplay, 1) } { nil };
        if(UGen.buildSynthDef.children.any { |ugen| ugen.isKindOf(AbstractOut) }) {
            Error("Sound block must return audio, rather than writing Out.ar itself").throw;
        };
        if(signal.size < 1 or: { signal.size > 2 }) {
            Error("Sound block must return one or two channels").throw;
        };
        signal = signal.collect { |channel|
            if(channel.isNumber) {
                DC.ar(channel)
            } {
                if(channel.isKindOf(UGen).not or: { channel.numOutputs != 1 }) {
                    Error("Sound block must return audio, rather than writing Out.ar itself").throw;
                };
                switch(channel.rate,
                    \audio, { channel },
                    \control, { K2A.ar(channel) },
                    \scalar, { DC.ar(channel) },
                    { Error("Sound block must return an audio, control or scalar signal").throw }
                )
            }
        };
        if(signal.size == 1) { signal = signal.dup(2).flat };
        Out.ar(0, signal);
    });
};
