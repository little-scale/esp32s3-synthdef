"""Compile a declarative SC pattern tree to the portable ESP32 pattern format.

This is a pattern compiler, never an evaluator for source strings or Functions.
The binary contains bounded stream nodes, references and UTF-8 symbols. Nodes
are expanded per occurrence so reusing one SC Pattern creates independent streams.
"""
import hashlib
import math
import struct

MAGIC = b'ESPp'
VERSION = 1
MAX_NODES, MAX_REFS, MAX_SYMBOLS, MAX_DEPTH, MAX_LIST = 256, 2048, 64, 24, 32
HEADER = struct.Struct('<4sHHHHHHdI32s')
NODE = struct.Struct('<BBHHHd')
OPS = ['number','symbol','array','rest','Pseq','Pser','Prand','Pxrand','Pshuf','Pwrand',
       'Pseries','Pgeom','Pwhite','Pexprand','Pbrown','Pgbrown','Pn','Pstutter','Pdup',
       'Pfin','Pdrop','Pkey','Pbind','Pchain','Pbindf','Punop','Pbinop','Ptuple',
       'Pswitch','Pswitch1','Pseed','Ptime','Pbjorklund','Pbjorklund2']
OP = {name:index for index,name in enumerate(OPS)}
ARITIES = {'Pseq':(1,3),'Pser':(1,3),'Prand':(1,2),'Pxrand':(1,2),'Pshuf':(1,2),
    'Pwrand':(2,3),'Pseries':(0,3),'Pgeom':(0,3),'Pwhite':(0,3),'Pexprand':(0,3),
    'Pbrown':(0,4),'Pgbrown':(0,4),'Pn':(1,2),'Pstutter':(2,2),'Pdup':(2,2),
    'Pfin':(2,2),'Pdrop':(2,2),'Pkey':(1,2),'Punop':(2,2),'Pbinop':(3,4),
    'Ptuple':(1,2),'Pswitch':(2,2),'Pswitch1':(2,2),'Pseed':(2,2),'Ptime':(0,1),
    'Pbjorklund':(2,4),'Pbjorklund2':(2,4)}
DEFAULTS = {'Pseq':[None,1,0],'Pser':[None,1,0],'Prand':[None,1],
    'Pxrand':[None,1],'Pshuf':[None,1],'Pwrand':[None,None,1],
    'Pseries':[0,1,math.inf],'Pgeom':[0,1,math.inf],'Pwhite':[0.,1.,math.inf],
    'Pexprand':[.0001,1.,math.inf],'Pbrown':[0.,1.,.125,math.inf],
    'Pgbrown':[0.,1.,.125,math.inf],'Pn':[None,math.inf],'Pkey':[None,math.inf],
    'Pbinop':[None,None,None,None],'Ptuple':[None,1],'Ptime':[math.inf],
    'Pbjorklund':[None,None,math.inf,0],'Pbjorklund2':[None,None,math.inf,0]}
UNARY = ['neg','abs','squared','cubed','sqrt','exp','reciprocal','midicps','cpsmidi',
         'midiratio','ratiomidi','dbamp','ampdb','log','log2','log10','sin','cos','tan',
         'floor','ceil','frac','sign','distort','softclip']
BINARY = ['+','-','*','/','mod','pow','min','max','<','<=','>','>=','==','!=','round','clip2']


class PatternError(ValueError): pass


