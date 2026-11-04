"""Bounded musical inputs for per-family, deterministic target profiling."""

def fixtures(suite):
    if suite=='smooth':
        result={}
        for typ in ('Lag2','Lag3','OnePole','OneZero','LPZ1','HPZ1'):
            args='x, time' if typ.startswith('Lag') else 'x, 0.5' if typ.startswith('One') else 'x'
            result[typ]='{ arg time=0.1; var x=SinOsc.ar(220,0,0.01); (Mix.fill(8, { '+typ+'.ar('+args+') })*0.01)!2 }'
        return result
    if suite=='core':
        return {
          'Klang':r'{ var f=Array.fill(16,{Rand(220,4000)}); (Klang.ar(`[f, 0.05!16, 0!16])*0.01)!2 }',
          'Klank':r'{ var f=Array.fill(16,{Rand(220,4000)}); (Klank.ar(`[f, 0.05!16, 0.5!16],Dust.ar(3)*0.01))!2 }',
          'SinOscFB':'{ (SinOscFB.ar(330,0.6)*0.01)!2 }',
          'Blip':'{ (Blip.ar(SinOsc.kr(0.2).range(110,880),8)*0.01)!2 }',
          'Formant':'{ (Formant.ar(110,440,220)*0.01)!2 }',
          'Gendy1':'{ (Gendy1.ar(minfreq:220,maxfreq:880)*0.01)!2 }',
          'Gendy2':'{ (Gendy2.ar(minfreq:220,maxfreq:880)*0.01)!2 }',
          'Gendy3':'{ (Gendy3.ar(freq:330)*0.01)!2 }',
        }
    if suite=='delay':
        result={}
        for typ in ('DelayN','DelayL','DelayC','CombN','CombL','CombC','AllpassN','AllpassL','AllpassC'):
            extra=', 0.6' if not typ.startswith('Delay') else ''
            result[typ]='{ var x=Decay2.kr(Dust.kr(3),0.001,0.03)*WhiteNoise.ar(0.02), t=SinOsc.kr(0.7).range(0.013,0.04); ('+typ+'.ar(x,0.05,t'+extra+')*0.1)!2 }'
        result['MiVerb_modulated']='{ var x=Decay2.kr(Dust.kr(3),0.001,0.03)*WhiteNoise.ar(0.02); MiVerb.ar(x!2,SinOsc.kr(0.1).range(0.5,0.9),0.5,0.1)*0.1 }'
        return result
    raise ValueError('Unknown target profiling suite: '+suite)
