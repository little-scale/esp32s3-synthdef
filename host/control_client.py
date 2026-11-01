"""Named, revision-bound controls over the existing paired device transport."""
import math
import struct
import time

class ControlDeltas:
    """Per-recipient, per-stream float32 baselines, committed only after ACK.

    The node expands a delta into a complete queued event. This is deliberately
    not a cache of the node's live controls: other writers and event timestamps
    may interleave after a packet is accepted.
    """
    def __init__(self):self.entries={}
    @staticmethod
    def key(wire):
        boot,revision,stream=struct.unpack_from('<III',wire)
        return boot,revision,wire[29],stream
    def prepare(self,full,now=None):
        if full[28]==2:return full
        now=time.monotonic() if now is None else now
        previous=self.entries.get(self.key(full))
        records={full[i]:full[i:i+5] for i in range(32,len(full),5)}
        if previous is None or now-previous[0]>=8 or previous[1]!=full[28] or records.keys()!=previous[2].keys():return full
        changed=b''.join(value for index,value in records.items() if value!=previous[2][index])
        if len(changed)==len(full)-32:return full
        return full[:30]+bytes([len(changed)//5,1])+changed
    def confirm(self,full,now=None):
        if full[28]==2:
            stream=struct.unpack_from('<I',full,8)[0]
            self.entries={k:v for k,v in self.entries.items() if k[3]!=stream};return
        now=time.monotonic() if now is None else now
        self.entries={k:v for k,v in self.entries.items() if now-v[0]<120}
        key=self.key(full)
        if key not in self.entries and len(self.entries)>=64:self.entries.pop(min(self.entries,key=lambda k:self.entries[k][0]))
        self.entries[key]=(now,full[28],{full[i]:full[i:i+5] for i in range(32,len(full),5)})
    def clear(self):self.entries.clear()

def pairs(values):
    if isinstance(values,dict):items=list(values.items())
    elif isinstance(values,list) and len(values)%2==0:items=list(zip(values[::2],values[1::2]))
    else:raise ValueError('Arguments must be name/value pairs')
    if len({k for k,v in items})!=len(items):raise ValueError('Duplicate argument name')
    for name,value in items:
        if not isinstance(name,str) or name.startswith('__esp32_'):raise ValueError('Invalid or reserved parameter name')
        for v in value if isinstance(value,list) else [value]:
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>3.402823466e38:raise ValueError('Parameter values must be finite 32-bit numbers')
    return items

def controls(schema,values,live=True):
    definitions={c['name']:c for c in schema['controls']};result=[]
    for name,value in pairs(values):
        if name not in definitions:raise ValueError('Unknown parameter: '+name)
        c=definitions[name];array=value if isinstance(value,list) else [value]
        if len(array)!=c['count']:raise ValueError(f'{name} needs {c["count"]} values')
        if live and not c['writable']:raise ValueError(name+' is initial-rate or reserved; redeploy with args instead')
        for k,v in enumerate(array):result.append((c['index']+k,float(v)))
    if len(result)>64 or len({i for i,v in result})!=len(result):raise ValueError('Overlapping or oversized parameter update')
    return result

def defaults(graph,values,schema):
    """Only change the validated SCgf default table, preserving its original source."""
    updates=controls(schema,values,live=False)
    if not updates:return graph
    if graph[:4]!=b'SCgf' or struct.unpack_from('>ih',graph,4)!=(2,1):raise ValueError('Expected one SynthDef v2')
    at=11+graph[10];constant_count=struct.unpack_from('>i',graph,at)[0];at+=4+4*constant_count
    count=struct.unpack_from('>i',graph,at)[0];at+=4
    result=bytearray(graph)
    for index,value in updates:
        if index>=count:raise ValueError('Parameter index outside graph')
        struct.pack_into('>f',result,at+4*index,value)
    return bytes(result)

def schema(device,stage=0):
    started=time.monotonic();info=device.request('RCINFO',bytes([stage,0]),timeout=2,retries=0);ended=time.monotonic()
    offset=info['now_us']-(started+ended)*500000
    for page in range(1,(info['total']+7)//8):
        extra=device.request('RCINFO',bytes([stage,page]),timeout=2,retries=0)
        if (extra['boot'],extra['revision'])!=(info['boot'],info['revision']):raise RuntimeError('Patch changed while reading its controls')
        info['controls'].extend(extra['controls'])
    for c in info['controls']:c['name']=bytes.fromhex(c.pop('name_hex')).decode('utf8')
    info['offset_us']=offset;info['clock_error_us']=(ended-started)*500000
    return info

def packet(info,stage,stream,sequence,values,kind=0,when=0,sustain=0):
    values=controls(info,values)
    if kind==1:
        gate=next((c for c in info['controls'] if c['name']=='gate' and c['writable'] and c['count']==1),None)
        if stage or gate is None:raise ValueError('Note events need a Main patch with a live gate control')
        if any(i==gate['index'] for i,v in values):raise ValueError('Note events manage gate automatically')
        if not math.isfinite(sustain) or not 0<sustain<=60:raise ValueError('Note sustain must be 0–60 seconds, excluding zero')
    if not math.isfinite(when):raise ValueError('Invalid event time')
    at=max(1,round(when*1000000+info['offset_us'])) if when else 0
    header=struct.pack('<IIIIQIBBBB',info['boot'],info['revision'],stream,sequence,at,round(sustain*1000000),kind,stage,len(values),0)
    return header+b''.join(struct.pack('<Bf',i,v) for i,v in values)

def instance_packet(info,stage,values):
    """Creation accepts initial-rate controls without changing saved defaults."""
    updates=controls(info,values,live=False)
    return struct.pack('<IIBB',info['boot'],info['revision'],stage,len(updates))+b''.join(struct.pack('<Bf',i,v) for i,v in updates)
