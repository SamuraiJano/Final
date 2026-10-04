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


def sphere_case(defect_width_deg):
    size,radius=150,55.
    center=np.array([(size-1)/2]*2)
    yy,xx=np.mgrid[:size,:size]
    X,Y=xx-center[0],yy-center[1]
    visible=X*X+Y*Y<radius*radius
    Z=np.sqrt(np.maximum(radius*radius-X*X-Y*Y,0))
    camera=np.stack((X,Y,Z),axis=-1)
    views,rotations=[],[]
    for k in range(16):
        vector=np.array([0.,np.deg2rad(k*25.),0.])
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
    settings=Settings(spheroid_type='sphere',rotation_axis='y',minimum_rotation_coverage_deg=350,
                      maximum_pair_gap_deg=55,defect_observations_complete=True)
    with patch.object(algorithm,'fit_spheroid',return_value=model),patch.object(algorithm,'estimate_rotation',side_effect=pairs):
        result=build_surface_map(views,settings)
    return views,result,settings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    args=parser.parse_args()
    output=ROOT/'synthetic_runs'/args.label
    output.mkdir(parents=True,exist_ok=False)
    source=Path(algorithm.__file__).read_bytes()
    (output/'algorithm_snapshot.py').write_bytes(source)
    (output/'benchmark_snapshot.py').write_bytes(Path(__file__).read_bytes())
    report={'recorded_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
            'algorithm_sha256':hashlib.sha256(source).hexdigest(),
            'method':'Analytically rendered radius-55 sphere, exact 25-degree y rotations, 16 views, true longitude-wedge defect masks. Geometry and motion estimators bypassed only in this control.',
            'limitations':'No neural models; validates projection, repeated-defect fusion, area normalization and grading arithmetic, not field accuracy.',
            'tolerance_percentage_points':1.,'cases':[]}
    for width,grade in ((18.,'Class 1'),(54.,'Class 2'),(108.,'Class 3')):
        views,result,settings=sphere_case(width)
        expected=width/360*100
        folder=output/f'defect_{expected:.0f}pct';folder.mkdir()
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
    report['passed']=all(case['passed'] for case in report['cases'])
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
