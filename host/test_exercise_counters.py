#!/usr/bin/env python3
"""A later patch must not inherit a previous patch's DMA failure grade."""
from exercise_timing import output_counter_delta

before='dma_event_overflow=849 faults=0 clips=0\n'
baseline,delta=output_counter_delta('dma_event_overflow=849 faults=0 clips=0\n',before)
assert baseline['dma_event_overflow']==849 and not any(delta.values())
_,delta=output_counter_delta('dma_event_overflow=850 faults=0 clips=0\n',before)
assert delta['dma_event_overflow']==1
_,delta=output_counter_delta('dma_event_overflow=849 faults=2 clips=0\n',before)
assert delta['faults']==2
print('Output-counter attribution regressions passed')
