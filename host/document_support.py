#!/usr/bin/env python3
"""Render the support ledger from measured software results and historical graphs."""
import json
import hashlib
from pathlib import Path
from engine_profile import ROOT
from synthdef_binary import decode

report=json.loads((ROOT/('evidence/fm1-fixed-inventory.json' if (ROOT/'evidence/fm1-fixed-inventory.json').exists() else 'evidence/fm1-inventory.json')).read_text())
reference=json.loads((ROOT/('evidence/fm1-fixed-reference.json' if (ROOT/'evidence/fm1-fixed-reference.json').exists() else 'evidence/fm1-reference.json')).read_text())
assert report['passed'] and reference['passed']
heard={};captured={}
def collect(paths,target):
    for name in paths:
        for typ,rate,refs,outputs,selector in decode((ROOT/f'examples/{name}.scsyndef').read_bytes())['nodes']:
            target.setdefault((typ,None),set()).add(rate)
            if typ in ('UnaryOpUGen','BinaryOpUGen'):target.setdefault((typ,str(selector)),set()).add(rate)
collect(['gated-sine','touch-sine','mac-sine','phase-fm','additive','filtered'],heard)
collect(['master-delay'],captured)
device_path=ROOT/'evidence/fm1-device-smoke.json'
device=json.loads(device_path.read_text()) if device_path.exists() else None
assert device and device.get('passed'),'The current ledger requires the completed FM1 hardware follow-up'
if device and device.get('passed'):
    for result in device['matrices']:
        if not result['numerical']['passed'] or not result.get('diagnostic_graph_hex'):continue
        raw=bytes.fromhex(result['diagnostic_graph_hex'])
        assert hashlib.sha256(raw).hexdigest()==result['active']['graph_sha256']
        for typ,rate,refs,outputs,selector in decode(raw)['nodes']:
            captured.setdefault((typ,None),set()).add(rate)
            if typ in ('UnaryOpUGen','BinaryOpUGen'):captured.setdefault((typ,str(selector)),set()).add(rate)
def rates(values):return ', '.join({0:'ir',1:'kr',2:'ar'}[i] for i in sorted(values))
long_results={}
for filename in ('fm1-extended-device.json','fm1-fixed-edges-device.json'):
    path=ROOT/'evidence'/filename
    if not path.exists():continue
    proof=json.loads(path.read_text())
    if proof.get('status')!='complete':continue
    for result in proof.get('captures',[]):
        if any(int(result['device'][k]) for k in ('faults','nonfinite','guards')):continue
        grade=result['comparison']['comparison']
        for typ,rate in result['type_rates']:
            long_results.setdefault((typ,None),{}).setdefault(rate,set()).add(grade)
        if 'operator_selectors' in result:
            typ='UnaryOpUGen' if 'unary' in result['id'] else 'BinaryOpUGen'
            for selector in result['operator_selectors']:
                long_results.setdefault((typ,str(selector)),{}).setdefault(result['operator_rate'],set()).add(grade)
def board(typ,selector=None):
    key=(typ,selector)
    if key in long_results:
        entries=long_results[key];grades=set().union(*entries.values())
        note='; some statistical' if 'statistical-only' in grades and typ.startswith(('Gendy','Standard','Latoocarfian','Lorenz','Henon','Cusp','FBSine','Crackle')) else ''
        if typ=='Klang' and 'failed' in grades:note='; float drift, PCM ≤1 step'
        return 'Long: '+rates(entries)+note
    if key in heard:return 'Heard: '+rates(heard[key])
    if key in captured:return 'Captured: '+rates(captured[key])
    return 'Untested'
unary=dict(zip([0,5,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,42,43],
    ['neg','abs','ceil','floor','frac','sign','squared','cubed','sqrt','exp','reciprocal','midicps','cpsmidi','midiratio','ratiomidi','dbamp','ampdb','octcps','cpsoct','log','log2','log10','sin','cos','tan','asin','acos','atan','sinh','cosh','tanh','distort','softclip']))
binary=dict(zip([0,1,2,3,4,5,6,7,8,9,10,11,12,13,17,18,19,20,21,22,23,24,25,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46],
    ['+','-','*','div (floor integer division)','/','mod','==','!=','<','>','<=','>=','min','max','lcm','gcd','round','roundUp','trunc (floor quantization)','atan2','hypot','hypotApx','pow (signed)','ring1','ring2','ring3','ring4','difsqr','sumsqr','sqrsum','sqrdif','absdif','thresh','amclip','scaleneg','clip2','excess','fold2','wrap2','firstArg']))
