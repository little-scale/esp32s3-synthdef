"""Minimal lossless SynthDef v2 reader/writer for software-test graph construction."""
import struct

def decode(data):
    offset=0
    def take(fmt):
        nonlocal offset
        value=struct.unpack_from('>'+fmt,data,offset);offset+=struct.calcsize('>'+fmt)
        return value[0] if len(value)==1 else value
    def string():
        nonlocal offset
        length=take('B');s=data[offset:offset+length].decode();offset+=length;return s
    assert data[:4]==b'SCgf';offset=4
    assert take('i')==2 and take('h')==1
    name=string();constants=[take('f') for _ in range(take('i'))]
    controls=[take('f') for _ in range(take('i'))]
    names=[(string(),take('i')) for _ in range(take('i'))];nodes=[]
    for _ in range(take('i')):
        typ=string();rate=take('B');inputs=take('i');outputs=take('i');special=take('h')
        refs=[take('ii') for _ in range(inputs)];rates=[take('B') for _ in range(outputs)]
        nodes.append((typ,rate,refs,rates,special))
    assert take('h')==0 and offset==len(data)
    return dict(name=name,constants=constants,controls=controls,names=names,nodes=nodes)

def encode(graph):
    def p(fmt,*values):return struct.pack('>'+fmt,*values)
    def string(s):
        b=s.encode();assert len(b)<256;return bytes([len(b)])+b
    data=b'SCgf'+p('ih',2,1)+string(graph['name'])
    for key in ('constants','controls'):
        values=graph[key];data+=p('i',len(values))+b''.join(p('f',v) for v in values)
    data+=p('i',len(graph['names']))+b''.join(string(n)+p('i',i) for n,i in graph['names'])
    data+=p('i',len(graph['nodes']))
    for name,rate,refs,rates,special in graph['nodes']:
        data+=string(name)+p('Biih',rate,len(refs),len(rates),special)
        data+=b''.join(p('ii',*r) for r in refs)+bytes(rates)
    return data+p('h',0)

def voice_interface(data):
    """Add an unused live interface to test admission, retaining source DSP.

    This is a test wrapper, not a patch converter: it does not claim the added
    frequency/amp/gate controls modulate the wrapped fixture's synthesis.
    """
    g=decode(data);index=len(g['controls']);g['controls'] += [440,.5,1]
    g['names']=[('src_'+name,i) for name,i in g['names']]+[(n,index+i) for i,n in enumerate(('freq','amp','gate'))]
    nodes=[]
    for name,rate,refs,rates,special in g['nodes']:
        nodes.append((name,rate,[(n+1 if n>=0 else n,o) for n,o in refs],rates,special))
    g['nodes']=[('Control',1,[],[1,1,1],index)]+nodes
    return encode(g)
