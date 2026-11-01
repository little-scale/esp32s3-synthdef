#!/usr/bin/env python3
"""Saved defaults, parameter shape/rate checks and bounded wire encoding."""
import math,struct,unittest
from studio import Compiler
from control_client import controls,packet,ControlDeltas
from synthdef_binary import decode
SOURCE='''{arg freq=220,amp=0.1; var values=NamedControl.kr(\\values,[1,2]); var initial=NamedControl.ir(\\initial,7); var pulse=NamedControl.tr(\\pulse,0); (SinOsc.ar(freq+values.sum)*amp*initial+pulse)!2}'''
class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler=Compiler('/Applications/SuperCollider.app/Contents/MacOS/sclang')
        cls.graph,cls.source,cls.info=cls.compiler.compile(dict(source=SOURCE,args=['freq',440,'values',[3,4],'initial',9]))
    def test_initial_values_are_saved_in_graph_without_rewriting_source(self):
        self.assertEqual(self.source.decode(),SOURCE);g=decode(self.graph);names=dict(g['names'])
        self.assertEqual(g['controls'][names['freq']],440)
        self.assertEqual(g['controls'][names['values']:names['values']+2],[3,4])
        self.assertEqual(g['controls'][names['initial']],9)
        self.assertTrue(self.info['admitted'])
    def test_shapes_rates_reserved_names_and_nonfinite_rejected(self):
        for values in (['values',1],['initial',3],['__esp32_autoplay',0],['freq',math.nan],['freq',math.inf],['missing',1],['freq',1,'freq',2],['freq',True]):
            with self.subTest(values=values),self.assertRaises(ValueError):controls(self.info,values)
        result=controls(self.info,['values',[5,6],'freq',.1]);self.assertEqual(len(result),3)
        self.assertTrue(next(c for c in self.info['controls'] if c['name']=='pulse')['trigger'])
    def test_packet_is_fixed_width_float32_with_revision_and_timestamp(self):
        schema=dict(self.info,boot=1,revision=2,offset_us=500)
        raw=packet(schema,0,3,4,['freq',440],when=1)
        self.assertEqual(len(raw),37);header=struct.unpack_from('<IIIIQIBBBB',raw)
        self.assertEqual(header[:5],(1,2,3,4,1000500))
        with self.assertRaises(ValueError):packet(schema,1,3,5,[],kind=1,sustain=.1)
    def test_deltas_use_wire_values_and_only_acknowledged_baselines(self):
        info=dict(self.info,boot=1,revision=2,offset_us=0);cache=ControlDeltas()
        a=packet(info,0,3,1,['freq',440,'amp',.6]);self.assertEqual(cache.prepare(a,0),a)
        self.assertEqual(cache.prepare(a,1),a);cache.confirm(a,1)
        b=packet(info,0,3,2,['freq',440.00000001,'amp',.6]);delta=cache.prepare(b,2)
        self.assertEqual(len(delta),32);self.assertEqual(delta[30:32],b'\x00\x01')
        c=packet(info,0,3,3,['freq',660,'amp',.6]);self.assertEqual(len(cache.prepare(c,2)),37)
        self.assertEqual(cache.prepare(c,10),c);cache.clear();self.assertEqual(cache.prepare(c,2),c)
    def test_deltas_isolate_stage_stream_revision_kind_and_field_sets(self):
        info=dict(self.info,boot=1,revision=2,offset_us=0);cache=ControlDeltas()
        a=packet(info,0,3,1,['freq',440,'amp',.6]);cache.confirm(a,0)
        for wire in (packet(info,1,3,2,['freq',440,'amp',.6]),packet(info,0,4,2,['freq',440,'amp',.6]),packet(dict(info,revision=3),0,3,2,['freq',440,'amp',.6]),packet(info,0,3,2,['freq',440])):
            self.assertEqual(cache.prepare(wire,1),wire)
        cancel=packet(info,0,3,2,[],kind=2);self.assertEqual(cache.prepare(cancel,1),cancel);cache.confirm(cancel,1)
        self.assertEqual(cache.prepare(a,2),a)
if __name__=='__main__':unittest.main(verbosity=2)
