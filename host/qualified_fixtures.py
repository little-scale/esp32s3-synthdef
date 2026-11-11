"""Additional valid/matching-fault layouts for the selective production paths."""
from test_signal_reuse import graph
from qualified_kernels import SMOOTH_TYPES


def fixtures(folder):
    paths=[];c=lambda i:(-1,i)
    def save(name,nodes,constants):
        path=folder/(name+'.scsyndef');path.write_bytes(graph(name,nodes,constants=constants));paths.append(path)
    for typ in SMOOTH_TYPES:
        for rate in (1,2):
            for source_rate in range(rate+1):
                # The importer requires initial/control smoothing parameters.
                params=range(2)
                if typ in ('LPZ1','HPZ1'):params=(0,)
                for parameter_rate in params:
                    for fault in (False,True) if typ not in ('LPZ1','HPZ1') and parameter_rate==1 else (False,):
                        nodes=[('In',1,[c(0)],3,0),('In',2,[c(0)],2,0)]
                        source=c(1) if source_rate==0 else (0 if source_rate==1 else 1,0)
                        parameter=c(2) if parameter_rate==0 else (0 if parameter_rate==1 else 1,1)
                        refs=[source]+([] if typ in ('LPZ1','HPZ1') else [parameter])
                        nodes.append((typ,rate,refs,1,0));index=2
                        if rate==1:nodes.append(('K2A',2,[(2,0)],1,0));index=3
                        nodes.append(('Out',2,[c(0),(index,0),(index,0)],0,0))
                        name=f'qualified_smooth_{typ}_{rate}_{source_rate}_{parameter_rate}'+('_fault' if fault else '')
                        save(name,nodes,(0,.125,.1))
    for typ in ('DelayN','DelayL','DelayC','CombN','CombL','CombC','AllpassN','AllpassL','AllpassC'):
        for source_rate in range(3):
            for delay_rate in range(3):
                for decay_rate in (0,1) if not typ.startswith('Delay') else (0,):
                    nodes=[('In',1,[c(0)],3,0),('In',2,[c(0)],2,0)]
                    source=c(1) if source_rate==0 else (0 if source_rate==1 else 1,0)
                    delay=c(3) if delay_rate==0 else (0 if delay_rate==1 else 1,1)
                    refs=[source,c(2),delay]
                    if not typ.startswith('Delay'):refs.append(c(4) if decay_rate==0 else (0,2))
                    nodes.extend([(typ,2,refs,1,0),('Out',2,[c(0),(2,0),(2,0)],0,0)])
                    save(f'qualified_delay_{typ}_{source_rate}_{delay_rate}_{decay_rate}',nodes,(0,.125,.05,.025,.2))
    # Several fixed banks sharing an excitation and reused signal storage.
    for rate in range(3):
        nodes=[('In',1,[c(0)],1,0),('In',2,[c(0)],2,0)]
        source=c(1) if rate==0 else (0 if rate==1 else 1,0)
        constants=[0,.125,1];outputs=[]
        for count in (1,5,16,32):
            refs=[source,c(2),c(0),c(2)]
            for k in range(count):
                for value in (110*(k+1),(-1 if k%2 else 1)/(k+1),.1+k*.01):
                    refs.append(c(len(constants)));constants.append(value)
            outputs.append(len(nodes));nodes.append(('Klank',2,refs,1,0))
        for i in outputs:nodes.append(('Out',2,[c(0),(i,0),(i,0)],0,0))
        save(f'qualified_banks_shared_{rate}',nodes,constants)
    # Distinct per-voice .ir values must survive shared scratch and remapping.
    constants=[0,1,220,1760,.01,.1,2];nodes=[('In',2,[c(0)],2,0)];partials=[]
    for _ in range(8):
        refs=[]
        for lo,hi in ((2,3),(4,5),(5,6)):
            refs.append((len(nodes),0));nodes.append(('Rand',0,[c(lo),c(hi)],1,0))
        partials.extend(refs)
    left=len(nodes);nodes.append(('Klang',2,[c(1),c(0),*partials],1,0))
    right=len(nodes);nodes.append(('Klank',2,[(0,0),c(1),c(0),c(1),*partials],1,0))
    nodes.append(('Out',2,[c(0),(left,0),(right,0)],0,0))
    save('qualified_banks_random_initials',nodes,constants)
    return paths