assert set(map(str,unary))==set(report['operators']['UnaryOpUGen'])
assert set(map(str,binary))==set(report['operators']['BinaryOpUGen'])
text='''# UGen and operator support — 31 October 2026

All **154 UGen types, 33 unary operators and 40 binary operators** in the pinned
FM1 engine now have successful computer-side execution coverage. They are no
longer merely inferred from compiled source. The renderer already contained this
set; the new optional ESP32 profile expands upload admission, graph capacities
and synth memory to make it usable.

The initial full-set validation used silent local tests. The user subsequently
authorized flashing and hardware tests, including playback. The FM1 profile is
now installed. Extended captures cover all 154 UGen types, all 258 observed
fixture type/rate pairs, and every unary/binary selector at initial, control and
audio rate. A Gendy3 closing-segment fault was found and fixed. The ledger labels
statistical-only and float-drift results explicitly; numerical support does not
guarantee real-time CPU suitability. See [EXTENDED_TESTS.md](EXTENDED_TESTS.md).
Native execution of C on the computer is not cycle-accurate Xtensa emulation.

## Meaning of the results

- **Software tested:** every row passed finite-output rendering with undefined-
  behaviour, bounds and float-cast sanitizers. The 1,444 pinned fixtures also
  passed SuperCollider 3.14.1 offline comparisons. Some stochastic/chaotic cases
  use the pinned statistical/timing criteria rather than exact waveforms;
  independent state and arithmetic oracles passed separately.
- **In:** absent from those 1,444 fixtures; covered by the embedded master-delay
  graph and three additional 12-second SuperCollider input-bus comparisons.
- **Heard:** occurs at the stated rates in graphs previously played successfully
  on this board. This covers those graph configurations, not every input domain.
- **Captured:** muted numerical captures, including all 73 audio-rate operator
  selectors on the FM1 compatibility image and earlier/current delay evidence.
  The operator graphs cycle through every selector and vary inputs over 280
  cases each; all 107,520 mono samples matched the computer exactly. This does
  not establish all domains/rates or arbitrary graph performance.
- **Long:** 11.89-second guarded hardware traces, including parameter events.
  Statistical cases and Klang drift are labelled; they are not exact waveform
  claims. CPU timing is separate from numerical agreement.
- **Untested:** no board evidence for that particular combination.

`ir` = initial/scalar, `kr` = control, `ar` = audio rate. Rates shown below are
observed in the rendered fixtures/probes, not a promise of every possible rate or
input combination. The pinned loader remains authoritative for valid layouts,
literal parameters, selectors and domains.

## UGen list

| UGen | Software-tested rates | Graphs | Board evidence |
| --- | --- | ---: | --- |
'''
for typ,entry in sorted(report['types'].items()):
    text+=f"| {typ} | {rates(set(entry['rates']) | set(long_results.get((typ,None),{})))} | {len(entry['fixtures'])} | {board(typ)} |\n"
for typ,names,title in [('UnaryOpUGen',unary,'Unary operators'),('BinaryOpUGen',binary,'Binary operators')]:
    text+=f'\n## {title}\n\n| Selector | Operation | Software-tested rates | Board evidence |\n| ---: | --- | --- | --- |\n'
    for selector,name in names.items():
        entry=report['operators'][typ][str(selector)]
        text+=f"| {selector} | {name} | {rates(entry['rates'])} | {board(typ,str(selector))} |\n"
