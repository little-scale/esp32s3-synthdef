"""Loopback OSC/TCP adapter shared by SC Functions and custom pattern events.

Uploads reuse the Studio compiler and package protocol. Shared USB and paired
HTTP transactions use bounded device scheduling. No unauthenticated LAN OSC
listener is exposed.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import hmac
import json
import math
from pathlib import Path
import secrets
import socketserver
import struct
import threading
import time
from control_client import pairs,packet,schema,instance_packet,ControlDeltas
from network import NetworkDevice,Pairings,discover,DEVICE_ID
from patches import ROOT,Device

MAX_MESSAGE=384*1024

def typed(value):
    """SC's YAML-backed JSON reader returns scalars as strings; retain types explicitly."""
    if value is None:return ['n']
    if isinstance(value,bool):return ['b','1' if value else '0']
    if isinstance(value,int):return ['i',str(value)]
    if isinstance(value,float):return ['f',repr(value)]
    if isinstance(value,str):return ['s',value]
    if isinstance(value,list):return ['a',[typed(v) for v in value]]
    if isinstance(value,dict):return ['o',[[str(k),typed(v)] for k,v in value.items()]]
    raise ValueError('Unsupported bridge result')

def osc_message(path,*args):
    def string(text):
        raw=text.encode('utf8')+b'\0';return raw+b'\0'*(-len(raw)%4)
    tags=',';body=b''
    for value in args:
        if isinstance(value,str):tags+='s';body+=string(value)
        elif isinstance(value,bytes):tags+='b';body+=struct.pack('>I',len(value))+value+b'\0'*(-len(value)%4)
        elif type(value) is int:tags+='i';body+=struct.pack('>i',value)
        else:raise ValueError('Unsupported OSC value')
    return string(path)+string(tags)+body

def osc_decode(data):
    at=0
    def string():
        nonlocal at
        end=data.index(b'\0',at);value=data[at:end].decode('utf8');at=(end+4)&~3;return value
    path=string();tags=string();values=[]
    if not tags.startswith(','):raise ValueError('Missing OSC types')
    for tag in tags[1:]:
        if tag=='s':values.append(string())
        elif tag=='i':values.append(struct.unpack_from('>i',data,at)[0]);at+=4
        elif tag=='b':
            count=struct.unpack_from('>I',data,at)[0];at+=4
            if count>MAX_MESSAGE or at+count>len(data):raise ValueError('Invalid OSC blob')
            values.append(data[at:at+count]);at+=(count+3)&~3
        else:raise ValueError('Unsupported OSC type')
    if at!=len(data):raise ValueError('Trailing OSC data')
    return path,values

class Node:
    def __init__(self,row,pairings):
        self.row=row;self.lock=threading.RLock();self.device=NetworkDevice(row,pairings.get(row['device_id']));self.schemas={};self.deltas=ControlDeltas();self.delta_enabled=None

class SharedUSB(Device):
    """Borrow Studio's serial connection; its device lock owns every transaction."""
    def __init__(self,studio):self.studio=studio;self.owner=studio.device
    def request(self,*args,**kwargs):
        if self.studio.device is not self.owner:raise RuntimeError('USB module disconnected or changed; reconnect and restart the pattern')
        return self.owner.request(*args,**kwargs)
    def close(self):pass  # Only Studio may close its shared connection.

class USBNode:
    def __init__(self,row,studio):
        self.row=row;self.lock=studio.device_lock;self.device=SharedUSB(studio)
        self.schemas={};self.deltas=ControlDeltas();self.delta_enabled=None

