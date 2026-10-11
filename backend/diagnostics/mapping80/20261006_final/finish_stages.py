"""Queue final evidence and full inference after the paired CPU replay completes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

OUTPUT=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[4]
VARIANT='final_v4'
INTEGRATION='integration_commit_guard'
sys.path.insert(0,str(ROOT/'backend'))
from validation_resources import wait_for_memory
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('YOLO_CONFIG_DIR',str(ROOT/'backend/runtime/ultralytics-validation'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(stage,**details):
    payload=dict(stage=stage,**details)
    temporary=OUTPUT/'finish_stage_state.tmp'
    temporary.write_text(json.dumps(payload,indent=2))
    temporary.replace(OUTPUT/'finish_stage_state.json')
    print(payload,flush=True)


def run(*args):
    subprocess.run([sys.executable,'-B',*args],cwd=ROOT,check=True)


def main():
    report_path=OUTPUT/VARIANT/'report.json'
    state('waiting_for_complete_paired_replay')
    while not report_path.exists():
        time.sleep(10)
    report=json.loads(report_path.read_text())
    tests=json.loads((OUTPUT/'tests_final_v4.json').read_text())
    assert len(report['records'])==556
    assert report['algorithm_sha256']==sha(ROOT/'backend/algorithm.py')
    assert report['input_manifest_sha256']==sha(OUTPUT/'inputs.json')
    assert tests['passed'] and tests['tests']==202
    for name,digest in tests['source_sha256'].items():
        assert sha(ROOT/name)==digest
    state('writing_complete_paired_comparison')
    run('backend/validate_dense_mapping.py','compare','--variants','baseline',VARIANT)
    destination=OUTPUT/INTEGRATION
    assert not destination.exists(),'Full integration label already exists; preserve it and use a new label.'
    state('waiting_for_memory_before_full_inference',integration=INTEGRATION)
    wait_for_memory(OUTPUT/'resource_status.json',physical_gib=8,commit_gib=12,disk_gib=2,
                    context='before complete original-video inference')
    state('starting_complete_original_video_integration')
    with (OUTPUT/(INTEGRATION+'_runtime.log')).open('w') as log, (OUTPUT/(INTEGRATION+'_stderr.log')).open('w') as error:
        process=subprocess.Popen([sys.executable,'-B','backend/validate_dense_pipeline.py',
            '--output',str(destination),'--full-video'],cwd=ROOT,stdout=log,stderr=error,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        state('complete_original_video_integration_running',pid=process.pid)
        result=process.wait()
    assert result==0,'Full production integration failed; see its preserved error and failure report.'
    integration=json.loads((destination/'summary.json').read_text())
    assert integration['passed'] and integration['frames']==795 and integration['full_original_video']
    state('serial_runtime_benchmark')
    wait_for_memory(OUTPUT/'resource_status.json',commit_gib=4,context='before serial mapping benchmark')
    run('backend/benchmark_dense_runtime.py','--variant',VARIANT)
    state('all_queued_validation_stages_passed')


if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        state('failed',error=repr(error))
        raise
