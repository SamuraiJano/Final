"""Serial baseline/final timing on a deterministic subset of the paired cohort.

Run after other inference/replay jobs finish. This times mapping, not neural
inference, on identical already loaded input arrays; no saved-result cache.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import random
import time

import cv2
from validate_dense_mapping import DEFAULT_OUTPUT,load_module,load_views,sha,stats,write


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--variant',default='final_v2')
    args=parser.parse_args()
    output=args.output.resolve()
    manifest=json.loads((output/'inputs.json').read_text())
    candidates=[r for r in manifest['records'] if len(r['views'])>=40]
    chosen=random.Random(817).sample(candidates,min(5,len(candidates)))
    cv2.setNumThreads(1)
    rows=[]
    modules={}
    settings_by_variant={}
    for variant in ('baseline',args.variant):
        module=load_module(output/variant/'algorithm.py','serial_'+variant)
        settings=replace(module.Settings(**json.loads((output/variant/'settings.json').read_text())),
                         defect_observations_complete=False,grade_partial_maps=False)
        modules[variant]=module
        settings_by_variant[variant]=settings
    for index,record in enumerate(chosen):
        # Alternate order to avoid attributing a changing machine load to one
        # algorithm. No baseline or final result is reused from replay caches.
        order=('baseline',args.variant) if index%2==0 else (args.variant,'baseline')
        for variant in order:
            module=modules[variant]
            settings=settings_by_variant[variant]
            views=load_views(module,output,record)
            start=time.perf_counter()
            try:
                result=module.build_surface_map(views,settings)
                row=dict(status=result.status,coverage=result.observed_surface_pct)
            except module.MappingError as error:
                row=dict(status='mapping_failed',reason=str(error))
            row.update(variant=variant,track_id=record['track_id'],views=len(views),
                       seconds=time.perf_counter()-start)
            rows.append(row)
            print(row,flush=True)
    summary={variant:stats([r['seconds'] for r in rows if r['variant']==variant])
             for variant in ('baseline',args.variant)}
    write(output/'serial_runtime.json',dict(summary=summary,records=rows,seed=817,
          input_manifest_sha256=sha(output/'inputs.json'),
          source_sha256={v:sha(output/v/'algorithm.py') for v in summary},
          method=__doc__,limitations='One mapping pass per selected record; five records, no inference, '
          'CPU timings depend on machine load; alternating pair order mitigates drift. '
          'Not a full application throughput estimate.'))


if __name__=='__main__':
    main()