class Hub:
    def __init__(self,studio):
        self.studio=studio;self.pairings=studio.pairings;self.lock=threading.RLock()
        self.rows=[];self.nodes={};self.streams={};self.pool=ThreadPoolExecutor(max_workers=8);self.upload_pool=ThreadPoolExecutor(max_workers=8)
        self.alias_path=ROOT/'build/host/private/module-aliases.json'
        self.aliases=json.loads(self.alias_path.read_text()) if self.alias_path.exists() else {}
    def close(self):
        self.upload_pool.shutdown(wait=True,cancel_futures=True);self.pool.shutdown(wait=True,cancel_futures=True)
    def usb_row(self):
        device=getattr(self.studio,'device',None)
        if device is None or isinstance(device,NetworkDevice):return None
        with self.studio.device_lock:return self.usb_row_locked()
    def usb_row_locked(self):
        device=getattr(self.studio,'device',None);info=getattr(self.studio,'device_info',None)
        if device is None or isinstance(device,NetworkDevice) or not isinstance(info,dict):return None
        identity=info.get('device_id','')
        if not DEVICE_ID.fullmatch(identity):return None
        return dict(device_id=identity,device_name=info.get('device_name',info.get('model','USB module')),
            address=self.studio.device_port,port=0,transport='usb',online=True,paired=True)
    def refresh(self):
        self.rows=discover(self.pairings)
        usb=self.usb_row()
        if usb:self.rows=[row for row in self.rows if row['device_id']!=usb['device_id']]+[usb]
        return self.rows
    def resolve(self,target,refresh=False):
        usb=self.usb_row()
        if usb and isinstance(target,str) and self.aliases.get(target,target) in (usb['device_id'],usb['device_name'],usb['address']):return [usb]
        if refresh:self.refresh()
        public=self.pairings.public();paired={r['device_id']:r for r in public}
        rows={r['device_id']:r for r in self.rows if r.get('paired') and r.get('online') and r.get('transport')!='usb'}
        if usb:paired.setdefault(usb['device_id'],usb);rows[usb['device_id']]=usb
        targets=target if isinstance(target,list) else [target];ids=[]
        for value in targets:
            if not isinstance(value,str):raise ValueError('A module target must be an ID, alias, address or list')
            if value=='all':
                if not self.rows:self.refresh();rows={r['device_id']:r for r in self.rows if r.get('paired') and r.get('online')}
                ids.extend(rows);continue
            resolved=self.aliases.get(value,value)
            if resolved in paired:ids.append(resolved);continue
            matches=[i for i,r in paired.items() if resolved in (r['device_name'],r['address'],rows.get(i,r)['device_name'],rows.get(i,r)['address'])]
            if len(matches)!=1:raise ValueError('Unknown or ambiguous module: '+value)
            ids.extend(matches)
        ids=list(dict.fromkeys(ids))
        if not ids:raise ValueError('No paired online recipients')
        if len(ids)>64:raise ValueError('At most 64 modules per operation')
        return [dict(rows[i] if i in rows else paired[i],paired=True) for i in ids]
    def node(self,row):
        with self.lock:
            node=self.nodes.get(row['device_id'])
            usb=row.get('transport')=='usb'
            stale_usb=usb and (not isinstance(node,USBNode) or node.device.owner is not self.studio.device)
            if node is None or stale_usb or isinstance(node,USBNode)!=usb or (node.row['address'],node.row['port'])!=(row['address'],row['port']):
                if usb:
                    with self.studio.device_lock:
                        current=self.usb_row_locked()
                        if current is None or current['device_id']!=row['device_id']:raise RuntimeError('USB module changed before dispatch; select the current module')
                        node=USBNode(row,self.studio)
                else:node=Node(row,self.pairings)
                self.nodes[row['device_id']]=node
            return node
    @staticmethod
    def delta_mode(node,info):
        # Call under node.lock, during preparation rather than after a timed
        # event's deadline check. Metadata-only clients do not need this read.
        if not hasattr(node,'deltas'):node.deltas=ControlDeltas();node.delta_enabled=None
        if getattr(node,'delta_boot',info['boot'])!=info['boot']:node.delta_enabled=None;node.deltas.clear()
        node.delta_boot=info['boot']
        if node.delta_enabled is None:
            hello=node.device.hello();node.delta_enabled=isinstance(hello,dict) and hello.get('control_deltas')==1
    def deploy(self,p,source,graph):
        from studio import Studio,Artifact
        target='master' if p.get('stage','main')=='fx' else 'sound'
        if p.get('stage','main') not in ('main','fx'):raise ValueError('Choose Main or FX')
        rows=self.resolve(p.get('target'),refresh=True)
        definition=p.get('definition',False)
        if type(definition) is not bool:raise ValueError('Invalid definition mode')
        payload=dict(target=target,source=source,args=p.get('args',[]),definition=definition)
        if graph:payload['graph']=base64.b64encode(graph).decode()
        graph,source,info=self.studio.compiler.compile(payload,wait=True)
        artifact=Artifact(graph,source,info)
        if not info['admitted']:raise ValueError(info['admission_error'])
        def send(row):
            worker=None
            try:
                node=self.node(row)
                with node.lock:
                    d=node.device;hello=d.hello()
                    if definition and not hello.get('definition_lifecycle'):raise ValueError('Update device firmware to upload definitions without playing')
                    worker=Studio(str(self.studio.compiler.sclang));worker.device=d;worker.device_info=hello;worker.device_port=row['address'];worker.artifacts['ide']=artifact
                    expected=next(r for r in d.request('FXLIST' if target=='master' else 'LIST') if r['slot']==1)
                    name=p.get('name') or info['name'];name=''.join(c if 32<=ord(c)<127 and c not in '\\"' else '_' for c in name)[:31] or 'Main'
                    result=worker.upload(dict(artifact='ide',slot=1,expected=expected,replace=True,name=name,device_id=row['device_id']))
                    if hello.get('remote_controls') and info.get('continuous') and target=='sound' and not definition:
                        until=time.monotonic()+5
                        while not d.request('RCINFO',bytes([0,0]),timeout=2,retries=0)['prepared']:
                            if time.monotonic()>until:raise RuntimeError('Main saved but constructor is not ready')
                            time.sleep(.01)
                    if hello.get('remote_controls'):
                        cached=schema(d,int(target=='master'));cached['_synced']=time.monotonic();node.schemas[int(target=='master')]=cached
                    return dict(device_id=row['device_id'],device_name=row['device_name'],verified=result['verified'])
            except Exception as e:return dict(device_id=row['device_id'],device_name=row['device_name'],verified=False,error=str(e))
            finally:
                if worker:worker.close()
        results=list(self.upload_pool.map(send,rows))
        with self.lock:self.streams.pop((p.get('_client'),1),None)
        return dict(verified=all(r['verified'] for r in results),results=results,graph_sha256=info['graph_sha256'],source_sha256=info['source_sha256'],controls=info['controls'])
    def instance(self,p,start,client):
        stage=p.get('stage','main')
        if stage not in ('main','fx'):raise ValueError('Choose Main or FX')
        stage=int(stage=='fx');results=[]
        for row in self.resolve(p.get('target')):
            try:
                node=self.node(row)
                with node.lock:
                    if not node.device.hello().get('definition_lifecycle'):raise ValueError('Update firmware for explicit instance control')
                    if stage and start:
                        selected=next(e['slot'] for e in node.device.request('FXLIST') if e.get('selected'))
                        if selected!=1:node.device.request('FXSELECT',b'\x01',retries=0)
                    info=schema(node.device,stage)
                    wire=instance_packet(info,stage,p.get('args',[]) if start else [])
                    node.device.request('START' if start else 'STOP',wire,retries=0)
                    if start:
                        until=time.monotonic()+5
                        while True:
                            status=node.device.request('RCINFO',bytes([stage,0]),timeout=2,retries=0)
                            if not status['active'] or status['prepared']:break
                            if time.monotonic()>until:raise ValueError('Instance constructor is not ready')
                            time.sleep(.01)
                    info=schema(node.device,stage);info['_synced']=time.monotonic();node.schemas[stage]=info
                    results.append(dict(device_id=row['device_id'],verified=True,active=info['active']))
            except Exception as error:results.append(dict(device_id=row['device_id'],verified=False,error=str(error)))
        with self.lock:self.streams.pop((client,1),None)
        return dict(verified=all(r['verified'] for r in results),results=results)
    def control(self,p,client,sequence):
        stage=p.get('stage','main')
        if stage not in ('main','fx'):raise ValueError('Choose Main or FX')
        stage=int(stage=='fx');kind={'set':0,'note':1,'cancel':2}[p['kind']]
        stream=p.get('stream')
        if type(stream) is not int or not 0<stream<2**31:raise ValueError('Invalid stream ID')
        key=(client,stream)
        with self.lock:
            # Idle bookkeeping is bounded, including abandoned/disconnected SC sessions.
            now=time.monotonic()
            self.streams={k:v for k,v in self.streams.items() if now-v['touched']<120}
            entry=self.streams.get(key)
            if entry is None:
                if len(self.streams)>=256:raise ValueError('Too many active control streams')
                used={v['wire'] for v in self.streams.values()};wire=secrets.randbelow(2147483646)+1
                while wire in used:wire=secrets.randbelow(2147483646)+1
                entry=self.streams[key]=dict(bindings={},cancelled=False,failed=None,touched=now,lock=threading.Lock(),all=None,wire=wire)
        with entry['lock']:
            entry['touched']=time.monotonic()
            if stream==1 and kind!=2:entry['bindings']={};entry['all']=None
            if entry['cancelled']:raise ValueError('This pattern was stopped')
            if kind!=2 and entry.get('failed'):raise ValueError('Pattern delivery stopped: '+entry['failed'])
            if kind==2:
                entry['cancelled']=True;bindings=list({node.row['device_id']:(node,stage,info) for node,stage,info in entry['bindings'].values()}.values())
            else:
                target=p.get('target')
                if target=='all':
                    if entry['all'] is None:entry['all']=self.resolve(target)
                    rows=entry['all']
                else:rows=self.resolve(target)
                bindings=[]
                for row in rows:
                    bindkey=(row['device_id'],stage)
                    if bindkey not in entry['bindings']:
                        node=self.node(row)
                        with node.lock:
                            info=node.schemas.get(stage)
                            if stream==1 or info is None or time.monotonic()-info.get('_synced',0)>10:
                                info=schema(node.device,stage);info['_synced']=time.monotonic();node.schemas[stage]=info
                        entry['bindings'][bindkey]=(node,stage,info)
                    bindings.append(entry['bindings'][bindkey])
            if kind!=2:
                for node,s,info in bindings:
                    with node.lock:self.delta_mode(node,info)
                    if time.monotonic()-info.get('_synced',0)>5:
                        with node.lock:new=schema(node.device,s)
                        if (new['boot'],new['revision'])!=(info['boot'],info['revision']):raise ValueError('Patch changed; restart the pattern')
                        info['offset_us']=new['offset_us'];info['_synced']=time.monotonic()
            when=float(p.get('when',0));sustain=float(p.get('sustain',0));values=p.get('args',[])
            if kind!=2 and when and time.monotonic()>when+.1:
                error='Control deadline missed; prepare the modules or increase ESP32.latency before restarting the pattern'
                if stream!=1:entry['failed']=error
                raise ValueError(error)
            # Validate every recipient before enqueueing on any of them.
            prepared=[(node,packet(info,s,entry['wire'],sequence,[] if kind==2 else values,kind,0 if kind==2 else when,sustain)) for node,s,info in bindings]
            def send(item):
                node,full=item
                try:
                    with node.lock:
                        wire=node.deltas.prepare(full) if node.delta_enabled else full
                        result=node.device.request('RCEVENT',wire,timeout=.75,retries=0)
                        if wire[31] and result.get('need_full') is True and result.get('queued') is False:
                            # The device explicitly confirms it did not accept
                            # this event. Restore its baseline once, with the
                            # same timestamp/sequence; never retry an unknown ACK.
                            result=node.device.request('RCEVENT',full,timeout=.75,retries=0)
                        if result.get('queued') is not True:raise ValueError('Module did not accept the control event')
                        if node.delta_enabled:node.deltas.confirm(full)
                    return dict(device_id=node.row['device_id'],queued=True)
                except Exception as e:
                    with node.lock:
                        if hasattr(node,'deltas'):node.deltas.clear()
                    return dict(device_id=node.row['device_id'],queued=False,error=str(e))
            results=list(self.pool.map(send,prepared))
            if stream!=1 and kind!=2 and not all(r['queued'] for r in results):
                entry['failed']='; '.join(r['device_id']+': '+r['error'] for r in results if not r['queued'])
            return dict(queued=all(r['queued'] for r in results),results=results)
    def meta(self,p):
        settings=dict(pairs(p.get('args',[])))
        if set(settings)-{'volume'}:raise ValueError('Supported module setting: volume')
        level=settings.get('volume')
        if settings and (type(level) not in (int,float) or not 0<=level<=1):
            raise ValueError('Module volume must be a number from 0 to 1')
        percent=math.floor(level*100+.5) if settings else None
        rows=self.resolve(p.get('target'))
        def send(row):
            try:
                node=self.node(row)
                with node.lock:result=node.device.request('VOLUME',b'' if percent is None else bytes([percent]),timeout=2,retries=0)
                actual=result.get('percent')
                if type(actual) is not int or not 0<=actual<=100 or (percent is not None and actual!=percent):
                    raise ValueError('Module did not confirm the requested volume')
                return dict(device_id=row['device_id'],verified=True,volume=actual/100,percent=actual)
            except Exception as error:return dict(device_id=row['device_id'],verified=False,error=str(error))
        results=list(self.pool.map(send,rows))
        return dict(verified=all(r['verified'] for r in results),results=results)
    def dispatch(self,action,p,source,graph,client,sequence):
        if action=='hello':
            modules=self.pairings.public();usb=self.usb_row()
            if usb:modules=[r for r in modules if r['device_id']!=usb['device_id']]+[usb]
            return dict(time=time.monotonic(),modules=modules,aliases=self.aliases)
        if action=='scan':return dict(modules=self.refresh())
        if action=='alias':
            name,module=p.get('name'),p.get('module')
            available={r['device_id'] for r in self.pairings.public()};usb=self.usb_row()
            if usb:available.add(usb['device_id'])
            if not isinstance(name,str) or not 1<=len(name.encode('utf8'))<=63 or name=='all' or module not in available:raise ValueError('Alias needs a paired or USB-connected permanent module ID; all is reserved')
            import os
            with self.lock:
                self.aliases[name]=module;self.alias_path.parent.mkdir(parents=True,exist_ok=True)
                temporary=self.alias_path.with_name('.aliases-'+secrets.token_hex(8))
                try:
                    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                    with os.fdopen(fd,'w') as f:json.dump(self.aliases,f,indent=2)
                    os.replace(temporary,self.alias_path)
                finally:temporary.unlink(missing_ok=True)
                return dict(aliases=dict(self.aliases))
        if action=='deploy':return self.deploy(dict(p,_client=client),source,graph)
        if action in ('play','stop'):return self.instance(p,action=='play',client)
        if action=='control':return self.control(p,client,sequence)
        if action=='meta':return self.meta(p)
        if action=='inputs':
            results=[]
            for row in self.resolve(p.get('target')):
                node=self.node(row)
                with node.lock:result=node.device.request('INPUTS',retries=0)
                results.append(dict(device_id=row['device_id'],**result))
            return dict(results=results)
        if action in ('bypass','restart','panic'):
            results=[]
            for row in self.resolve(p.get('target')):
                node=self.node(row)
                try:
                    op,data=('FXLOAD',bytes([0 if p.get('bypassed',True) else 1])) if action=='bypass' else ('LOAD',b'\x01') if action=='restart' else ('PANIC',b'')
                    with node.lock:
                        node.device.request(op,data)
                        if action=='panic':node.schemas.clear()
                        else:node.schemas.pop(1 if action=='bypass' else 0,None)
                    results.append(dict(device_id=row['device_id'],verified=True))
                except Exception as error:results.append(dict(device_id=row['device_id'],verified=False,error=str(error)))
            with self.lock:self.streams.pop((client,1),None)
            return dict(verified=all(r['verified'] for r in results),results=results)
        if action in ('info','prepare'):
            results=[]
            for row in self.resolve(p.get('target')):
                node=self.node(row)
                with node.lock:
                    stage=int(p.get('stage')=='fx');info=schema(node.device,stage);info['_synced']=time.monotonic();node.schemas[stage]=info;self.delta_mode(node,info)
                results.append(dict(device_id=row['device_id'],**(info if action=='info' else dict(boot=info['boot'],revision=info['revision']))))
            return dict(results=results)
        raise ValueError('Unknown SuperCollider action')

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        write_lock=threading.Lock();pending=threading.Semaphore(32);transfers={};control_tails={}
        def exact(count):
            chunks=[]
            while count:
                part=self.request.recv(count)
                if not part:return None
                chunks.append(part);count-=len(part)
            return b''.join(chunks)
        def execute(req,action,p,source,graph,client,previous=None):
            try:
                if previous is not None:previous.result()
                result=self.server.hub.dispatch(action,p,source,graph,client,req);ok=1
            except Exception as e:result=dict(error=str(e));ok=0
            try:
                data=osc_message('/esp32/reply',req,ok,json.dumps(typed(result),ensure_ascii=False,allow_nan=False))
                with write_lock:self.request.sendall(struct.pack('>I',len(data))+data)
            except OSError:pass
            finally:pending.release()
        try:
            while True:
                size=exact(4)
                if not size:return
                count=struct.unpack('>I',size)[0]
                if not 0<count<=MAX_MESSAGE:return
                raw=exact(count)
                if raw is None:return
                path,args=osc_decode(raw)
                if path in ('/esp32/begin','/esp32/chunk','/esp32/commit'):
                    if len(args)<3:return
                    token,client,req=args[:3]
                    if not isinstance(token,str) or not hmac.compare_digest(token,self.server.token):return
                    if not isinstance(client,str) or not 1<=len(client)<=64 or type(req) is not int or req<=0:return
                    key=(client,req)
                    if path=='/esp32/begin':
                        if len(args)!=7 or len(transfers)>=4 or key in transfers:return
                        action,payload,source_size,graph_size=args[3:]
                        if action!='deploy' or type(source_size) is not int or type(graph_size) is not int or not 0<=source_size<=65536 or not 0<=graph_size<=65536:return
                        transfers[key]=(action,payload,source_size,graph_size,bytearray());continue
                    if key not in transfers:return
                    action,payload,source_size,graph_size,buffer=transfers[key]
                    if path=='/esp32/chunk':
                        if len(args)!=5 or args[3]!=len(buffer) or not isinstance(args[4],bytes) or not 0<len(args[4])<=8192 or len(buffer)+len(args[4])>source_size+graph_size:return
                        buffer.extend(args[4]);continue
                    if len(args)!=3 or len(buffer)!=source_size+graph_size:return
                    transfers.pop(key)
                    args=[token,client,req,action,payload,b'\x01'+bytes(buffer[:source_size]),b'\x01'+bytes(buffer[source_size:])];path='/esp32/request'
                if path!='/esp32/request' or len(args)!=7:return
                token,client,req,action,payload,source,graph=args
                if not isinstance(token,str) or not hmac.compare_digest(token,self.server.token):return
                if not isinstance(client,str) or not 1<=len(client)<=64 or type(req) is not int or req<=0:return
                if not isinstance(source,bytes) or not source or source[0]!=1 or not isinstance(graph,bytes) or not graph or graph[0]!=1:return
                source=source[1:].decode('utf8');graph=graph[1:]
                p=json.loads(payload)
                if isinstance(p,dict) and 'lead' in p:p['when']=time.monotonic()+float(p['lead'])
                if not isinstance(p,dict) or not isinstance(source,str) or not isinstance(graph,bytes) or len(source.encode())>65536 or len(graph)>65536:return
                if not pending.acquire(blocking=False):return
                # Configuration replies remain ordered; control/deployment jobs
                # run asynchronously and never block sclang's TempoClock.
                if action in ('hello','alias'):execute(req,action,p,source,graph,client)
                elif action=='meta' or (action=='control' and type(p.get('stream')) is int):
                    # Worker lock acquisition is not FIFO. Preserve SC's event
                    # and cancel order per stream, even after a slow HTTP call.
                    key=(client,'meta' if action=='meta' else p['stream']);previous=control_tails.get(key)
                    control_tails={k:v for k,v in control_tails.items() if not v.done()}
                    control_tails[key]=self.server.jobs.submit(execute,req,action,p,source,graph,client,previous)
                else:self.server.jobs.submit(execute,req,action,p,source,graph,client)
        except (OSError,ValueError,struct.error,TypeError):return

class Bridge(socketserver.ThreadingTCPServer):
    allow_reuse_address=True;daemon_threads=True
    def __init__(self,studio,token,port=0,config=None):
        super().__init__(('127.0.0.1',port),Handler)
        self.token=token;self.hub=Hub(studio);self.jobs=ThreadPoolExecutor(max_workers=8)
        self.config=Path(config) if config else ROOT/'build/host/private/studio-client.json'
        self.config.parent.mkdir(parents=True,exist_ok=True)
        import os
        fd=os.open(self.config,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:json.dump(dict(host='127.0.0.1',port=self.server_address[1],token=token),f)
        self.thread=threading.Thread(target=self.serve_forever,daemon=True);self.thread.start()
    def server_close(self):
        self.shutdown();super().server_close();self.jobs.shutdown(wait=True,cancel_futures=True);self.hub.close()
