// SPDX-License-Identifier: GPL-3.0-or-later
ESP32Job {
    var <id, <started, <deadline, <done=false, <result, <error, condition, callbacks, failures;
    *new { |id,timeout=10| ^super.new.init(id,timeout) }
    init { |number,timeout| id=number;started=Main.elapsedTime;deadline=started+timeout;condition=Condition.new;callbacks=List.new;failures=List.new;^this }
    finish { |ok, value|
        if(done){^this};done=true;
        result=value;condition.unhang;
        if(ok){callbacks.do(_.value(value))}{error=value;failures.do(_.value(value));if(failures.isEmpty){("ESP32: "++value.asString).warn}};
        ^this
    }
    wait { if(done.not){condition.hang};if(error.notNil){Error(error.asString).throw};^result }
    onDone { |function| if(done and:{error.isNil}){function.value(result)}{callbacks.add(function)};^this }
    onError { |function| if(done and:{error.notNil}){function.value(error)}{failures.add(function)};^this }
}
ESP32 {
    classvar address, token, client, jobs, counter=0, reply, aliases, players, offset=0;
    classvar <>latency=0.25, <>configPath;
    *initClass {
        jobs=IdentityDictionary.new;aliases=Dictionary.new;players=IdentityDictionary.new;
        configPath="ESP32_STUDIO_CONFIG".getenv ? (Platform.userAppSupportDir +/+ "ESP32Studio/connection.json");
        Event.addEventType(\esp32Set,{ESP32.patternEvent(currentEnvironment,false)});
        Event.addEventType(\esp32Note,{ESP32.patternEvent(currentEnvironment,true)});
        CmdPeriod.add(this);
    }
    *connect { |path|
        var config,job,connection;
        if(path.notNil){configPath=path};
        if(address.notNil and:{address.isConnected}){reply.tryPerform(\enable);^this.request(\hello,())};
        if(address.notNil){this.disconnected(address)};
        config=configPath.parseJSONFile;
        if(config.isNil){Error("Start SynthDef Studio, then set ESP32.configPath or install its connection file.").throw};
        token=config["token"];client=UniqueID.next.asString++"-"++Main.elapsedTime.asStringPrec(17);
        address=NetAddr("127.0.0.1",config["port"].asInteger);
        connection=address;
        reply.tryPerform(\free);
        reply=OSCFunc({|message|
            var job=jobs.removeAt(message[1]),value;
            if(job.notNil){
                value=this.decode(message[3].asString.parseJSON);
                if(message[2]==1){
                    if(value["time"].notNil){offset=value["time"]-((job.started+Main.elapsedTime)*0.5)};
                    if(value["aliases"].notNil){value["aliases"].keysValuesDo{|k,v|aliases[k]=v}};
                    job.finish((value["verified"]!==false) and:{value["queued"]!==false},value)
                }{job.finish(false,value["error"] ? "Bridge error")};
            }
        },'/esp32/reply',address).permanent_(true);
        try {connection.connect({this.disconnected(connection)})} {|error|
            counter=(counter%2147483646)+1;job=ESP32Job(counter);jobs[counter]=job;
            this.disconnected(connection,true);this.watch(job);^job
        };
        job=this.request(\hello,());^job
    }
    *disconnected { |connection,deferred=false|
        var pending,affected,old,finish;
        // A late close callback from an old socket must not close a new session.
        if(connection.notNil and:{address!==connection}){^this};
        old=address;address=nil;pending=jobs.values.copy;affected=players.copy;
        reply.tryPerform(\free);reply=nil;
        try {old.tryPerform(\disconnect)} {|error|nil};
        finish={
            affected.keysValuesDo{|stream,player|player.remoteError(stream,"Studio connection closed")};
            pending.do{|job|jobs.removeAt(job.id);job.finish(false,"Studio connection closed")}
        };
        // Allow request callers to attach their error handlers before a failed
        // synchronous send completes. Jobs stay tracked across CmdPeriod.
        if(deferred){SystemClock.sched(0,{finish.value;nil})}{finish.value};
        ^this
    }
    *disconnect {this.stopPatterns;^this.disconnected}
    *decode { |item|
        ^switch(item[0].asString,
            "n",{nil},"b",{item[1].asString=="1"},"i",{var number=item[1].asString.asFloat;if(number.abs<=2147483647){number.asInteger}{number}},"f",{item[1].asString.asFloat},"s",{item[1].asString},
            "a",{item[1].collect{|v|this.decode(v)}},
            "o",{var result=Dictionary.new;item[1].do{|pair|result[pair[0].asString]=this.decode(pair[1])};result},
            {Error("Invalid Studio reply").throw})
    }
    *json { |value|
        if(value.isKindOf(ESP32Target)){^this.json(value.target)};
        if(value.isNil){^"null"};if(value===true){^"true"};if(value===false){^"false"};
        if(value.isKindOf(Float)){if(value.isNaN or:{value.abs==inf}){Error("ESP32 values must be finite").throw};^value.asStringPrec(17)};
        if(value.isKindOf(Integer)){^value.asString};
        if(value.isKindOf(Dictionary)){^"{"++value.keys.asArray.collect{|k|this.json(k.asString)++":"++this.json(value[k])}.join(",")++"}"};
        if(value.isKindOf(String) or:{value.isKindOf(Symbol)}){
            var text="";
            value.asString.do{|char|text=text++switch(char,$\",{"\\\""},$\\,{"\\\\"},Char.nl,{"\\n"},13.asAscii,{"\\r"},9.asAscii,{"\\t"},{char.asString})};
            ^"\""++text++"\""
        };
        if(value.isArray){^"["++value.collect{|item|this.json(item)}.join(",")++"]"};
        Error("Cannot encode ESP32 argument: "++value.class).throw
    }
    *request { |action,payload,source="",graph|
        var job,timeout,connection,opening,encoded=this.json(payload),sourceBytes=Int8Array.newFrom(source.ascii),graphBytes=graph ? Int8Array.new,bytes;
        if(sourceBytes.size>65536 or:{graphBytes.size>65536}){Error("Source and graph must each fit 64 KiB").throw};
        if(address.notNil and:{address.isConnected.not}){this.disconnected(address)};
        if(address.isNil){opening=this.connect;if(address.isNil){^opening};opening.onError({})};
        connection=address;
        counter=(counter%2147483646)+1;timeout=if(#[deploy,program].includes(action)){120}{10};job=ESP32Job(counter,timeout);jobs[counter]=job;
        // Cancellation is best effort after a stream has already stopped.
        if(action==\control and:{payload[\kind]==\cancel}){job.onError({})};
        // SC's OSC builder has a 64 KiB limit even over TCP. Larger jobs are
        // assembled by the bridge; code is never evaluated until commit.
        try {
            if((sourceBytes.size+graphBytes.size+encoded.size)>30000){
                connection.sendMsg('/esp32/begin',token,client,counter,action.asString,encoded,sourceBytes.size,graphBytes.size);
                bytes=sourceBytes++graphBytes;
                (0,8192..bytes.size-1).do{|at|
                    connection.sendMsg('/esp32/chunk',token,client,counter,at,bytes.copyRange(at,(at+8191).min(bytes.size-1)));
                };
                connection.sendMsg('/esp32/commit',token,client,counter);
            }{
                // A nonempty prefix also avoids SC's zero-length blob encoding bug.
                connection.sendMsg('/esp32/request',token,client,counter,action.asString,encoded,(Int8Array[1]++sourceBytes),(Int8Array[1]++graphBytes));
            };
        } {|error|this.disconnected(connection,true)};
        if(action==\deploy){job.onDone({|report|report["results"].do{|row|("ESP32 "++row["device_id"]++": saved and verified").postln}})};
        this.watch(job);^job
    }
    *watch { |job|
        SystemClock.sched((job.deadline-Main.elapsedTime).max(0),{if(job.done.not){jobs.removeAt(job.id);job.finish(false,"ESP32 request timed out")};nil});
    }
    *cmdPeriod {
        this.stopPatterns;
        // CmdPeriod clears SystemClock before invoking us. Keep pending jobs
        // bounded by their original deadlines after that clock reset.
        jobs.values.copy.do{|job|this.watch(job)};
    }
    *alias { |name,module| aliases[name.asString]=module.asString;^this.request(\alias,(name:name,module:module)) }
    *scan {^this.request(\scan,())}
    *discovered {
        var scan = this.scan;
        var result = ESP32Job(0, (scan.deadline - Main.elapsedTime).max(0));
        scan.onDone({ |report|
            result.finish(true, report["modules"].select { |row| row["online"] === true });
        }).onError({ |error| result.finish(false, error) });
        ^result
    }
    *module { |target ... args|
        if(args.isEmpty){^ESP32Target(target)};
        ^this.request(\meta,(target:target,args:args))
    }
    *omni { ^ESP32Target(\all) }
    *group { |name| ^ESP32Target((group: name.asString)) }
    *groups { ^this.request(\groups, ()) }
    *now { ^Main.elapsedTime+offset }
    *deploy { |function,target,args,stage=\main,name,source,definitionOnly=true|
        var definition,original=source;
        if(target.isNil){Error("Choose a module, alias, address, group or \\all").throw};
        if(function.isKindOf(SynthDef)){
            definition=function;
            if(original.isNil and:{definition.func.notNil} and:{definition.func.def.sourceCode.notNil}){
                original="SynthDef("++definition.name.asCompileString++", "++definition.func.def.sourceCode++")";
            };
        }{
            original=original ? function.def.sourceCode;
            definition=SynthDef(if(stage==\fx){\MasterFX}{\SoundBlock},{
                var signal=SynthDef.wrap(function).asArray;
                var mode=if(stage==\main and:{definitionOnly.not}){NamedControl.ir(\__esp32_autoplay,1)}{nil};
                if(UGen.buildSynthDef.children.any{|u|u.isKindOf(AbstractOut)}){Error("Return audio from the Function; use a literal SynthDef for authored Out.ar routing.").throw};
                if(signal.size<1 or:{signal.size>2}){Error("Return mono or stereo audio").throw};
                signal=signal.collect{|channel|if(channel.isNumber){DC.ar(channel)}{if(channel.rate==\audio){channel}{K2A.ar(channel)}}};
                if(signal.size==1){signal=signal.dup(2).flat};Out.ar(0,signal)
            });
        };
        if(original.isNil){Error("Original source unavailable: supply source: when sending this definition.").throw};
        ^this.request(\deploy,(target:target,args:args ? [],stage:stage,name:name,definition:definitionOnly),original,definition.asBytes)
    }
    *playObject { |object,target,args,stage=\main,name,source|
        var combined=ESP32Job(0,120),autonomous=object.isKindOf(Function);
        this.deploy(object,target,if(autonomous){args}{nil},stage,name,source,autonomous.not).onDone({|report|
            if(autonomous){combined.finish(true,report)}{
                try {this.playStage(target,stage,args).onDone({|r|combined.finish(true,r)}).onError({|e|combined.finish(false,e)})}
                {|error|combined.finish(false,error.errorString)}
            }
        }).onError({|error|combined.finish(false,error)});
        ^combined
    }
    *sendCode { |source,target,args,stage=\main,name| ^this.request(\deploy,(target:target,stage:stage,args:args ? [],name:name,definition:true),source) }
    *program { |sound,pattern,target,tempo=1,autostart=true,seed=0,name|
        ^ESP32Program(sound,pattern,tempo,autostart,seed).sendESP32(target,name)
    }
    *programInfo { |target| ^this.request(\pattern,(target:target,command:\info)) }
    *programPlay { |target| ^this.request(\pattern,(target:target,command:\play)) }
    *programStop { |target| ^this.request(\pattern,(target:target,command:\stop)) }
    *sendSelection { |target,stage=\main,args,name|
        var document=Document.current,source;
        if(document.isNil){Error("Open a document in the SuperCollider IDE and select code first").throw};
        source=document.selectedString;
        if(source.isNil or:{source.stripWhiteSpace.isEmpty}){Error("Select a sound Function or SynthDef first").throw};
        ^this.sendCode(source,target,args,stage,name)
    }
    *gui {
        {
            var window=Window("ESP32 Studio",Rect(100,100,460,155));
            var targets=[\all],destination=PopUpMenu(window,Rect(12,12,310,26)).items_(["All paired online modules"]);
            var stage=PopUpMenu(window,Rect(332,12,116,26)).items_(["Main","FX"]);
            var status=StaticText(window,Rect(12,100,436,40)).string_("Select code in the IDE, then click Send selected code.");
            Button(window,Rect(12,50,436,34)).states_([["Send selected code"]]).action_({
                status.string="Compiling and uploading…";
                try {
                    ESP32.sendSelection(targets[destination.value],[\main,\fx][stage.value])
                        .onDone({{status.string="Saved and verified."}.defer})
                        .onError({|error|{status.string=error.asString}.defer});
                } {|error|status.string=error.errorString};
            });
            ESP32.scan.onDone({|report|{
                var rows=report["modules"].select{|row|row["paired"] and:{row["online"]}};
                targets=[\all]++rows.collect{|row|row["device_id"]};
                destination.items=["All paired online modules"]++rows.collect{|row|row["device_name"]++" · "++row["device_id"]};
            }.defer});
            window.front;
        }.defer;^this
    }
    *set { |target ... args| ^this.setStage(target,\main,args) }
    *setStage { |target,stage,args| ^this.request(\control,(kind:\set,target:target,stage:stage,args:args,stream:1)) }
    *play { |target,args| ^this.playStage(target,\main,args) }
    *playStage { |target,stage,args| ^this.request(\play,(target:target,stage:stage,args:args ? [])) }
    *stop { |target| ^this.request(\stop,(target:target,stage:\main)) }
    *prepare { |target,stage=\main| ^this.request(\prepare,(target:target,stage:stage)) }
    *info { |target,stage=\main| ^this.request(\info,(target:target,stage:stage)) }
    *cancel { |stream| if(address.isNil or:{address.isConnected.not}){^nil};^this.request(\control,(kind:\cancel,stream:stream)) }
    *patternEvent { |event,note|
        var stream=event[\esp32Stream],player=players[stream],args=List.new;
        var reserved=#[type,module,stage,dur,delta,stretch,legato,sustain,midinote,note,degree,octave,scale,root,ctranspose,mtranspose,gtranspose,harmonic,detune,db,params,addToCleanup,addToNodeCleanup,removeFromCleanup,server,instrument,group,out,esp32Stream];
        if(stream.isNil){Error("Use .playESP32 for ESP32 patterns so stop and CmdPeriod cancel queued notes.").throw};
        event.keysValuesDo{|key,value|if(reserved.includes(key).not and:{note.not or:{key!=\gate}}){args.add(key);args.add(value.value)}};
        if(note){
            args=List.new.addAll(args.asArray.clump(2).reject{|pair|#[freq,amp].includes(pair[0])}.flat);
            args.add(\freq);args.add(event.use{~freq.value});args.add(\amp);args.add(event.use{~amp.value});
        };
        if(event[\params].notNil){event[\params].keysValuesDo{|key,value|args.add(key);args.add(value.value)}};
        ^this.request(\control,(kind:if(note){\note}{\set},target:event[\module],stage:event[\stage] ? \main,
            args:args.asArray,stream:stream,lead:thisThread.seconds+latency-Main.elapsedTime,
            sustain:if(note){event.use{~sustain.value}/thisThread.clock.tempo}{0})).onError({|error|if(player.notNil){player.remoteError(stream,error)}})
    }
    *registerPattern { |stream,player| players[stream]=player }
    *forgetPattern { |stream| players.removeAt(stream) }
    *stopPatterns {players.values.copy.do(_.stop)}
}
ESP32Target {
    var <target;
    *new { |target| ^super.newCopyArgs(target) }
    main { ^ESP32Stage(target,\main) }
    fx { ^ESP32Stage(target,\fx) }
}
ESP32Stage {
    var <target,<stage;
    *new { |target,stage| ^super.newCopyArgs(target,stage) }
    send { |function,args,name,source| ^ESP32.deploy(function,target,args,stage,name,source) }
    sendSelection { |args,name| ^ESP32.sendSelection(target,stage,args,name) }
    set { |... args| ^ESP32.setStage(target,stage,args) }
    setn { |name,values| ^ESP32.setStage(target,stage,[name,values]) }
    info { ^ESP32.info(target,stage) }
    play { |args| ^ESP32.playStage(target,stage,args) }
    stop { ^ESP32.request(\stop,(target:target,stage:stage)) }
    bypass { |enabled=true| if(stage!=\fx){Error("Bypass applies to FX").throw};^ESP32.request(\bypass,(target:target,bypassed:enabled)) }
    restart { ^this.play }
    panic { ^ESP32.request(\panic,(target:target)) }
}
ESP32Player : EventStreamPlayer {
    var remoteStream, cancelled=true, failed=false;
    play { |argClock,doReset=false,quant|
        // A clock/stop-era reset can leave a retained stream non-nil even
        // though it is no longer scheduled. Clear it before super.play's
        // "already playing" guard, and give the replay a fresh remote stream.
        if(this.isPlaying and:{this.wasStopped}){this.stop;doReset=true};
        if(this.isPlaying.not){
            remoteStream=UniqueID.next;cancelled=false;failed=false;
            this.event[\esp32Stream]=remoteStream;
            // Child Pdef/Pbindef streams execute inherited event cleanups when
            // their source changes. Only this player's lifecycle owns cancel.
            ESP32.registerPattern(remoteStream,this);
        };
        ^super.play(argClock,doReset,quant)
    }
    cancelRemote {
        if(cancelled.not){
            cancelled=true;ESP32.forgetPattern(remoteStream);ESP32.cancel(remoteStream);
        };
    }
    remoteError { |stream,error|
        var detail;
        // A reply from a cancelled run must not stop a later replay or emit
        // one warning for every event that was already in flight.
        if(stream==remoteStream and:{cancelled.not} and:{failed.not}){
            failed=true;
            detail=if(error.isKindOf(Dictionary)){
                (error["results"] ? []).select{|row|row["queued"]===false}.collect{|row|
                    row["device_id"]++": "++(row["error"] ? "Control failed")
                }.join("; ")
            }{error.asString};
            ("ESP32 pattern stopped: "++detail).warn;this.stop;
        };
    }
    stop {this.cancelRemote;super.stop}
    removedFromScheduler { |freeNodes=true|
        if(this.streamHasEnded.not){this.cancelRemote}{ESP32.forgetPattern(remoteStream)};
        super.removedFromScheduler(freeNodes);
    }
}
+ Function {
    playESP32 { |target,args,stage=\main,name,source| ^ESP32.playObject(this,target,args,stage,name,source) }
    sendESP32 { |target,args,stage=\main,name,source| ^ESP32.deploy(this,target,args,stage,name,source) }
}

+ SynthDef {
    sendESP32 { |target,args,stage=\main,name,source| ^ESP32.deploy(this,target,args,stage,name,source) }
    playESP32 { |target,args,stage=\main,name,source| ^ESP32.playObject(this,target,args,stage,name,source) }
}

+ String {
    sendESP32 { |target,args,stage=\main,name| ^ESP32.sendCode(this,target,args,stage,name) }
}

+ Pattern {
    playESP32 { |clock,quant| ^ESP32Player(this.asStream,Event.default).play(clock,false,quant) }
}

+ EventPatternProxy {
    playESP32 { |clock,quant|
        var reset=false;
        if(player.notNil and:{player.isKindOf(ESP32Player).not}){
            player.stop;player=nil;
        };
        if(player.isNil){
            player=ESP32Player(this.asProtected.asStream,Event.default);
        }{
            reset=player.streamHasEnded or:{player.wasStopped};
        };
        playQuant=quant ? this.quant;
        if(player.isPlaying.not or:{player.wasStopped}){player.play(clock ? this.clock,reset,playQuant)};
        ^player
    }
}
