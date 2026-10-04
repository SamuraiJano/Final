"""Analytical mapping/area/grade controls, separate from neural-model accuracy."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import algorithm
from algorithm import FruitView, Settings, Spheroid, _ellipse, build_surface_map
from benchmark_authors import ROOT


def sphere_case(defect_width_deg, total_rotation=375., surface_coverage_gate=False):
    size,radius=150,55.
    center=np.array([(size-1)/2]*2)
    yy,xx=np.mgrid[:size,:size]
    X,Y=xx-center[0],yy-center[1]
    visible=X*X+Y*Y<radius*radius
    Z=np.sqrt(np.maximum(radius*radius-X*X-Y*Y,0))
    camera=np.stack((X,Y,Z),axis=-1)
    views,rotations=[],[]
    for k in range(16):
        vector=np.array([0.,np.deg2rad(k*total_rotation/15),0.])
        R=cv2.Rodrigues(vector)[0];rotations.append(R)
        body=camera@R
        lon=np.rad2deg(np.arctan2(body[:,:,2],body[:,:,0]))
        defect=visible & (np.abs(lon)<defect_width_deg/2)
        intensity=np.uint8(np.clip(150+45*np.sin(.25*body[:,:,0])+30*np.cos(.23*body[:,:,2]),0,255))
        image=np.repeat(intensity[:,:,None],3,axis=2);image[~visible]=0
        views.append(FruitView(image,visible.astype(np.uint8),{'known_defect':defect.astype(np.uint8)},k))
    ellipse=_ellipse(views[0].object_mask);ellipse.center=center
    matrix=np.eye(3)/radius**2
    model=Spheroid(radius,radius,[ellipse]*16,[matrix]*16,np.eye(3),0,[np.array([0.,1.,0.])]*16)
    pairs=[(rotations[k+1]@rotations[k].T,0.) for k in range(15)]
    settings=Settings(spheroid_type='sphere',rotation_axis='y',
                      minimum_rotation_coverage_deg=0 if surface_coverage_gate else 350,
                      minimum_longitude_coverage_deg=350 if surface_coverage_gate else 0,
                      maximum_pair_gap_deg=55,defect_observations_complete=True)
    with patch.object(algorithm,'fit_spheroid',return_value=model),patch.object(algorithm,'estimate_rotation',side_effect=pairs):
        result=build_surface_map(views,settings)
    return views,result,settings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    parser.add_argument('--expected-sha256',help='Require an exact algorithm snapshot before running')
    args=parser.parse_args()
    output=ROOT/'synthetic_runs'/args.label
    output.mkdir(parents=True,exist_ok=False)
    source=Path(algorithm.__file__).read_bytes()
    if args.expected_sha256 and hashlib.sha256(source).hexdigest()!=args.expected_sha256:
        raise ValueError('Current algorithm does not match the requested exact source')
    (output/'algorithm_snapshot.py').write_bytes(source)
    (output/'benchmark_snapshot.py').write_bytes(Path(__file__).read_bytes())
    report={'recorded_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
            'algorithm_sha256':hashlib.sha256(source).hexdigest(),
            'method':'Analytically rendered radius-55 sphere, exact 25-degree y rotations, 16 views, true longitude-wedge defect masks. Geometry and motion estimators bypassed only in this control.',
            'limitations':'No neural models; validates projection, repeated-defect fusion, area normalization and grading arithmetic, not field accuracy.',
            'tolerance_percentage_points':1.,'cases':[],
            'input_manifest':[], 'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for width,grade in ((18.,'Class 1'),(54.,'Class 2'),(108.,'Class 3')):
        views,result,settings=sphere_case(width)
        expected=width/360*100
        folder=output/f'defect_{expected:.0f}pct';folder.mkdir()
        inputs=folder/'inputs';inputs.mkdir()
        for index,view in enumerate(views):
            path=inputs/f'view_{index:02d}.npz'
            np.savez_compressed(path,image=view.image,object_mask=view.object_mask,
                true_defect_mask=view.defect_masks['known_defect'],frame_index=view.frame_index,
                radius_px=55.,center_xy=np.array([74.5,74.5]),
                true_rotation_vector_deg=np.array([0.,index*375./15,0.]),defect_width_deg=width)
            report['input_manifest'].append({'file':str(path.relative_to(output)),
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        for index in (0,4,8,12):
            cv2.imwrite(str(folder/f'view_{index:02d}.png'),views[index].image)
            cv2.imwrite(str(folder/f'true_defect_{index:02d}.png'),views[index].defect_masks['known_defect']*255)
        cv2.imwrite(str(folder/'surface_map.png'),result.bgr_map)
        cv2.imwrite(str(folder/'observed_mask.png'),result.observed_mask*255)
        cv2.imwrite(str(folder/'mapped_defect.png'),result.defect_maps['known_defect']*255)
        overlay=result.bgr_map.copy();mask=result.defect_maps['known_defect']>0
        overlay[mask]=(.5*overlay[mask]+.5*np.array([0,0,255])).astype(np.uint8)
        cv2.imwrite(str(folder/'defect_overlay.png'),overlay)
        row={'expected_pct_of_observed':expected,'measured_pct_of_observed':result.defect_pct_of_observed,
             'absolute_error_percentage_points':abs(result.defect_pct_of_observed-expected),
             'expected_grade':grade,'grade':result.grade,'status':result.status,
             'expected_rotation_deg':375.,'rotation_deg':result.rotation_coverage_deg,
             'observed_surface_pct':result.observed_surface_pct}
        row['passed']=(row['absolute_error_percentage_points']<=1 and result.grade==grade and
                       abs(result.rotation_coverage_deg-375)<1e-6)
        report['cases'].append(row)
    report['settings']=asdict(settings)
    report['coverage_controls']=[]
    for degrees,should_grade in ((375.,True),(270.,True),(250.,False),(100.,False)):
        views,result,settings=sphere_case(54.,degrees,True)
        folder=output/f'coverage_{degrees:.0f}deg';folder.mkdir()
        inputs=folder/'inputs';inputs.mkdir()
        for index,view in enumerate(views):
            path=inputs/f'view_{index:02d}.npz'
            np.savez_compressed(path,image=view.image,object_mask=view.object_mask,
                true_defect_mask=view.defect_masks['known_defect'],frame_index=view.frame_index,
                radius_px=55.,center_xy=np.array([74.5,74.5]),
                true_rotation_vector_deg=np.array([0.,index*degrees/15,0.]),defect_width_deg=54.)
            report['input_manifest'].append({'file':str(path.relative_to(output)),
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        cv2.imwrite(str(folder/'surface_map.png'),result.bgr_map)
        cv2.imwrite(str(folder/'observed_mask.png'),result.observed_mask*255)
        row={'true_rotation_deg':degrees,'observed_longitude_deg':result.observed_longitude_deg,
             'observed_surface_pct':result.observed_surface_pct,'expected_graded':should_grade,
             'grade':result.grade,'status':result.status,
             'passed':(result.grade is not None)==should_grade}
        report['coverage_controls'].append(row)
    report['coverage_control_settings']=asdict(settings)
    report['passed']=all(case['passed'] for case in report['cases'])
    report['passed'] &= all(case['passed'] for case in report['coverage_controls'])
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    lines=['# Known-area mapping controls','',
        f"Exact algorithm SHA `{report['algorithm_sha256']}`.",
        '',report['method'],report['limitations'],'',
        'These controls deliberately substitute known geometry and rotations. They test projection, repeated-defect union, area weighting, coverage gates and grade arithmetic. They do not test rotation estimation, detection, segmentation or field grading accuracy. All 112 rendered input views, truth masks and poses are frozen as hashed NPZ files.',
        '', '| True defect percentage | Measured percentage | Absolute error, percentage points | Expected / returned grade | Outcome |',
        '|---:|---:|---:|---|---|']
    for row in report['cases']:
        lines.append(f"| {row['expected_pct_of_observed']:.0f} | {row['measured_pct_of_observed']:.6f} | {row['absolute_error_percentage_points']:.6f} | {row['expected_grade']} / {row['grade']} | {'PASS' if row['passed'] else 'FAIL'} |")
    lines+=['', 'Area tolerance: 1 percentage point, declared before execution. Coverage cases retain the existing 375°/270° eligible and 250°/100° partial expectations.','']
    (output/'KNOWN_AREA_CONTROLS.md').write_text('\n'.join(lines),encoding='utf-8')
    hashes={str(path.relative_to(output)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in output.rglob('*') if path.is_file()}
    (output/'sha256.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
