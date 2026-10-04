"""Diagnostic only: compare longitude strips with all-view visibility at known poses.

This bypasses motion, masks, identities and defect networks. It cannot establish
the success rate on the recorded conveyor. It writes only beside this script.
"""
from pathlib import Path
import json
import sys
from unittest.mock import patch

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
import algorithm as a


def render(angles):
    size, radius = 150, 55.
    center = np.array([74.5, 74.5])
    yy, xx = np.mgrid[:size, :size]
    x, y = xx-center[0], yy-center[1]
    mask = (x*x+y*y < radius*radius).astype(np.uint8)
    camera = np.stack((x, y, np.sqrt(np.maximum(radius*radius-x*x-y*y, 0))), axis=-1)
    poses = [cv2.Rodrigues(np.deg2rad([0., angle, 0.]))[0] for angle in angles]
    views = []
    for index, pose in enumerate(poses):
        body = camera @ pose
        longitude = np.rad2deg(np.arctan2(body[..., 2], body[..., 0]))
        defect = mask & (np.abs(longitude) < 27.)
        texture = np.uint8(np.clip(150+45*np.sin(.25*body[...,0])+30*np.cos(.23*body[...,2]), 0, 255))
        image = np.repeat(texture[..., None], 3, axis=2)
        image[mask == 0] = 0
        views.append(a.FruitView(image, mask, {'known_defect': defect.astype(np.uint8)}, index))
    ellipse = a._ellipse(mask)
    ellipse.center = center
    matrix = np.eye(3)/radius**2
    model = a.Spheroid(radius, radius, [ellipse]*len(views), [matrix]*len(views),
                      np.eye(3), 0, [np.array([0., 1., 0.])]*len(views))
    return views, model, poses


def all_visible(views, model, poses, normal_floor):
    radius = model.A
    width, height = int(np.ceil(2*np.pi*radius)), int(np.ceil(np.pi*radius))
    latitude = (np.arange(height)+.5)*np.pi/height-np.pi/2
    longitude = (np.arange(width)+.5)*2*np.pi/width-np.pi
    lam, phi = np.meshgrid(latitude, longitude, indexing='ij')
    points = np.stack((radius*np.cos(lam)*np.cos(phi), radius*np.sin(lam),
                       radius*np.cos(lam)*np.sin(phi)), axis=-1).reshape(-1,3)
    observed = np.zeros(len(points), bool)
    defects = np.zeros(len(points), bool)
    weight = np.zeros(len(points), float)
    colors = np.zeros((len(points), 3), float)
    for view, pose in zip(views, poses):
        camera = points @ pose.T
        cosine = camera[:,2]/radius
        projected = camera.copy()
        projected[:,:2] += model.ellipses[0].center
        pieces = [a._sample_view(view, projected[start:start+16384], ['known_defect'],
                                 np.eye(3)/radius**2, model.ellipses[0].center)
                  for start in range(0, len(projected), 16384)]
        color = np.concatenate([piece[0] for piece in pieces])
        valid = np.concatenate([piece[1] for piece in pieces])
        defect = {'known_defect':np.concatenate([piece[2]['known_defect'] for piece in pieces])}
        valid &= (cosine >= normal_floor) & (np.abs(lam.ravel()) < np.deg2rad(60))
        factor = np.where(valid, cosine*cosine, 0.)
        colors += color[:,0,:]*factor[:,None]
        weight += factor
        observed |= valid
        defects |= defect['known_defect'] & valid
    colors /= np.maximum(weight[:,None], 1e-9)
    image = np.clip(colors.reshape(height,width,3), 0,255).astype(np.uint8)
    observed = observed.reshape(height,width)
    defects = defects.reshape(height,width)
    area = np.broadcast_to(np.cos(latitude[:,None]), observed.shape)
    coverage = 100*(area*observed).sum()/area.sum()
    defect_pct = 100*(area*defects).sum()/(area*observed).sum()
    longitude_coverage = observed.any(axis=0).mean()*360
    return {'surface_pct':float(coverage), 'longitude_deg':float(longitude_coverage),
            'defect_pct_of_observed':float(defect_pct),
            'meets_80_surface_and_350_longitude':bool(coverage>=80 and longitude_coverage>=350)}, image, observed


def main():
    folder = Path(__file__).resolve().parent
    report = {'method':'Independent exact-pose sphere rendering; production strip fusion versus diagnostic all-view projection union. Existing 60-degree latitude limit retained. Pose fitting, segmentation, masks and tracker identity are bypassed. Results are not recorded-video accuracy or a success-rate estimate.',
              'all_view_weights':'Squared camera-normal cosine; optional conservative normal cosine cutoffs.',
              'cases':[]}
    cases = [(f'forward_{degrees}', np.linspace(0,degrees,16).tolist()) for degrees in (100,250,270,375)]
    cases += [('stationary_duplicate_16', [0.]*16),
              ('rocking_275_unique_span', [0,25,50,75,100,125,150,175,200,175,150,175,200,225,250,275])]
    settings = a.Settings(spheroid_type='sphere',rotation_axis='y',minimum_surface_coverage=.8,
                          minimum_longitude_coverage_deg=350,defect_observations_complete=True)
    for name, angles in cases:
        views,model,poses=render(angles)
        row = {'name':name, 'angles_deg':angles, 'current_strip':{}, 'all_view_visibility':[]}
        pairs=[(poses[i+1]@poses[i].T,0.) for i in range(len(poses)-1)]
        try:
            with patch.object(a,'fit_spheroid',return_value=model), patch.object(a,'estimate_rotation',side_effect=pairs):
                result=a.build_surface_map(views,settings)
            row['current_strip']={'surface_pct':result.observed_surface_pct,
                                  'longitude_deg':result.observed_longitude_deg,
                                  'status':result.status,'coverage_complete':result.coverage_complete,
                                  'defect_pct_of_observed':result.defect_pct_of_observed}
            cv2.imwrite(str(folder/f'{name}_current_strip.png'),result.bgr_map)
        except a.MappingError as error:
            row['current_strip']={'unavailable_reason':str(error)}
        for normal_floor in (0., .25, .5):
            measurements,image,mask=all_visible(views,model,poses,normal_floor)
            row['all_view_visibility'].append({'normal_cosine_floor':normal_floor,**measurements})
            if normal_floor == .25:
                cv2.imwrite(str(folder/f'{name}_all_view.png'),image)
                cv2.imwrite(str(folder/f'{name}_all_view_observed.png'),mask.astype(np.uint8)*255)
        report['cases'].append(row)
    (folder/'oracle_visibility.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
