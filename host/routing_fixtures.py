"""Raw legal rate/layout edges for converter/selector candidate comparison."""
from test_signal_reuse import graph


def fixtures(folder):
    c=lambda i:(-1,i)
    paths=[]
    rates={'A2K':(1,),'K2A':(2,),'DC':(0,1,2),'Delay1':(1,2),'Delay2':(1,2),'Select':(0,1,2),'Clip':(1,2),'RandSeed':(0,1,2)}
    constants=(0,.25,.75,-0.0,-.75,12345)
    for kind,output_rates in rates.items():
        for rate in output_rates:
            for arate in range(3 if kind=='A2K' else min(rate,1)+1 if kind=='K2A' else rate+1):
                nodes=[('In',2,[c(0)],2,0),('In',1,[c(0)],3,0)]
                a=c(1) if arate==0 else (1 if arate==1 else 0,0)
                refs=[a]
                if kind in ('Delay1','Delay2'):refs.append((1,1))
                if kind=='Delay2':refs.append(c(3))
                if kind=='RandSeed':refs.append(c(5))
                if kind=='Clip':refs += [(1,0),(0,1) if rate==2 else (1,1)]
                if kind=='Select':refs += [(0,0),(0,1)] if rate==2 else [c(1),c(4)]
                i=len(nodes);nodes.append((kind,rate,refs,1,0))
                if rate!=2:nodes.append(('K2A',2,[(i,0)],1,0));i+=1
                nodes.append(('Out',2,[c(0),(i,0),(i,0)],0,0))
                path=folder/f'Routing_{kind}_{rate}_{arate}.scsyndef'
                path.write_bytes(graph(kind,nodes,constants=constants));paths.append(path)
    for rate in (1,2):
        for arate in range(rate+1):
            constants=(0,1,5,12,2,4,7,9)
            nodes=[('MaxLocalBufs',0,[c(1)],1,0),('LocalBuf',0,[c(1),c(2),(0,0)],1,0),
                   ('SetBuf',0,[(1,0),c(0),c(2),c(0),c(4),c(5),c(6),c(7)],1,0),
                   ('In',2,[c(0)],2,0),('In',1,[c(0)],3,0)]
            source=c(4) if arate==0 else (4 if arate==1 else 3,0)
            i=len(nodes);nodes.append(('DegreeToKey',rate,[(1,0),source,c(3)],1,0))
            if rate!=2:nodes.append(('K2A',2,[(i,0)],1,0));i+=1
            nodes.append(('Out',2,[c(0),(i,0),(i,0)],0,0))
            path=folder/f'Routing_DegreeToKey_{rate}_{arate}.scsyndef'
            path.write_bytes(graph('Scale',nodes,constants=constants));paths.append(path)
    return paths
