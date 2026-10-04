"""Submit a real video through the running application API and retain evidence."""
import argparse
from collections import Counter
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import requests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video',type=Path)
    parser.add_argument('--label',required=True)
    parser.add_argument('--read-timeout-seconds',type=float,default=21600,
                        help='Maximum wait for the full API result (default: six hours).')
    parser.add_argument('--expected-algorithm-sha256',
                        help='Require the completed report to name this frozen algorithm source.')
    args=parser.parse_args()
    if args.read_timeout_seconds <= 0:
        parser.error('--read-timeout-seconds must be positive')
    output=Path(__file__).resolve().parent/'diagnostics'/'api-runs'/args.label
    output.mkdir(parents=True,exist_ok=False)
    video=args.video.resolve()
    with video.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    run_id=uuid4().hex
    metadata={'started_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'video':str(video),'video_sha256':digest,'analysis_id':run_id,
              'api_url':'http://127.0.0.1:8000',
              'connect_timeout_seconds':30,'read_timeout_seconds':args.read_timeout_seconds,
              'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'expected_algorithm_sha256':args.expected_algorithm_sha256,
              'method':'Full video submitted through POST /api/analyze-video; no track subset filter.',
              'limitations':'No manually labelled fruit identities, rotations or grades; tests pipeline execution, not classification accuracy.'}
    (output/'request.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    health=requests.get('http://127.0.0.1:8000/api/health',timeout=30)
    health.raise_for_status()
    (output/'health.json').write_text(json.dumps(health.json(),indent=2),encoding='utf-8')
    print('API ready. Submitting the complete original video.',flush=True)
    started=time.perf_counter()
    response=None
    try:
        with video.open('rb') as stream:
            response=requests.post('http://127.0.0.1:8000/api/analyze-video',
                                   files={'video':(video.name,stream,'video/mp4')},
                                   headers={'X-Analysis-Id':run_id},
                                   timeout=(30,args.read_timeout_seconds))
        (output/'response.json').write_text(response.text,encoding='utf-8')
        response.raise_for_status()
        result=response.json()
    except requests.RequestException as error:
        failure={**metadata,'status':'incomplete',
                 'failed_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
                 'request_duration_sec':round(time.perf_counter()-started,1),
                 'error_type':type(error).__name__,'error':str(error),
                 'note':'A failed request does not prove that the server stopped. No cancellation was sent.'}
        if response is not None:
            failure['http_status']=response.status_code
        try:
            status=requests.get('http://127.0.0.1:8000/api/analysis/status',timeout=10)
            status.raise_for_status()
            failure['last_api_status']=status.json()
            if failure['last_api_status'].get('state')=='error':
                failure['status']='failed'
        except requests.RequestException as status_error:
            failure['status_error']=str(status_error)
        (output/'failure.json').write_text(json.dumps(failure,indent=2),encoding='utf-8')
        raise
    algorithm_sha256=result.get('metrics',{}).get('algorithm_sha256')
    source_matches=(not args.expected_algorithm_sha256 or
                    algorithm_sha256 == args.expected_algorithm_sha256)
    metadata.update(finished_at=datetime.now(timezone(timedelta(hours=2))).isoformat(),
                    request_duration_sec=round(time.perf_counter()-started,1),
                    status=result.get('status','complete') if source_matches else 'source_mismatch',
                    algorithm_sha256=algorithm_sha256,source_matches=source_matches,
                    job_id=result.get('job_id'),fruits=len(result.get('fruits',[])),
                    statuses=dict(Counter(row.get('status') for row in result.get('fruits',[]))),
                    grades=dict(Counter(row.get('grade') or 'ungraded' for row in result.get('fruits',[]))))
    (output/'summary.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(metadata,indent=2),flush=True)
    if not source_matches:
        raise RuntimeError('The API report used a different algorithm source from the expected snapshot.')
    if metadata['status'] != 'complete':
        raise RuntimeError('The API did not return a completed video analysis.')


if __name__=='__main__':main()
