"""Diagnostic only: test a depth-branch bound without supplying any rotations.

An adjacent pole axis cannot move farther than the configured rotation-vector
bound. Both depth signs describe the same measured projected ellipse. This
probe changes the sign only when the preferred branch violates that bound and
the other measured branch fits it. It never changes ellipse radii or XY axes.
This probe is not production code and is not a full-cohort result.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from pathlib import Path
import sys
import json
import numpy as np
import cv2
OUTPUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUTPUT.parents[2]))
from validate_dense_mapping import load_module,load_views,sha,write


def main():
    cv2.setNumThreads(1)
    module=load_module(OUTPUT/'final_v4/algorithm.py','branch_probe_algorithm')
    settings=module.Settings(**json.loads((OUTPUT/'final_v4/settings.json').read_text()))
    original=module._oblate_poles
    changes=[]
    def bounded(ellipses,A,B,s,frame_indices=None):
        poles=original(ellipses,A,B,s,frame_indices)
        corrected=[]
        for i,pole in enumerate(poles):
            if corrected and s.pole_pose_method=='projected_trend':
                gap=(frame_indices[i]-frame_indices[i-1] if frame_indices is not None else 1)
                bound=min(np.pi/2,np.deg2rad(np.hypot(s.max_pair_angle_deg,s.transverse_angle_deg))*max(1,gap))
                other=pole.copy();other[2]*=-1
                preferred=np.arccos(np.clip(abs(pole@corrected[-1]),0,1))
                alternate=np.arccos(np.clip(abs(other@corrected[-1]),0,1))
                if preferred>bound and alternate<=bound:
                    changes.append(dict(index=i,preferred_deg=float(np.rad2deg(preferred)),alternate_deg=float(np.rad2deg(alternate))))
                    pole=other
            corrected.append(pole)
        return corrected
    manifest=json.loads((OUTPUT/'inputs.json').read_text())
    record=next(r for r in manifest['records'] if r['track_id']==393)
    views=load_views(module,OUTPUT,record)
    results={}
    for label in ('active','bounded_branch'):
        if label=='bounded_branch':module._oblate_poles=bounded
        try:
            mapped=module.build_surface_map(views,settings)
            results[label]=dict(coverage=mapped.observed_surface_pct,longitude=mapped.observed_longitude_deg,
                measured_rolling=mapped.rotation_coverage_deg,selected_frames=mapped.view_frames,
                selection_diagnostics=mapped.selection_diagnostics)
        except module.MappingError as error:results[label]=dict(error=str(error))
        print(label,{k:v for k,v in results[label].items() if k!='selection_diagnostics'},flush=True)
    write(OUTPUT/'pole_branch_probe.json',dict(track_id=393,results=results,branch_changes=changes,
          algorithm_sha256=sha(OUTPUT/'final_v4/algorithm.py'),probe_sha256=sha(Path(__file__)),
          limitations='Diagnostic one-record geometry branch experiment. No physical truth; no headline success count.'))


if __name__=='__main__':main()
