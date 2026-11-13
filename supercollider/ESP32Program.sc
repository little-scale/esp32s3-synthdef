// SPDX-License-Identifier: GPL-3.0-or-later
// A data bundle: constructing it never plays audio or starts a host pattern.
ESP32Program {
    var <sound, <pattern, <tempo, <autostart, <seed;
    *new { |sound,pattern,tempo=1,autostart=true,seed=0|
        ^super.newCopyArgs(sound,pattern,tempo,autostart,seed)
    }
    definition {
        if(sound.isKindOf(SynthDef)) { ^sound };
        if(sound.isKindOf(Function).not) { Error("ESP32Program needs a Function or SynthDef").throw };
        ^SynthDef(\StandaloneProgram,{
            var signal=SynthDef.wrap(sound).asArray;
            if(UGen.buildSynthDef.children.any{|u|u.isKindOf(AbstractOut)}) {
                Error("Return audio from the Function; use SynthDef for authored Out routing").throw;
            };
            if(signal.size<1 or:{signal.size>2}) { Error("Return mono or stereo audio").throw };
            signal=signal.collect{|x|if(x.isNumber){DC.ar(x)}{if(x.rate==\audio){x}{K2A.ar(x)}}};
            if(signal.size==1){signal=signal.dup(2).flat};Out.ar(0,signal);
        })
    }
    specification {
        ^(pattern:ESP32Pattern.tree(pattern),tempo:tempo,autostart:autostart,seed:seed)
    }
    source {
        var code;
        if(sound.isKindOf(Function)) {code=sound.def.sourceCode} {
            if(sound.func.notNil and:{sound.func.def.sourceCode.notNil}) {
                code="SynthDef("++sound.name.asCompileString++", "++sound.func.def.sourceCode++")";
            };
        };
        if(code.isNil) {Error("Original program sound source is unavailable").throw};
        ^"ESP32Program(\n"++code++",\n"++pattern.asCompileString++",\n"++tempo.asCompileString++", "++autostart.asCompileString++", "++seed.asCompileString++"\n)"
    }
    sendESP32 { |target,name|
        var spec=this.specification;
        spec[\target]=target;spec[\name]=name;
        ^ESP32.request(\program,spec,this.source,this.definition.asBytes)
    }
}
