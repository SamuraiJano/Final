"""Diagnose filter-related rotation bias with known full-turn images.

This compares objectives, not a production replacement. All points and 3D
projections remain the original matcher's. It must not be called field validation.
"""
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT/'diagnostics/algorithm-revision/photometric_objective_20261002'


def main():
    OUTPUT.mkdir(parents=True,exist_ok=False)
    source=ROOT/'diagnostics/algorithm-revision/adjacent_observable_source/algorithm_snapshot.py'
    (OUTPUT/'algorithm_snapshot.py').write_bytes(source.read_bytes())
    (OUTPUT/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    spec=importlib.util.spec_from_file_location('objective_algorithm',source)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    cv2.setNumThreads(1)
    settings=module.Settings(spheroid_type='sphere',rotation_axis='y',rotation_direction=1,
                             image_downsample=1,highpass_sigma=5.,min_pair_angle_deg=.25)
    report=dict(algorithm_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                method='Same native lifted texture points and scalar MAD projection. Compare image-plane '
                       'high-pass against raw green (with 0 or 2 pixel blur). Known truth is scoring only. '
                       'One-axis cost curves do not validate the full two-axis matcher.',cases=[])
    figure,axes=plt.subplots(2,4,figsize=(14,7),layout='constrained')
    for panel,(case,frame) in zip(axes.flat,[("constant_6deg_texture_a",i) for i in (0,13,29,45)]+
                                          [("variable_06_54deg_texture_b",i) for i in (0,1,30,61)]):
        path=ROOT/f'diagnostics/algorithm-revision/full_turn_observable_20261002/{case}_inputs.npz'
        with np.load(path) as data:
            images=data['images'][frame:frame+2];mask=data['mask']
            truth=float(data['angles_deg'][frame+1]-data['angles_deg'][frame])
        views=[module.FruitView(image,mask,frame_index=frame+i) for i,image in enumerate(images)]
        model=module.fit_spheroid(views,settings)
        points,high_values,_=module._relevant(views[0],model,0,settings)
        target_high,target_mask=module._preprocess(views[1],1,5.)
        angles=np.arange(max(0.,truth-1.5),truth+1.501,.025)
        row=dict(case=case,source_frame=frame,truth_increment_deg=truth,
                 input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),curves={})
        source_px=points[:,0]+model.ellipses[0].center[0]
        source_py=points[:,1]+model.ellipses[0].center[1]
        for name in ('highpass','green_sigma0','green_sigma2'):
            if name=='highpass':
                source_values,target_values=high_values,target_high
            else:
                greens=[view.image[:,:,1].astype(np.float32)/255. for view in views]
                if name=='green_sigma2':
                    greens=[cv2.GaussianBlur(green,(0,0),2.) for green in greens]
                source_values=cv2.remap(greens[0],source_px.astype(np.float32).reshape(1,-1),
                                       source_py.astype(np.float32).reshape(1,-1),cv2.INTER_LINEAR)[0]
                target_values=greens[1]
            costs=[module._cost(np.deg2rad([0.,angle,0.]),points,source_values,target_values,
                                target_mask,views[1],model.ellipses[1].center,settings.min_pair_points,
                                model.matrices[1],normalize=False) for angle in angles]
            minimum=float(angles[int(np.argmin(costs))])
            row['curves'][name]=dict(angles_deg=angles.tolist(),mad=costs,
                                    minimum_deg=minimum,error_deg=minimum-truth)
            panel.plot(angles,costs,label=f'{name}: {minimum:.3f}°')
        panel.axvline(truth,color='black',ls='--',label=f'truth {truth:g}°')
        panel.set(title=f'{case[-1]}: source frame {frame}',xlabel='Candidate y rotation (degrees)',ylabel='MAD intensity')
        panel.legend(fontsize=7);panel.grid(alpha=.2)
        report['cases'].append(row)
    (OUTPUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    figure.suptitle('Known-motion diagnostic: image-plane filtering can move the MAD optimum')
    figure.savefig(OUTPUT/'objective_curves.png',dpi=300);figure.savefig(OUTPUT/'objective_curves.pdf')
    plt.close(figure)
    print(json.dumps([dict(case=r['case'],frame=r['source_frame'],truth=r['truth_increment_deg'],
                           minima={k:v['minimum_deg'] for k,v in r['curves'].items()}) for r in report['cases']],indent=2))


if __name__=='__main__':
    main()
