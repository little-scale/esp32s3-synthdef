#!/usr/bin/env python3
"""Audit the computer-only selective update; no device access or flashing."""
import hashlib
import json
import re
from pathlib import Path
from patches import ROOT


def main():
    evidence=ROOT/'evidence'
    native=json.loads((evidence/'qualified-kernels-host.json').read_text())
    assert native['passed'] and native['baseline_compiled_sources_identical']
    assert not native['hardware'] and not native['device_access'] and not native['audio_playback']
    for name,digest in native['source_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    for path,key in [('host/dsp_core.py','candidate_core_source_sha256'),('host/dsp_candidates.py','candidate_source_sha256')]:
        assert native['target_profile'][key]==hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    samples=native['inventory']['samples']+native['four_rate_edges']['samples']
    for row in native['experimental_composition'].values():assert row['passed'];samples+=row['samples']
    interleaved=native['interleaved_shared_scratch'];assert interleaved['canaries'] and interleaved['alternate_signal_mapping'] and interleaved['restart_one_voice']
    stack=json.loads((evidence/'qualified-kernels-stack.json').read_text())
    assert not stack['hardware']
    assert stack['render_sha256']==native['target_profile']['target_render_sha256']
    builds={}
    build_id=re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
    for board,old in [('xiao','dsp-seeded-xiao-default-build.json'),('amoled','dsp-seeded-amoled-build.json')]:
        new=json.loads((evidence/f'qualified-kernels-{board}-build.json').read_text())
        previous=json.loads((evidence/old).read_text())
        profile=new['engine_profile'];selected=profile['qualified_kernels']
        assert new['build_id']==build_id
        assert profile==native['target_profile'], 'Native and board renderers differ'
        assert profile['qualified_kernels_source_sha256']==hashlib.sha256((ROOT/'host/qualified_kernels.py').read_bytes()).hexdigest()
        assert selected['enabled'] and selected['smoothing'] and selected['partial_banks']
        assert set(selected['input_binding'])=={'delay_render','render_miverb'}
        assert not any(profile['candidate_kernels'].values())
        assert new['target_structure_sizes']==previous['target_structure_sizes']
        builds[board]=dict(record=f'evidence/qualified-kernels-{board}-build.json',
             app_bytes=new['app_bytes'],added_app_bytes=new['app_bytes']-previous['app_bytes'],
             build_id=new['build_id'],target_structure_sizes=new['target_structure_sizes'])
    rollback=json.loads((evidence/'qualified-kernels-xiao-rollback-build.json').read_text())
    assert not rollback['engine_profile']['qualified_kernels']['enabled']
    assert not any(rollback['engine_profile']['candidate_kernels'].values())
    assert rollback['build_id']==build_id
    diagnostics={}
    for mode in ('reference','qualified'):
        result=json.loads((ROOT/f'build/host/seeded-profile-test/{mode}/result.json').read_text())
        assert result['passed'] and not result['hardware']
        diagnostics[mode]=result
    sources=['host/qualified_kernels.py','host/qualified_fixtures.py','host/test_qualified_kernels.py',
             'host/test_qualified_selection.py','host/engine_profile.py','host/dsp_binding.py',
             'host/record_build.py','host/test_seeded_profile.py','host/run_dsp_qa.py','host/test_run_dsp_qa.py',
             'firmware/main/ugen_profile.c','firmware/main/dsp_qa.c','tests/dsp_kernels_test.c',
             'tests/signal_reuse_test.c','firmware/components/synthdef_engine/CMakeLists.txt']
    report=dict(passed=True,date='2026-11-04',hardware=False,device_access=False,firmware_flashed=False,
        status='Prepared selective board-build defaults; combined-image hardware validation pending',
        baseline_commit=native['baseline_commit'],compared_output_samples=samples,
        interleaved_output_samples=interleaved['output_samples'],interleaved_graphs=interleaved['graphs'],
        comparison_record='evidence/qualified-kernels-host.json',
        diagnostic_mode_tests=diagnostics,
        earlier_individual_hardware_record='evidence/dsp-seeded-xiao-summary.json',
        earlier_measurements_apply_to_combined_image=False,
        paths=dict(smoothing=['Lag2','Lag3','OnePole','OneZero','LPZ1','HPZ1'],
                   partial_banks=['Klang','Klank'],input_binding=['DelayN','DelayL','DelayC','CombN','CombL','CombC','AllpassN','AllpassL','AllpassC','MiVerb']),
        experimental_flags_enabled=False,builds=builds,
        rollback='SYNTHDEF_QUALIFIED_KERNELS=OFF; candidate flags remain none',
        rollback_cross_build='evidence/qualified-kernels-xiao-rollback-build.json',
        stack_record='evidence/qualified-kernels-stack.json',
        scope='Native equality and target compilation only. Individual-function stack frames are not full-call-chain runtime headroom. A same-board combined-image check remains before deployment.',
        source_sha256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources})
    (evidence/'qualified-kernels-review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','hardware','firmware_flashed','compared_output_samples','builds')},indent=2))


if __name__=='__main__':main()
