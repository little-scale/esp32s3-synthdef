#!/usr/bin/env python3
"""Actual sclang extension -> OSC/TCP bridge -> two paired HTTP modules; silent."""
import json,socket,struct,subprocess,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from test_network import Module
from network import Pairings
from studio import Studio,Compiler
from ide_bridge import Bridge,Hub,osc_message,osc_decode
from synthdef_binary import decode
from control_client import defaults,controls,packet
ROOT=Path(__file__).resolve().parents[1]
SCLANG='/Applications/SuperCollider.app/Contents/MacOS/sclang'
LANGUAGE=ROOT/'build/host/ide-language.yaml'
installed=Path.home()/'Library/Application Support/SuperCollider/Extensions/ESP32Studio'
LANGUAGE.parent.mkdir(parents=True,exist_ok=True)
same_install=installed.is_symlink() and installed.resolve()==ROOT/'supercollider'
excluded=[str(installed),str(installed.resolve())] if installed.exists() and not same_install else []
LANGUAGE.write_text(json.dumps(dict(includePaths=[] if same_install else [str(ROOT/'supercollider')],excludePaths=excluded,postInlineWarnings=False)))

class ControlModule(Module):
    def __init__(self,number):
        super().__init__(number);self.graphs=[None,None];self.revisions=[1,1];self.values=[[],[]];self.remote_events=[];self.running=[False,False];self.volume=100;self.volume_history=[];self.supports_deltas=False;self.delta_baselines={};self.remote_wires=[]
    def operation(self,op,data):
        if op=='VOLUME':
            self.calls.append(op)
            if data:self.volume=data[0];self.volume_history.append(self.volume)
            return dict(percent=self.volume)
        if op=='RCINFO':
            stage,page=data;g=self.graphs[stage];items=[]
            if g:
                for name,index in g['names']:
                    count=min([i-index for n,i in g['names'] if i>index]+[len(g['controls'])-index]);rate=1;trigger=False
                    for typ,r,refs,rates,start in g['nodes']:
                        if typ in ('Control','LagControl','TrigControl') and start<=index<start+len(rates):rate=r;trigger|=typ=='TrigControl'
                    items.append(dict(name_hex=name.encode().hex(),index=index,count=count,rate=rate,trigger=trigger,writable=rate==1 and not name.startswith('__esp32_'),values=self.values[stage][index:index+count]))
            return dict(boot=100,revision=self.revisions[stage],now_us=round(time.monotonic()*1e6),active=self.running[stage],prepared=self.running[stage],total=len(items),controls=items[page*8:page*8+8])
        if op in ('START','STOP'):
            boot,revision,stage,count=struct.unpack_from('<IIBB',data)
            assert boot==100 and revision==self.revisions[stage]
            self.running[stage]=op=='START';self.revisions[stage]+=1
            if op=='START':
                self.values[stage]=self.graphs[stage]['controls'].copy()
                for i in range(count):
                    index,value=struct.unpack_from('<Bf',data,10+i*5);self.values[stage][index]=value
            return dict(started=self.running[stage])
        if op=='RCEVENT':
            boot,rev,stream,seq,at,duration,kind,stage,count,reserved=struct.unpack_from('<IIIIQIBBBB',data)
            assert boot==100 and rev==self.revisions[stage]
            if kind!=2 and at:assert round(time.monotonic()*1e6)-100000<=at<=round(time.monotonic()*1e6)+5000000,'Event outside device timing window'
            values=[struct.unpack_from('<Bf',data,32+i*5) for i in range(count)]
            self.remote_wires.append(data)
            key=(stage,stream);previous=self.delta_baselines.get(key)
            if reserved:
                assert reserved==1 and self.supports_deltas and kind!=2
                if previous is None or previous[:2]!=(rev,kind):return dict(queued=False,need_full=True)
                assert set(dict(values))<=set(previous[2]);values=list((previous[2]|dict(values)).items())
            if kind!=2:self.delta_baselines[key]=(rev,kind,dict(values))
            self.remote_events.append(dict(stream=stream,sequence=seq,at=at,duration=duration,kind=kind,stage=stage,values=values,wire_count=count,wire_bytes=len(data),delta=reserved))
            for i,value in values:self.values[stage][i]=value
            return dict(queued=True)
        result=super().operation(op,data)
        if op=='HELLO' and self.supports_deltas:result['control_deltas']=1
        if op=='INSTALL':
            stage=int(self.stage_master);self.graphs[stage]=decode(self.stage[:self.graph_bytes]);self.values[stage]=self.graphs[stage]['controls'].copy();self.revisions[stage]+=1;self.running[stage]=not bool(self.meta[157]&1)
        return result

