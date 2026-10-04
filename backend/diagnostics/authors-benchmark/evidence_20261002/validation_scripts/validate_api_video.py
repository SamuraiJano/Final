"""Submit a real video through the running application API and retain evidence."""
import argparse
from collections import Counter
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import requests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video',type=Path)
    parser.add_argument('--label',required=True)
    args=parser.parse_args()
    output=Path(__file__).resolve().parent/'diagnostics'/'api-runs'/args.label
    output.mkdir(parents=True,exist_ok=False)
    video=args.video.resolve()
    with video.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    run_id=uuid4().hex
    metadata={'started_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
              'video':str(video),'video_sha256':digest,'analysis_id':run_id,
              'method':'Full video submitted through POST /api/analyze-video; no track subset filter.',
              'limitations':'No manually labelled fruit identities, rotations or grades; tests pipeline execution, not classification accuracy.'}
    (output/'request.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    health=requests.get('http://127.0.0.1:8000/api/health',timeout=30)
    health.raise_for_status()
    print('API ready. Submitting the complete original video.',flush=True)
    with video.open('rb') as stream:
        response=requests.post('http://127.0.0.1:8000/api/analyze-video',
                               files={'video':(video.name,stream,'video/mp4')},
                               headers={'X-Analysis-Id':run_id},timeout=7200)
    (output/'response.json').write_text(response.text,encoding='utf-8')
    response.raise_for_status()
    result=response.json()
    metadata.update(finished_at=datetime.now(timezone(timedelta(hours=2))).isoformat(),
                    job_id=result.get('job_id'),fruits=len(result.get('fruits',[])),
                    statuses=dict(Counter(row.get('status') for row in result.get('fruits',[]))),
                    grades=dict(Counter(row.get('grade') or 'ungraded' for row in result.get('fruits',[]))))
    (output/'summary.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(metadata,indent=2),flush=True)


if __name__=='__main__':main()
