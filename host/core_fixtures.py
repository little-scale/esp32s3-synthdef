"""Raw graph edges for exact oscillator/ramp/bank/cache candidate tests."""
import json
from engine_profile import ROOT
from test_signal_reuse import graph
from synthdef_binary import decode,encode


def fixtures(folder):
    paths=[];c=lambda i:(-1,i)
    def save(name,nodes,constants):
        path=folder/(name+'.scsyndef');path.write_bytes(graph(name,nodes,constants=constants));paths.append(path)
    for typ in ('LFSaw','LFTri','LFPulse'):
        for rate in (1,2):
            for source_rate in range(rate+1):
                for phase in (0,-0.0,.5,3.000001,-5):
                    constants=(0,220,phase,.5)
                    nodes=[('In',2,[c(0)],2,0),('In',1,[c(0)],3,0)]
                    source=c(1) if source_rate==0 else (1 if source_rate==1 else 0,0)
                    args=[source,c(2)]+([(1,1)] if typ=='LFPulse' else [])
                    index=len(nodes);nodes.append((typ,rate,args,1,0))
                    if rate==1:nodes.append(('K2A',2,[(index,0)],1,0));index+=1
                    nodes.append(('Out',2,[c(0),(index,0),(index,0)],0,0))
                    save(f'core_{typ}_{rate}_{source_rate}_{phase}',nodes,constants)
    for typ in ('Line','XLine'):
        for rate in (1,2):
            for duration in (0,.000001,.001,.1,1000):
                for variant,(start,end) in enumerate(((.1,1),(1,.1),(-1,-.1),(-0.0,0),(-1,1))):
                    constants=(0,start,end,duration,2 if variant%2 else 0)
                    nodes=[(typ,rate,[c(1),c(2),c(3),c(4)],1,0)];index=0
                    if rate==1:nodes.append(('K2A',2,[(0,0)],1,0));index=1
                    nodes.append(('Out',2,[c(0),(index,0),(index,0)],0,0))
                    save(f'core_{typ}_{rate}_{duration}_{variant}',nodes,constants)
    for typ in ('Klang','Klank'):
        for size in (1,5,32,64):
            constants=[0,1];nodes=[('In',2,[c(0)],2,0)]
            refs=[c(1),c(0)] if typ=='Klang' else [(0,0),c(1),c(0),c(1)]
            for i in range(size):
                for value in (220*(i+1),1/(i+1),0 if typ=='Klang' else .1+i*.01):
                    refs.append(c(len(constants)));constants.append(value)
            nodes += [(typ,2,refs,1,0),('Out',2,[c(0),(1,0),(1,0)],0,0)]
            save(f'core_{typ}_{size}',nodes,constants)
    inventory=json.loads((ROOT/'evidence/fm1-fixed-inventory.json').read_text())
    for typ in ('Gendy1','Gendy2','Gendy3','Formant','SinOscFB','Blip','BPeakEQ','BLowShelf','BHiShelf','Amplitude','Formlet'):
        options=[ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures'/(name+'.scsyndef') for name in inventory['types'][typ]['fixtures']]
        p=next(p for p in options if any(n[0]==typ and n[1]==2 for n in decode(p.read_bytes())['nodes']))
        g=decode(p.read_bytes());nodes=[]
        for name,rate,refs,rates,special in g['nodes']:
            shifted=[(n+1 if n>=0 else n,o) for n,o in refs]
            if name==typ:
                if typ in ('BPeakEQ','BLowShelf','BHiShelf','Formlet'):
                    for i in (1,2,3):shifted[i]=(0,i-1)
                elif typ=='Amplitude':shifted[1]=(0,1);shifted[2]=(0,2)
                else:
                    for i in range(2 if typ in ('SinOscFB','Blip') else 3 if typ=='Formant' else 4):shifted[i]=(0,i)
            nodes.append((name,rate,shifted,rates,special))
        try:zero=g['constants'].index(0)
        except ValueError:zero=len(g['constants']);g['constants'].append(0)
        g['nodes']=[('In',1,[(-1,zero)],[1,1,1,1],0)]+nodes
        path=folder/f'core_dynamic_{typ}.scsyndef';path.write_bytes(encode(g));paths.append(path)
    return paths