class IDETests(unittest.TestCase):
    def test_function_play_is_autonomous_and_definition_lifecycle_is_preserved(self):
        m=ControlModule(71)
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);app.pairings=Pairings(folder/'pairs.json');app.pairings.save(m.pairing())
            bridge=Bridge(app,'test-autonomous-functions',config=folder/'connection.json')
            bridge.hub.refresh=lambda:[dict(m.info(),paired=True,online=True)]
            bridge.hub.rows=bridge.hub.refresh();original=bridge.hub.dispatch;snapshots={};operations=[]
            operation=m.operation
            def observe(op,data):operations.append(op);return operation(op,data)
            m.operation=observe
            def dispatch(action,p,*args):
                if action=='snapshot':
                    stage=int(p.get('stage')=='fx')
                    snapshots[p['name']]=dict(flags=m.meta[157],graph=m.graphs[stage],running=m.running[stage],starts=operations.count('START'))
                    return dict(saved=True)
                return original(action,p,*args)
            bridge.hub.dispatch=dispatch
            script=folder/'autonomous-functions.scd'
            script.write_text(r'''
Routine({
    try {
        ESP32.connect(%CONFIG%).wait;
        {arg freq=220;SinOsc.ar(freq,0,0.01)!2}.playESP32(\all,args:[\freq,660]).wait;
        ESP32.request(\snapshot,(name:"function_play")).wait;
        {arg freq=220;SinOsc.ar(freq,0,0.01)!2}.sendESP32(\all).wait;
        ESP32.request(\snapshot,(name:"function_send")).wait;
        SynthDef(\literal,{arg gate=1;Out.ar(0,SinOsc.ar(220,0,0.01)!2)}).playESP32(\all).wait;
        ESP32.request(\snapshot,(name:"literal_play")).wait;
        SynthDef(\literal,{arg gate=1;Out.ar(0,SinOsc.ar(220,0,0.01)!2)}).sendESP32(\all).wait;
        ESP32.request(\snapshot,(name:"literal_send")).wait;
        {arg wet=0.5;In.ar(0,2)*wet}.playESP32(\all,args:[\wet,0.3],stage:\fx).wait;
        ESP32.request(\snapshot,(name:"fx_function_play",stage:\fx)).wait;
        ESP32.disconnect;"PASS: autonomous Function play, persisted args, single start and literal definition lifecycle".postln;0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))))
            try:
                run=subprocess.run([SCLANG,'-l',str(LANGUAGE),'-D',str(script)],capture_output=True,text=True,timeout=40)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                fn=snapshots['function_play'];self.assertEqual(fn['flags']&1,0);self.assertTrue(fn['running']);self.assertEqual(fn['starts'],0)
                names=dict(fn['graph']['names']);self.assertEqual(fn['graph']['controls'][names['freq']],660)
                self.assertEqual(fn['graph']['controls'][names['__esp32_autoplay']],1)
                for key in ('function_send','literal_play','literal_send'):
                    self.assertEqual(snapshots[key]['flags']&1,1,key)
                    self.assertNotIn('__esp32_autoplay',dict(snapshots[key]['graph']['names']))
                self.assertFalse(snapshots['function_send']['running']);self.assertTrue(snapshots['literal_play']['running'])
                self.assertFalse(snapshots['literal_send']['running']);self.assertEqual(snapshots['literal_play']['starts'],1)
                fx=snapshots['fx_function_play'];self.assertEqual(fx['flags']&1,0);self.assertTrue(fx['running'])
                self.assertEqual(fx['starts'],1)  # No second start for either Function.
                self.assertAlmostEqual(fx['graph']['controls'][dict(fx['graph']['names'])['wet']],.3,places=6)
            finally:bridge.server_close();app.close();m.close()

    def test_native_stale_named_and_cached_players_restart_after_clock_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);bridge=Bridge(app,'test-stale-player',config=folder/'connection.json')
            original=bridge.hub.dispatch;events=[]
            def dispatch(action,p,*args):
                if action=='count':return dict(count=len(events))
                if action=='control':
                    if p.get('kind')!='cancel':events.append(p.copy())
                    return dict(queued=True,results=[])
                return original(action,p,*args)
            bridge.hub.dispatch=dispatch
            script=folder/'stale-player.scd'
            script.write_text(r'''
Routine({
    var proxy,player,oldStream,count,makeStale;
    try {
        ESP32.connect(%CONFIG%).wait;
        makeStale={
            var retained=player.slotAt(\stream);
            // Inject the exact native state observed in the long-running IDE:
            // its clock has no scheduled work, but the retained player still
            // has a stream and an older CmdPeriod era.
            player.clock.clear;
            player.slotPut(\stream,retained);
            player.slotPut(\era,CmdPeriod.era-1);
        };
        proxy=Pbindef(\staleESP32,\type,\esp32Set,\module,\all,\freq,440,\dur,0.03).quant_(0);
        player=proxy.playESP32(SystemClock);0.15.wait;
        oldStream=player.event[\esp32Stream];
        makeStale.value;
        if(player.isPlaying.not or:{player.wasStopped.not}){Error("Did not reproduce stale player state").throw};
        count=ESP32.request(\count,()).wait["count"];
        if(proxy.playESP32(SystemClock) !== player){Error("Named proxy replaced its player").throw};
        if(player.event[\esp32Stream]==oldStream){Error("Stale named player did not receive a fresh stream").throw};
        0.15.wait;
        if(ESP32.request(\count,()).wait["count"]<=count){Error("Stale named player did not resume events").throw};
        oldStream=player.event[\esp32Stream];proxy.playESP32(SystemClock);
        if(player.event[\esp32Stream]!=oldStream){Error("Repeated play duplicated a live stream").throw};
        // The same recovery is needed when users keep and replay the player.
        makeStale.value;
        count=ESP32.request(\count,()).wait["count"];player.play;0.15.wait;
        if(player.event[\esp32Stream]==oldStream){Error("Cached player kept its stale stream").throw};
        if(ESP32.request(\count,()).wait["count"]<=count){Error("Cached player did not resume events").throw};
        player.stop;ESP32.disconnect;
        "PASS: stale named and cached ESP32 players restart with fresh streams; live replay stays single".postln;0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))))
            try:
                run=subprocess.run([SCLANG,'-l',str(LANGUAGE),'-D',str(script)],capture_output=True,text=True,timeout=8)
                (ROOT/'build/host/stale-player-native.log').write_text(run.stdout+run.stderr)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.assertNotIn('WARNING:',run.stdout+run.stderr)
                self.assertNotIn('ERROR:',run.stdout+run.stderr)
            finally:bridge.server_close();app.close()

    def test_native_note_deltas_mixed_firmware_and_other_writer(self):
        a,b=ControlModule(41),ControlModule(42);a.supports_deltas=True
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);app.pairings=Pairings(folder/'pairs.json')
            for m in (a,b):app.pairings.save(m.pairing())
            bridge=Bridge(app,'test-control-deltas',config=folder/'connection.json');bridge.hub.alias_path=folder/'aliases.json'
            bridge.hub.rows=[dict(m.info(),paired=True,online=True) for m in (a,b)];bridge.hub.refresh=lambda:bridge.hub.rows
            script=folder/'note-deltas.scd'
            script.write_text(r'''
Routine({
    var player;
    try {
        ESP32.connect(%CONFIG%).wait;
        {arg freq=220,amp=0.1,gate=0,curve=(-4),attack=0.01;
            (SinOsc.ar(freq)*EnvGen.kr(Env.asr(attack,1,0.01,curve),gate)*amp)!2;
        }.sendESP32(\all).wait;
        ESP32.play(\all).wait;ESP32.prepare(\all).wait;
        player=Pbind(\type,\esp32Note,\module,\all,\freq,Pseq([220,330,330,440],1),\amp,0.6,\curve,(-10),\attack,0.01,\dur,0.15).playESP32;
        0.36.wait;ESP32.set(\all,\amp,0.9).wait;
        0.4.wait;ESP32.disconnect;
        "PASS: note deltas preserve other-writer semantics and legacy recipients".postln;0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))))
            try:
                run=subprocess.run([SCLANG,'-l',str(LANGUAGE),'-D',str(script)],capture_output=True,text=True,timeout=12)
                (ROOT/'build/host/control-deltas-native.log').write_text(run.stdout+run.stderr)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertNotIn('WARNING: ESP32',run.stdout)
                notes_a=[e for e in a.remote_events if e['kind']==1];notes_b=[e for e in b.remote_events if e['kind']==1]
                self.assertEqual([e['wire_count'] for e in notes_a],[4,1,0,1]);self.assertEqual([e['wire_count'] for e in notes_b],[4,4,4,4])
                self.assertEqual([e['delta'] for e in notes_a],[0,1,1,1]);self.assertTrue(all(e['delta']==0 for e in notes_b))
                self.assertEqual([dict(e['values']) for e in notes_a],[dict(e['values']) for e in notes_b])
                amp=dict(a.graphs[0]['names'])['amp'];self.assertAlmostEqual(a.values[0][amp],.6,places=6)
                report=dict(passed=True,native_supercollider=True,hardware=False,note_events=4,optimized_payload_bytes=sum(e['wire_bytes'] for e in notes_a),legacy_payload_bytes=sum(e['wire_bytes'] for e in notes_b),same_note_retriggers_preserved=True,interleaved_set_restored=True,mixed_firmware_fallback=True)
                (ROOT/'evidence/control-deltas-host.json').write_text(json.dumps(report,indent=2)+'\n')
            finally:bridge.server_close();app.close();a.close();b.close()

    def test_delta_baseline_recovery_and_uncertain_ack(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            app=Studio(SCLANG);bridge=Bridge(app,'test-delta-miss',config=Path(folder)/'connection.json')
            info=dict(boot=1,revision=1,offset_us=0,_synced=time.monotonic(),controls=[dict(name='freq',index=0,count=1,writable=True)])
            node=SimpleNamespace(row=dict(device_id='node'),lock=threading.RLock(),schemas={0:info},device=Mock())
            node.device.hello.return_value=dict(control_deltas=1);node.device.request.return_value=dict(queued=True)
            bridge.hub.resolve=lambda *args:[node.row];bridge.hub.node=lambda row:node
            args=dict(kind='set',target='node',stream=42,args=['freq',440])
            try:
                self.assertTrue(bridge.hub.control(args,'client',1)['queued'])
                node.device.request.reset_mock();node.device.request.side_effect=[dict(queued=False,need_full=True),dict(queued=True)]
                self.assertTrue(bridge.hub.control(args,'client',2)['queued']);calls=node.device.request.call_args_list
                self.assertEqual(len(calls),2);delta,full=[c.args[1] for c in calls]
                self.assertEqual(delta[:30],full[:30]);self.assertEqual(delta[30:32],b'\x00\x01');self.assertEqual(full[30:32],b'\x01\x00')
                node.device.request.reset_mock();node.device.request.side_effect=TimeoutError('unknown acknowledgement')
                self.assertFalse(bridge.hub.control(args,'client',3)['queued']);self.assertEqual(node.device.request.call_count,1);self.assertFalse(node.deltas.entries)
                node.device.hello.return_value={};bridge.hub.delta_mode(node,dict(info,boot=2));self.assertFalse(node.delta_enabled)
                node.device.hello.return_value=dict(control_deltas=1);bridge.hub.delta_mode(node,dict(info,boot=3));self.assertTrue(node.delta_enabled)
            finally:bridge.server_close();app.close()

    def test_native_unavailable_bridge_returns_failed_job_and_can_reconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);bridge=Bridge(app,'test-unavailable',config=folder/'connection.json')
            with socket.socket() as unavailable:
                unavailable.bind(('127.0.0.1',0));port=unavailable.getsockname()[1]
            dead=folder/'unavailable.json';dead.write_text(json.dumps(dict(host='127.0.0.1',port=port,token='test-unavailable')))
            script=folder/'unavailable.scd'
            script.write_text(r'''
Routine({
    var failed=false;
    try {
        try {ESP32.connect(%DEAD%).onError({failed=true}).wait}{|error|nil};
        if(failed.not){Error("Unavailable connect did not fail its job").throw};
        failed=false;
        try {ESP32.module(\all,\volume,0.5).onError({failed=true}).wait}{|error|nil};
        if(failed.not){Error("Automatic connection did not fail its job").throw};
        ESP32.connect(%CONFIG%).wait;ESP32.disconnect;
        "PASS: unavailable bridge fails jobs cleanly; reconnect works".postln;0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))).replace('%DEAD%',json.dumps(str(dead))))
            try:
                run=subprocess.run([SCLANG,'-l',str(LANGUAGE),'-D',str(script)],capture_output=True,text=True,timeout=8)
                (ROOT/'build/host/unavailable-native.log').write_text(run.stdout+run.stderr)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.assertNotIn('PrimitiveFailedError',run.stdout+run.stderr);self.assertNotIn('WARNING: ESP32:',run.stdout)
            finally:bridge.server_close();app.close()

    def test_native_send_failure_stops_cleanly_and_old_close_cannot_break_reconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);bridge=Bridge(app,'test-send-failure',config=folder/'connection.json');original=bridge.hub.dispatch
            bridge.hub.dispatch=lambda action,*args:dict(queued=True) if action=='control' else original(action,*args)
            helpers=folder/'classes';helpers.mkdir()
            (helpers/'ESP32BrokenLink.sc').write_text('ESP32BrokenLink { isConnected { ^true } sendMsg { |... args| Error("simulated transport failure").throw } disconnect { ^this } }\n')
            language=folder/'language.yaml';config=json.loads(LANGUAGE.read_text());config['includePaths'].append(str(helpers));language.write_text(json.dumps(config))
            script=folder/'send-failure.scd'
            script.write_text(r'''
Routine({
    var old,vars,index,player;
    try {
        ESP32.connect(%CONFIG%).wait;
        vars=thisProcess.instVarAt(0);index=ESP32.classVarIndex+ESP32.classVarNames.indexOf(\address);old=vars[index];
        player=Pbind(\type,\esp32Set,\module,\all,\freq,440,\dur,0.03).playESP32;
        0.08.wait;vars[index]=ESP32BrokenLink.new;
        0.15.wait;
        if(player.isPlaying){Error("Failed send did not stop the pattern").throw};
        if(ESP32.cancel(999).notNil){Error("Cleanup reconnected a dead stream").throw};
        ESP32.connect.wait;
        old.disconnect;
        ESP32.connect.wait;
        // Exercise the original failure specifically inside stop/cancel.
        player=Pbind(\type,\esp32Set,\module,\all,\freq,330,\dur,0.1).playESP32;
        0.05.wait;vars[index]=ESP32BrokenLink.new;player.stop;0.05.wait;
        ESP32.connect.wait;ESP32.disconnect;
        "PASS: failed send and cancellation contained; old close ignored; reconnect works".postln;0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))))
            try:
                run=subprocess.run([SCLANG,'-l',str(language),'-D',str(script)],capture_output=True,text=True,timeout=8)
                (ROOT/'build/host/send-failure-native.log').write_text(run.stdout+run.stderr)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.assertNotIn('ERROR:',run.stdout+run.stderr)
                self.assertEqual(run.stdout.count('WARNING: ESP32 pattern stopped:'),1,run.stdout)
                self.assertNotIn('WARNING: ESP32:',run.stdout)
            finally:bridge.server_close();app.close()

    def test_native_peer_disconnect_stops_once_and_reconnects(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);bridge=Bridge(app,'test-peer-close',config=folder/'connection.json');original=bridge.hub.dispatch
            sockets=[];process=bridge.process_request;closed=threading.Event();received=[]
            def accept(connection,address):sockets.append(connection);process(connection,address)
            bridge.process_request=accept
            def dispatch(action,p,*args):
                if action=='control':
                    received.append(p.get('kind'))
                    if len(received)==3 and not closed.is_set():
                        closed.set();sockets[0].shutdown(socket.SHUT_RDWR);raise OSError('simulated uploader disconnect')
                    return dict(queued=True)
                return original(action,p,*args)
            bridge.hub.dispatch=dispatch
            script=folder/'peer-close.scd'
            script.write_text(r'''
Routine({
    var player,until;
    try {
        ESP32.connect(%CONFIG%).wait;
        player=Pbind(\type,\esp32Set,\module,\all,\freq,440,\dur,0.03).playESP32;
        until=Main.elapsedTime+11;
        while({player.isPlaying and:{Main.elapsedTime<until}},{0.05.wait});
        if(player.isPlaying){Error("Disconnected pattern is still running").throw};
        ESP32.connect.wait;ESP32.connect.wait;ESP32.disconnect;
        "PASS: peer disconnect stops once and reconnects".postln;0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))))
            try:
                run=subprocess.run([SCLANG,'-l',str(LANGUAGE),'-D',str(script)],capture_output=True,text=True,timeout=15)
                (ROOT/'build/host/peer-close-native.log').write_text(run.stdout+run.stderr)
                self.assertTrue(closed.is_set());self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.assertNotIn('PrimitiveFailedError',run.stdout+run.stderr);self.assertNotIn('OutOfContextReturn',run.stdout+run.stderr)
                self.assertEqual(run.stdout.count('WARNING: ESP32 pattern stopped:'),1,run.stdout)
            finally:bridge.server_close();app.close()

    def test_module_volume_validation_and_partial_failure(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        hub=Hub(SimpleNamespace(pairings=Mock()))
        node=SimpleNamespace(lock=threading.RLock(),device=Mock())
        hub.resolve=Mock(return_value=[dict(device_id='a'),dict(device_id='b')]);hub.node=Mock(return_value=node)
        try:
            for args in (["volume",-1],["volume",1.01],["volume",True],["volume",float('nan')],["volume",float('inf')],["volume",[.5]],["volume","0.5"],["volume"],["volume",.2,"volume",.3],["freq",440]):
                with self.subTest(args=args),self.assertRaises(ValueError):hub.meta(dict(target='all',args=args))
            hub.node.assert_not_called()
            node.device.request.side_effect=[dict(percent=50),TimeoutError('offline')]
            result=hub.meta(dict(target='all',args=['volume',.5]));self.assertFalse(result['verified'])
            self.assertEqual(sum(r['verified'] for r in result['results']),1)
            node.device.request.side_effect=None;node.device.request.return_value=dict(percent=99)
            self.assertFalse(hub.meta(dict(target='all',args=['volume',.5]))['verified'])
        finally:hub.close()

    def test_module_commands_keep_receive_order(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Studio(SCLANG);bridge=Bridge(app,'test-module-order',config=Path(folder)/'connection.json');order=[]
            def dispatch(action,p,source,graph,client,sequence):
                if sequence==1:time.sleep(.15)
                order.append(sequence);return dict(verified=True)
            bridge.hub.dispatch=dispatch
            try:
                with socket.create_connection(bridge.server_address,timeout=2) as connection:
                    for seq in range(1,5):
                        wire=osc_message('/esp32/request',bridge.token,'module-client',seq,'meta',json.dumps(dict(target='all',args=['volume',seq/10])),b'\x01',b'\x01')
                        connection.sendall(struct.pack('>I',len(wire))+wire)
                    deadline=time.monotonic()+2
                    while len(order)<4 and time.monotonic()<deadline:time.sleep(.01)
                    self.assertEqual(order,[1,2,3,4])
            finally:bridge.server_close();app.close()

    def test_native_module_volume_unicast_alias_group_and_all(self):
        a,b=ControlModule(31),ControlModule(32)
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);app.pairings=Pairings(folder/'pairs.json')
            for m in (a,b):app.pairings.save(m.pairing())
            bridge=Bridge(app,'test-module-volume',config=folder/'connection.json');bridge.hub.alias_path=folder/'aliases.json'
            bridge.hub.rows=[dict(m.info(),paired=True,online=True) for m in (a,b)]
            script=folder/'module-volume.scd'
            script.write_text(r'''
Routine({
    var report,first,second;
    try {
        ESP32.connect(%CONFIG%).wait;
        if(ESP32.module(%LEFT%).isKindOf(ESP32Target).not){Error("Module handle changed").throw};
        ESP32.alias(\left,%LEFT%).wait;
        report=ESP32.module(\left,\volume,0.255).wait;
        if(report["results"].size!=1 or:{report["results"][0]["device_id"]!=%LEFT%} or:{report["results"][0]["percent"]!=26}){Error("Unicast volume failed").throw};
        ESP32.module([\left,%RIGHT%],\volume,0).wait;
        report=ESP32.module(\all,\volume,0.5).wait;
        if(report["results"].size!=2 or:{report["results"].any{|row|row["percent"]!=50}}){Error("All volume failed").throw};
        first=ESP32.module(\all,\volume,0.1);second=ESP32.module(\all,\volume,1.0);
        first.wait;second.wait;
        ESP32.disconnect;"PASS: native module volume, alias, groups, all and queued order".postln;0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))).replace('%LEFT%',json.dumps(a.device_id)).replace('%RIGHT%',json.dumps(b.device_id)))
            try:
                run=subprocess.run([SCLANG,'-l',str(LANGUAGE),'-D',str(script)],capture_output=True,text=True,timeout=10)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.assertNotIn('WARNING: ESP32',run.stdout)
                self.assertEqual(a.volume_history,[26,0,50,10,100]);self.assertEqual(b.volume_history,[0,50,10,100])
                self.assertTrue(all(op=='VOLUME' for m in (a,b) for op in m.calls))
                report=dict(passed=True,native_supercollider=True,hardware=False,modules=2,alias_group_all=True,per_client_order=True,invalid_settings_rejected_before_sending=True,partial_failure_reported=True,normalized_volume=True,percent_resolution=1)
                (ROOT/'evidence/module-volume-host.json').write_text(json.dumps(report,indent=2)+'\n')
            finally:bridge.server_close();app.close();a.close();b.close()

    def test_osc_bounds_and_argument_types(self):
        wire=osc_message('/esp32/request','token','client',1,'hello','{}','',b'abc')
        self.assertEqual(osc_decode(wire),('/esp32/request',['token','client',1,'hello','{}','',b'abc']))
        with self.assertRaises(ValueError):osc_decode(wire+b'junk')
    def test_control_requests_keep_receive_order(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Studio(SCLANG);app.pairings=Pairings(Path(folder)/'pairs.json')
            bridge=Bridge(app,'test-order-token',config=Path(folder)/'connection.json');order=[]
            def dispatch(action,p,source,graph,client,sequence):
                if sequence==1:time.sleep(.15)
                order.append((p['stream'],sequence));return {'queued':True}
            bridge.hub.dispatch=dispatch
            try:
                with socket.create_connection(bridge.server_address,timeout=2) as connection:
                    for seq in range(1,7):
                        stream=20 if seq<6 else 21
                        wire=osc_message('/esp32/request',bridge.token,'order-client',seq,'control',json.dumps(dict(kind='set',stream=stream)),b'\x01',b'\x01')
                        connection.sendall(struct.pack('>I',len(wire))+wire)
                    deadline=time.monotonic()+2
                    while len(order)<6 and time.monotonic()<deadline:time.sleep(.01)
                    self.assertEqual(len(order),6)
                    self.assertEqual([seq for stream,seq in order if stream==20],[1,2,3,4,5])
                    self.assertLess(order.index((21,6)),order.index((20,1)))
            finally:bridge.server_close();app.close()

    def test_failed_stream_stops_device_submissions_but_can_cancel(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            app=Studio(SCLANG);app.pairings=Pairings(Path(folder)/'pairs.json')
            bridge=Bridge(app,'test-failure-token',config=Path(folder)/'connection.json')
            info=dict(boot=100,revision=1,offset_us=0,_synced=time.monotonic(),controls=[dict(name='freq',index=0,count=1,writable=True)])
            node=SimpleNamespace(row=dict(device_id='esp32-000000000015'),lock=threading.RLock(),schemas={0:info},device=Mock())
            node.device.request.side_effect=[TimeoutError('timed out'),{'queued':True},{'queued':True}]
            bridge.hub.resolve=lambda *args:[node.row];bridge.hub.node=lambda row:node
            args=dict(kind='set',target='all',stream=42,args=['freq',440])
            try:
                self.assertFalse(bridge.hub.control(args,'client',1)['queued'])
                with self.assertRaisesRegex(ValueError,'Pattern delivery stopped'):bridge.hub.control(args,'client',2)
                self.assertEqual(node.device.request.call_count,1)
                self.assertTrue(bridge.hub.control(dict(kind='cancel',stream=42),'client',3)['queued'])
                self.assertEqual(node.device.request.call_args.args[1][28],2)
                self.assertTrue(bridge.hub.control(dict(args,stream=43),'client',4)['queued'])
                with self.assertRaisesRegex(ValueError,'Control deadline missed'):
                    bridge.hub.control(dict(args,stream=44,when=time.monotonic()-.2),'client',5)
                self.assertEqual(node.device.request.call_count,3)
            finally:bridge.server_close();app.close()

    def test_native_failed_run_warns_once_and_stale_reply_cannot_stop_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);app.pairings=Pairings(folder/'pairs.json')
            bridge=Bridge(app,'test-callback-token',config=folder/'connection.json');original=bridge.hub.dispatch
            def dispatch(action,p,source,graph,client,sequence):
                if action=='control':
                    args=dict(zip(p.get('args',[])[::2],p.get('args',[])[1::2]));freq=args.get('freq')
                    if freq in (1,2):
                        time.sleep(.1 if freq==1 else .2)
                        return dict(queued=False,results=[dict(device_id='simulated-node',queued=False,error='simulated link stall')])
                    return dict(queued=True,results=[])
                return original(action,p,source,graph,client,sequence)
            bridge.hub.dispatch=dispatch
            script=folder/'failures.scd'
            script.write_text(r"""
Routine({
    try {
        ESP32.connect(%CONFIG%).wait;
        ~pattern=Pbind(\type,\esp32Set,\module,\all,\freq,1,\dur,0.02).playESP32;
        0.35.wait;
        if(~pattern.isPlaying){Error("Failed run is still playing").throw};
        0.2.wait;
        ~pattern=Pbind(\type,\esp32Set,\module,\all,\freq,Pseq([2]++Array.fill(100,3),1),\dur,0.02).playESP32;
        0.04.wait;~pattern.stop;~pattern.play;
        0.35.wait;
        if(~pattern.isPlaying.not){Error("Stale error stopped the replay").throw};
        ~pattern.stop;0.2.wait;
        ESP32.connect.wait;ESP32.disconnect;
        "PASS: one failure warning; cancelled and previous-run replies ignored".postln;0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
""".replace('%CONFIG%',json.dumps(str(folder/'connection.json'))))
            try:
                run=subprocess.run([SCLANG,'-l',str(LANGUAGE),'-D',str(script)],capture_output=True,text=True,timeout=8)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.assertEqual(run.stdout.count('WARNING: ESP32 pattern stopped:'),1,run.stdout)
                self.assertIn('simulated-node: simulated link stall',run.stdout)
                self.assertNotIn('request timed out',run.stdout)
            finally:bridge.server_close();app.close()

    def test_native_connection_survives_cmd_period(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);app.pairings=Pairings(folder/'pairs.json')
            bridge=Bridge(app,'test-private-token',config=folder/'connection.json')
            original_dispatch=bridge.hub.dispatch
            def dispatch(action,*args):
                if action=='stall':time.sleep(10.5);return {'queued':True}
                return original_dispatch(action,*args)
            bridge.hub.dispatch=dispatch
            script=folder/'stop-client.scd'
            script.write_text(r'''
Routine({
    var pending,expired=false;
    try {
        ESP32.connect(%CONFIG%).wait;
        CmdPeriod.run;
        ESP32.connect.wait;
        pending=ESP32.request(\stall,()).onError({ |error|
            if(error != "ESP32 request timed out"){Error(error.asString).throw};expired=true;
        });
        CmdPeriod.run;
        try { pending.wait } { |error|
            if(error.errorString.contains("ESP32 request timed out").not){error.throw};
        };
        if(expired.not){Error("Pending job lost its deadline after CmdPeriod").throw};
        ESP32.connect.wait;
        "PASS: ESP32 connection survives CmdPeriod".postln;
        ESP32.disconnect;0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))))
            try:
                run=subprocess.run([SCLANG,'-l',str(LANGUAGE),'-D',str(script)],capture_output=True,text=True,timeout=16)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.assertIn('PASS: ESP32 connection survives CmdPeriod',run.stdout)
            finally:bridge.server_close();app.close()

    def test_real_supercollider_deploy_defaults_routes_and_pattern_cleanup(self):
        a,b=ControlModule(21),ControlModule(22)
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=Studio(SCLANG);app.pairings=Pairings(folder/'pairs.json')
            for m in (a,b):app.pairings.save(m.pairing())
            bridge=Bridge(app,'test-private-token',config=folder/'connection.json')
            bridge.hub.alias_path=folder/'aliases.json'
            bridge.hub.refresh=lambda:[dict(m.info(),paired=True,online=True) for m in (a,b)]
            # Explicit IDs resolve saved addresses too; all uses this frozen discovery fixture.
            bridge.hub.rows=bridge.hub.refresh()
            original_dispatch=bridge.hub.dispatch
            actions=[]
            def dispatch(*args):
                actions.append(args[0]);return original_dispatch(*args)
            bridge.hub.dispatch=dispatch
            sources=[];graphs=[];wire_sizes=[]
            original_deploy=bridge.hub.deploy
            def capture(p,source,graph):
                sources.append(source);graphs.append(graph)
                (ROOT/'build/host/ide-last-source.scd').write_text(source)
                return original_deploy(p,source,graph)
            bridge.hub.deploy=capture
            script=folder/'client.scd';script.write_text('''
Routine({
    try {
        ESP32.connect(%CONFIG%).wait;
        ESP32.alias(\\left,"%LEFT%").wait;ESP32.alias(\\right,"%RIGHT%").wait;
        ("//"++String.fill(65450,{$x})++"\n{ SinOsc.ar(220,0,0.01)!2 }.play").sendESP32(\\all).wait;

        ~literal=SynthDef(\\Literal,{arg frequency=330;
            var initial=NamedControl.ir(\\initial,3);
            Out.ar(0,SinOsc.ar(frequency*initial,0,0.01)!2);
        });
        File.use(%LITERAL%,"wb",{|file|file.write(~literal.asBytes)});
        ~literal.sendESP32(\\all).wait;
        if(ESP32.info(\\left).wait["results"][0]["active"]){Error("Definition upload started audio").throw};
        ESP32.play(\\left,[\\frequency,220,\\initial,9]).wait;
        if(ESP32.info(\\left).wait["results"][0]["active"].not){Error("Explicit play did not start").throw};
        ESP32.stop(\\left).wait;
        if(ESP32.info(\\left).wait["results"][0]["active"]){Error("Explicit stop left a voice active").throw};
        ~fx=SynthDef(\\LiteralFX,{arg wet=0.3;Out.ar(0,In.ar(0,2)*(1-wet))});
        ~fx.sendESP32(\\left,stage:\\fx).wait;
        if(ESP32.info(\\left,\\fx).wait["results"][0]["active"]){Error("FX definition started").throw};
        ESP32.module(\\left).fx.play([\\wet,0.75]).wait;
        ESP32.module(\\left).fx.set(\\wet,0.5).wait;
        ESP32.module(\\left).fx.stop.wait;
        ~fx.playESP32(\\left,args:[\\wet,0.4],stage:\\fx).wait;
        ESP32.module(\\left).fx.bypass(true).wait;
        ESP32.module(\\left).fx.play([\\wet,0.2]).wait;
        { arg freq=220,dev=20,amp=0.1,gate=0;
            (SinOsc.ar(freq + dev) * amp * EnvGen.kr(Env.asr(0.01,1,0.1),gate)) ! 2;
        }.sendESP32(\\all,args:[\\freq,440.0]).wait;
        ESP32.play(\\all).wait;
        ESP32.set(\\left,\\freq,660.0,\\dev,5.0).wait;
        ESP32.module(\\right).main.set(\\freq,330.0).wait;
        CmdPeriod.run;
        ESP32.scan.wait;
        ~pattern=Pbind(\\type,\\esp32Set,\\module,Pseq([\\left,\\right],inf),\\freq,Pseq([220,330,440],inf),\\dur,0.08).playESP32;
        0.5.wait;~pattern.stop;0.1.wait;~pattern.play;0.15.wait;~pattern.stop;0.1.wait;
        ~pattern=Pbind(\\type,\\esp32Note,\\module,Prand([\\left,\\right],inf),\\midinote,Pseq([60,64,67],inf),\\amp,0.12,\\dur,0.08).playESP32;
        0.5.wait;~pattern.stop;0.1.wait;
        ~proxy=Pbindef(\\espLifecycle,\\type,\\esp32Set,\\module,\\left,\\freq,Pseq([220,330],inf),\\dur,0.04).quant_(0);
        ~pattern=~proxy.playESP32;
        if(~proxy.playESP32 !== ~pattern){Error("Named pattern created a duplicate player").throw};
        0.2.wait;Pbindef(\\espLifecycle,\\dev,7.0);0.3.wait;
        Pbindef(\\espLifecycle,\\dev,nil);0.2.wait;
        if(~pattern.isPlaying.not){Error("Pbindef source edit stopped the player").throw};
        ~proxy.stop;0.1.wait;
        if(~pattern.isPlaying){Error("Pbindef.stop did not stop its ESP32 player").throw};
        ~pattern=~proxy.playESP32;0.15.wait;~proxy.stop;0.1.wait;
        ~finite=Pbind(\\type,\\esp32Note,\\module,\\left,\\freq,Pseq([123],1),\\amp,0.12,\\dur,0.08).playESP32;
        0.2.wait;
        // Exercise five-second events and the periodic clock/schema refresh.
        ~pattern=Pbind(\\type,\\esp32Set,\\module,\\all,\\freq,Prand([220,330,440,660,1000],inf),\\dev,Prand([5.0,10.0,20.0,50.0],inf),\\dur,5).playESP32;
        10.3.wait;CmdPeriod.run;ESP32.scan.wait;0.2.wait;
        ESP32.disconnect;"PASS: native SC Function.sendESP32, saved args, aliases, Pseq/Prand endpoints, set/note events and stop cleanup".postln;
        0.exit;
    } {|error|error.reportError;1.exit};
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))).replace('%LITERAL%',json.dumps(str(folder/'literal.scsyndef'))).replace('%LEFT%',a.device_id).replace('%RIGHT%',b.device_id))
            try:
                def capture_wire(raw):
                    wire_sizes.append(len(raw));return osc_decode(raw)
                with patch('ide_bridge.osc_decode',side_effect=capture_wire):
                    run=subprocess.run([SCLANG,'-l',str(ROOT/'build/host/ide-language.yaml'),'-D',str(script)],capture_output=True,text=True,timeout=25)
                (ROOT/'build/host/ide-native-test.log').write_text(run.stdout+run.stderr)
                self.assertEqual(run.returncode,0,str(actions)+'\n'+run.stdout+run.stderr)
                self.assertNotIn('WARNING: ESP32',run.stdout)
                self.assertLessEqual(max(wire_sizes),65536);self.assertGreater(max(len(s.encode()) for s in sources),65000);self.assertTrue(sources[0].endswith('.play'));self.assertTrue(sources[-1].strip().endswith('}'))
                self.assertEqual(graphs[1],(folder/'literal.scsyndef').read_bytes())
                self.assertEqual(a.blob,b.blob)
                g=decode(a.blob[:a.graph_bytes]);freq=next(i for n,i in g['names'] if n=='freq');self.assertEqual(g['controls'][freq],440.0)
                self.assertTrue(a.remote_events and b.remote_events)
                self.assertTrue(any(e['kind']==1 for m in (a,b) for e in m.remote_events))
                self.assertTrue(any(e['kind']==2 for m in (a,b) for e in m.remote_events))
                finite=next(e for e in a.remote_events if e['kind']==1 and any(v==123 for i,v in e['values']))
                self.assertFalse(any(e['kind']==2 and e['stream']==finite['stream'] for e in a.remote_events))
                # Check the initial unicast before later all-module events may
                # legitimately choose the same frequency on either recipient.
                first_a=next(e for e in a.remote_events if e['stage']==0)
                first_b=next(e for e in b.remote_events if e['stage']==0)
                self.assertTrue(any(v==660 for i,v in first_a['values']))
                self.assertFalse(any(v==660 for i,v in first_b['values']))
                for m in (a,b):
                    for e in m.remote_events:
                        if e['kind']==1:self.assertGreater(e['duration'],0)
                report=dict(passed=True,hardware=False,native_supercollider=True,modules=2,events=[len(m.remote_events) for m in (a,b)],max_native_packet_bytes=max(wire_sizes),largest_source_bytes=max(len(s.encode()) for s in sources),source_preserved=True,literal_synthdef_bytes_preserved=True,definition_upload_inactive=True,explicit_main_fx_instances=True,initial_rate_creation_args=True,cmd_period_recovery=True,pbindef_live_edits=True,named_player_reuse=True,named_stop=True,natural_note_completion=True,long_pattern_interval_seconds=5,details='identical compile-once deployment; saved defaults; alias targeting; Pseq/Prand; note/set; cancellation; CmdPeriod then reuse; five-second all-module pattern')
                (ROOT/'evidence/ide-host.json').write_text(json.dumps(report,indent=2)+'\n')
            finally:bridge.server_close();app.close();a.close();b.close()

if __name__=='__main__':unittest.main(verbosity=2)
