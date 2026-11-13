// SPDX-License-Identifier: GPL-3.0-or-later
// Export pattern structure. Functions are rejected rather than evaluated.
ESP32Pattern {
    *tree { |value, depth=0|
        var name, args;
        if(depth > 24) { Error("ESP32 pattern nesting exceeds 24").throw };
        if(value === inf) { ^(op: "Infinity", args: []) };
        if(value.isNumber or: { value === true } or: { value === false }) { ^value };
        if(value.isKindOf(Symbol) or: { value.isKindOf(String) }) { ^value.asString };
        if(value.isArray) { ^value.collect { |item| this.tree(item, depth+1) } };
        if(value.isKindOf(Rest)) { ^(op: "rest", args: [this.tree(value.value,depth+1)]) };
        if(value.isKindOf(Function)) {
            Error("Arbitrary SC functions cannot run in an ESP32 pattern; use supported pattern nodes.").throw;
        };
        name = value.class.name.asString;
        if(#["Pseq","Pser","Prand","Pxrand","Pshuf","Pwrand","Pseries","Pgeom",
            "Pwhite","Pexprand","Pbrown","Pgbrown","Pn","Pstutter","Pdup","Pfin",
            "Pdrop","Pkey","Pbind","Pchain","Pbindf","Punop","Pbinop","Ptuple",
            "Pswitch","Pswitch1","Pseed","Ptime","Pbjorklund","Pbjorklund2"].any({|item|item==name}).not) {
            Error("Unsupported standalone ESP32 pattern: " ++ name).throw;
        };
        args = if(name == "Pchain") { value.patterns } { value.storeArgs };
        if(name == "Punop") { args = [value.operator,value.a] };
        if(name == "Pbinop") { args = [value.operator,value.a,value.b,value.adverb] };
        if(name == "Pn") {
            if(args[2].notNil) { Error("Pn environment-key mode is not supported on ESP32").throw };
            args = args.copyRange(0,1);
        };
        if(name == "Pkey" and: { args[1].isNil }) { args = [args[0],inf] };
        // Nil binary adverb means ordinary pairwise stream arithmetic.
        if(name == "Pbinop" and: { args.last.isNil }) {
            ^(op: name, args: args.copyRange(0,args.size-2).collect { |item| this.tree(item,depth+1) } ++ [nil]);
        };
        ^(op: name, args: args.collect { |item| this.tree(item,depth+1) });
    }
    *asJSON { |pattern| ^ESP32.json(this.tree(pattern)) }
}