def compile_pattern(tree, graph_sha256, *, tempo=1., seed=0, autostart=False):
    if type(tempo) not in (int,float) or not math.isfinite(tempo) or not .01<=tempo<=100:
        raise PatternError('Tempo must be finite beats/second in 0.01..100')
    if type(seed) is not int or not 0<=seed<=0xffffffff or type(autostart) is not bool:
        raise PatternError('Invalid pattern seed/autostart')
    try: graph_hash=bytes.fromhex(graph_sha256)
    except (ValueError,TypeError): raise PatternError('A compiled Main graph SHA-256 is required')
    if len(graph_hash)!=32: raise PatternError('Invalid Main graph SHA-256')
    nodes,refs,symbols=[],[],[]
    event_keys=set()
    def symbol(name):
        if not isinstance(name,str) or not name or len(name.encode('utf8'))>63 or '\0' in name:
            raise PatternError('Symbols must be nonempty UTF-8, at most 63 bytes')
        if name not in symbols: symbols.append(name)
        if len(symbols)>MAX_SYMBOLS: raise PatternError('Pattern needs too many symbols')
        return symbols.index(name)
    def emit(value,path='pattern',depth=0):
        if depth>MAX_DEPTH: raise PatternError(path+': nesting exceeds 24')
        if value=={'op':'Infinity','args':[]}: value=math.inf
        args=[];special=0;number=0.
        if type(value) in (int,float,bool):
            number=float(value)
            if math.isnan(number) or number==-math.inf: raise PatternError(path+': invalid numeric value')
            op='number';special=int(type(value) in (int,bool))
        elif isinstance(value,str): op='symbol';special=symbol(value)
        elif value is None: raise PatternError(path+': nil is not a standalone stream value')
        elif isinstance(value,list):
            if not value or len(value)>MAX_LIST: raise PatternError(path+': arrays require 1..32 entries')
            op='array';args=value
        elif isinstance(value,dict) and set(value)=={'op','args'}:
            op=value['op'];args=value['args']
            if op not in OP or not isinstance(args,list): raise PatternError(path+': unsupported pattern '+str(op))
            if op in ('number','symbol','array'): raise PatternError(path+': use literal values/arrays')
            if op=='rest':
                if len(args)!=1: raise PatternError(path+': Rest needs one numeric value')
            elif op=='Pbind':
                if len(args)<2 or len(args)%2: raise PatternError(path+': Pbind needs key/value pairs')
                keys=args[::2]
                if any(not isinstance(k,str) for k in keys) or len(set(keys))!=len(keys):
                    raise PatternError(path+': Pbind needs distinct symbol keys')
                if any(k in ('module','server','instrument','group','out') for k in keys):
                    raise PatternError(path+': standalone events target the local Main definition; choose modules when uploading')
                event_keys.update(keys)
            elif op=='Pchain':
                if not 1<=len(args)<=16: raise PatternError(path+': Pchain requires 1..16 patterns')
            elif op=='Pbindf':
                if len(args)<3 or len(args)%2!=1: raise PatternError(path+': Pbindf needs a pattern and key/value pairs')
                args=[args[0],{'op':'Pbind','args':args[1:]}]
            else:
                lo,hi=ARITIES[op]
                if not lo<=len(args)<=hi: raise PatternError(path+': invalid '+op+' arguments')
                if op in DEFAULTS: args=args+DEFAULTS[op][len(args):]
                if op in ('Punop','Pbinop'):
                    operators=UNARY if op=='Punop' else BINARY
                    if args[0] not in operators: raise PatternError(path+': unsupported operator '+str(args[0]))
                    special=operators.index(args[0]);args=args[1:]
                    if op=='Pbinop':
                        if args[-1] is not None: raise PatternError(path+': binary pattern adverbs are not supported')
                        args=args[:-1]
        else: raise PatternError(path+': functions and runtime objects cannot be uploaded')
        if len(args)>64: raise PatternError(path+': too many arguments')
        children=[emit(v,path+'.'+op+'['+str(i)+']',depth+1) for i,v in enumerate(args)]
        first=len(refs);refs.extend(children)
        index=len(nodes);nodes.append((OP[op],len(children),first,special,0,number))
        if len(nodes)>MAX_NODES or len(refs)>MAX_REFS: raise PatternError('Pattern graph exceeds node/reference limits')
        return index
    root=emit(tree)
    kinds=[]
    for op,argc,first,special,reserved,value in nodes:
        name=OPS[op];children=refs[first:first+argc];kind='value'
        if name=='Pbind':
            if any(kinds[c]=='event' for c in children[1::2]): raise PatternError('Pbind keys need value patterns, not nested event patterns')
            kind='event'
        elif name in ('Pchain','Pbindf'):
            if any(kinds[c]!='event' for c in children): raise PatternError(name+' needs event patterns')
            kind='event'
        elif name in ('Pseq','Pser','Prand','Pxrand','Pshuf','Pwrand','Pswitch','Pswitch1'):
            listnode=nodes[children[0]]
            if OPS[listnode[0]]!='array': raise PatternError(name+' needs a literal list')
            items=refs[listnode[2]:listnode[2]+listnode[1]]
            itemtypes={kinds[c] for c in items}
            if len(itemtypes)>1: raise PatternError('Mixing value and event streams in one list is not supported')
            kind=next(iter(itemtypes))
        elif name in ('Pn','Pfin','Pdrop','Pseed','Pstutter','Pdup'):
            kind=kinds[children[0 if name=='Pn' else 1]]
        kinds.append(kind)
    if kinds[root]!='event':
        raise PatternError('The program root must produce events, normally Pbind')
    raw=HEADER.pack(MAGIC,VERSION,len(nodes),len(refs),len(symbols),root,int(autostart),tempo,seed,graph_hash)
    raw+=b''.join(NODE.pack(*n) for n in nodes)
    raw+=struct.pack('<'+str(len(refs))+'H',*refs)
    raw+=b''.join(bytes([len(s.encode('utf8'))])+s.encode('utf8') for s in symbols)
    return raw,dict(version=VERSION,nodes=len(nodes),references=len(refs),symbols=symbols,
        graph_sha256=graph_sha256,pattern_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
        tempo=tempo,autostart=autostart,supported_patterns=OPS[4:],event_keys=sorted(event_keys))