text+='''
## What the firmware accepts

| Profile | Graph capacity | Synth arena | Upload policy | Qualification |
| --- | --- | --- | --- | --- |
| Compact (default) | 24 nodes, 32 signals, 256 references | None | Existing sine family and exact catalog graphs | Earlier graphs have board evidence; current changed source requires renewed qualification |
| FM1 compatibility (optional) | 256 nodes, 512 logical signals, 2,048 references; 192 live audio buffers | 262,144 floats / 1 MiB PSRAM | Entire pinned FM1 type/operator set, subject to loader validation | Expanded capacities and buffer reuse have host evidence; earlier physical captures retain their recorded build identities |

The compact loader accepted 1,443 of the 1,444 original fixtures; the large
`m5_addy` graph needs 125 nodes, 136 signals and 338 input references. Loader
acceptance alone does not grant upload admission. The optional profile restores
the FM1 graph capacities and admits all 1,444 after a test-only live-control
interface is added. Uploaded voices require live `freq`, `amp` and `gate` controls;
the four knobs are optional. The fixture wrapper does not automatically connect
those added controls to the fixture DSP and is not a musical patch converter.

The shared five-second master delay retains a separate 1 MiB arena. The optional
synth arena enables Delay/Comb/Allpass, Pluck, FreeVerb/FreeVerb2/MiVerb,
Gendy and Rings inside voices. Graphs share that voice arena and must fit its
total budget. Graphs and scratch move to PSRAM in this profile; voice state stays
internal. This affects performance. Extended hardware tests comprise 24 thirty-second rounds across the three
example voices, plus 60 patch activations. The fixed-image final maxima were
939 µs for Filtered Tone, 918 µs for Phase FM and 952 µs for Harmonic Mix, without
reported faults or 70%-margin violations. Some Rings and dense operator-bank
graphs exceed real-time budgets; see the separate constructor/live cost table
in [EXTENDED_TESTS.md](EXTENDED_TESTS.md).

Synth memory is cleared in chunks of at most 1,024 floats per block, with a
separate constructor block. A full 1 MiB clear therefore adds roughly 373 ms
before rendering starts, at the requested 44.1 kHz rate. Shorter arenas need
fewer blocks. Release/Panic cancels pending preparation. The tests compare
incremental initialization against ordinary initialization exactly, including
arena guards and the full 1 MiB case. This is a functional bound, not a measured
ESP32 execution-time guarantee.

The full-arena synth subsequently passed its own 280-case board comparison
(within one PCM step), cancellation before construction completed, and normal
incremental start/play/release without reported faults. The calculated 373 ms
startup interval has not been measured with an external audio capture.

`In` is meaningful in an effect role with an input bus; ordinary voices receive
a silent input bus. Custom master-effect uploads and general audio-bus routing
are not added by this profile. LocalBuf/SetBuf remain immutable scale tables
(up to 16 tables, 128 entries each), not general sample recording/playback.
Other FM1 limits remain, including 64 controls, 64 partials, 32 envelope segments
and 64 Gendy points. This is parity with the pinned FM1 DSP subset, not all of
SuperCollider: demand UGens, arbitrary plugins, file/sample playback, unsupported
selectors and unsupported layouts/rates remain rejected.

## Reproduce silently

```sh
make -C upstream/fm1-synthdef/synthdef-engine test
python3 host/test_fm1_parity.py --reference
python3 host/test_fm1_parity.py --fuzz
python3 host/test_fm1_voice.py
python3 host/test_fm1_rejections.py
python3 host/test_master_delay.py
python3 host/test_delay_reference.py
python3 host/document_support.py
```

The comparison uses SuperCollider 3.14.1 non-real-time file rendering. Original
scores remain untouched; cleanup messages are appended after the compared
interval so persistent nodes are destroyed before macOS unloads plugin code.
Upstream commands containing `--device` compile FM1 maths shims on the computer;
they do not connect to a device.

Build the optional firmware without flashing:

```sh
python3 host/prepare.py
SYNTHDEF_BUILD_DIR=build-fm1-compat host/idf.sh -D IDF_TARGET=esp32s3 \\
  -D "SDKCONFIG=$PWD/firmware/build-fm1-compat/sdkconfig" \\
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;$PWD/docs/ui.defaults;$PWD/docs/timing.defaults;$PWD/docs/fm1.defaults" build
python3 host/record_build.py --build-dir build-fm1-compat --output fm1-compat-build.json
```

For an existing build, the SDKCONFIG must actually contain
`CONFIG_SYNTHDEF_FM1_COMPAT=y`; defaults do not override an existing selection.
The build record checks this against the generated profile and records target
structure sizes. Current catalog entries are marked candidates because source
changed; historical hardware qualifications remain in their original evidence.

## Evidence

- [Extended results, Gendy fix, precision grades and CPU costs](EXTENDED_TESTS.md)
- [Fixed-source reference suite](../evidence/fm1-fixed-reference.json)
- [Rings optimization, selected caches, current timing and limits](RINGS_OPTIMIZATION.md)
- [Selected cache target build](../evidence/rings-cache-build.json)
- [Earlier broad-sweep fixed target build](../evidence/fm1-gendy-fixed-build.json)
- [Coverage and all graph results](../evidence/fm1-inventory.json)
- [FM1 hardware matrices and playback/timing follow-up](../evidence/fm1-device-smoke.json)
- [Full synth-arena hardware follow-up](../evidence/fm1-device-synth-memory.json)
- [1,444 SuperCollider comparisons](../evidence/fm1-reference.json)
- [1,445 admission/initialization/lifecycle tests](../evidence/fm1-voice.json)
- [Positive and negative upload-policy checks](../evidence/fm1-admission.json)
- [1,560,000 malformed-input cases](../evidence/fm1-fuzz.json)
- [Original FM1 API and independent oracle output](../evidence/fm1-upstream-tests.log)
- [Three persistent input-bus/delay comparisons](../evidence/delay-host-reference.json)
- [Compact target build](../evidence/fm1-compact-build.json)
- [FM1 compatibility target build](../evidence/fm1-compat-build.json)
- [Pinned FM1 limits and semantics](../upstream/fm1-synthdef/synthdef-engine/README.md)
'''
(ROOT/'docs/UGEN_SUPPORT.md').write_text(text)
print(f"Documented {len(report['types'])} UGens, {len(unary)} unary and {len(binary)} binary operators")
