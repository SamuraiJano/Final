"""Check the photometric candidate against independent descriptor matches.

All mutual feature matches are included after visible-surface lifting. Their
coordinates and per-point residuals are saved. The separately fitted3D feature
pose is reported only as a diagnostic; no feature fit controls the candidate.
"""
from pathlib import Path
import importlib.util
import hashlib
import json
import sys
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MAPS=ROOT/'diagnostics/fruit340-fix/20261004_native_3d_retry_maps/340'
spec=importlib.util.spec_from_file_location('frozen_final_feature_geometry',HERE/'feature_motion.py')
features=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=features
spec.loader.exec_module(features)
algorithm=features.algorithm


def distribution(errors):
    return dict(count=len(errors),mean_px=float(np.mean(errors)),median_px=float(np.median(errors)),
                maximum_px=float(np.max(errors)),p25_px=float(np.percentile(errors,25)),
                p75_px=float(np.percentile(errors,75)),p95_px=float(np.percentile(errors,95)),
                count_under2px=int(np.count_nonzero(errors<2.)),count_under5px=int(np.count_nonzero(errors<5.)))


def pose_from_result(path):
    if not path.exists():
        return None
    result=json.loads(path.read_text())
    match=next((row for row in result['selection_diagnostics'] if row['source_frame']==308 and row['target_frame']==309),None)
    return None if match is None else match.get('rotation_vector_deg')


def main():
    cv2.setNumThreads(1)
    views=[]
    for item in json.loads((features.FIXTURE/'views.json').read_text()):
        with np.load(features.FIXTURE/item['file']) as data:
            views.append(algorithm.FruitView(data['image'].copy(),data['mask'].copy(),frame_index=item['frame'],fruit_bbox=tuple(item['bbox'])))
    settings=algorithm.Settings(**json.loads((HERE/'manual_correspondences.json').read_text())['settings'])
    model=algorithm.fit_spheroid(views,settings)
    by_frame={view.frame_index:(index,view) for index,view in enumerate(views)}
    source_index,source_view=by_frame[308];target_index,target_view=by_frame[309]
    two_axis=pose_from_result(ROOT/'diagnostics/fruit340-fix/20261004_native_retry_maps/340/candidate/result.json')
    photo_3d=pose_from_result(MAPS/'candidate/result.json')
    vector_source='Saved candidate mapping result' if photo_3d is not None else 'Root-supplied candidate vector rounded to four decimal places'
    if photo_3d is None:
        photo_3d=[12.5235,-8.6043,-6.6061]
    descriptor=json.loads((HERE/'feature_motion.json').read_text())
    manual=json.loads((HERE/'manual_correspondences.json').read_text())
    marker=next(row for row in manual['pairs'] if row['source_frame']==308)
    report={'method':__doc__,'pair':[308,309],'candidate_vector_source':vector_source,
            'photometric_candidate_vector_deg':photo_3d,'earlier_two_axis_retry_vector_deg':two_axis,
            'limitations':['Automatic descriptor matches may include wrong correspondences.',
                           'No calibrated pose or map-coverage truth is available.',
                           'Feature fitted poses use RANSAC and are shown separately from the independent photometric candidate.',
                           'The manual marker has approximately2px label uncertainty and uses fitted geometry.'],
            'comparisons':[]}
    sources=[HERE/'feature_motion.json',HERE/'manual_correspondences.json',
             ROOT/'diagnostics/fruit340-fix/20261004_candidate/baseline/algorithm.py',
             ROOT/'diagnostics/fruit340-fix/20261004_native_retry_maps/340/candidate/result.json',
             MAPS/'baseline/result.json',MAPS/'candidate/result.json',MAPS/'baseline/surface_map.png',MAPS/'candidate/surface_map.png']
    report['sources_sha256']={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources if path.exists()}
    for row in descriptor['results']:
        if row['source_frame']!=308 or not row.get('matches'):
            continue
        source_xy=np.array([match['source_crop'] for match in row['matches']])
        target_xy=np.array([match['target_crop'] for match in row['matches']])
        xy=source_xy-model.ellipses[source_index].center
        points=np.column_stack((xy,algorithm._height(model.matrices[source_index],xy[:,0],xy[:,1])))
        variants={'earlier_two_axis_photometric_retry':two_axis,'final_three_axis_photometric_retry':photo_3d,
                  'diagnostic_three_axis_feature_fit':row['rotation_vector_deg']}
        item=dict(method=row['method'],preprocess=row['preprocess'],raw_mutual_match_count=row['mutual_matches'],
                  visible_lifted_match_count=len(points),excluded_invalid_depth_matches=row['mutual_matches']-len(points),
                  diagnostic_feature_ransac_inlier_count=row['inliers'],variants={})
        for name,vector in variants.items():
            prediction=(points@cv2.Rodrigues(np.deg2rad(vector))[0].T)[:,:2]+model.ellipses[target_index].center
            errors=np.linalg.norm(prediction-target_xy,axis=1)
            marker_prediction=(cv2.Rodrigues(np.deg2rad(vector))[0]@np.array(marker['lifted_source_point']))[:2]+np.array(marker['target_center'])
            item['variants'][name]=dict(vector_deg=vector,all_mutual_matches=distribution(errors),
                 manual_marker_reprojection_error_px=float(np.linalg.norm(marker_prediction-marker['target_crop'])),
                 per_point=[dict(source_crop_xy=a.tolist(),matched_target_crop_xy=b.tolist(),
                                 predicted_target_crop_xy=c.tolist(),reprojection_error_px=float(error),
                                 diagnostic_feature_fit_inlier=match['inlier'])
                            for a,b,c,error,match in zip(source_xy,target_xy,prediction,errors,row['matches'])])
        report['comparisons'].append(item)
    (HERE/'final_candidate_feature_evidence.json').write_text(json.dumps(report,indent=2))
    print(json.dumps([dict(method=row['method'],preprocess=row['preprocess'],
                          variants={name:value['all_mutual_matches'] for name,value in row['variants'].items()})
                     for row in report['comparisons'] if (row['method'],row['preprocess']) in [('sift','raw'),('orb','highpass')]],indent=2))
    if not (MAPS/'candidate/result.json').exists():
        print('Candidate map not yet available; projection statistics saved.')
        return
    baseline=json.loads((MAPS/'baseline/result.json').read_text())
    candidate=json.loads((MAPS/'candidate/result.json').read_text())
    fig,axes=plt.subplots(2,2,figsize=(12,10),layout='constrained',gridspec_kw={'height_ratios':[.9,1.1]})
    fig.get_layout_engine().set(rect=(0.,.075,1.,.88))
    fig.suptitle('Fruit 340: additional measured view, partial surface map',fontsize=17,fontweight='bold',y=.985)
    for axis,variant,result in zip(axes[0],('baseline','candidate'),(baseline,candidate)):
        im=cv2.imread(str(MAPS/variant/'surface_map.png'))
        observed=cv2.imread(str(MAPS/variant/'observed_mask.png'),cv2.IMREAD_GRAYSCALE)>0
        rgb=cv2.cvtColor(im,cv2.COLOR_BGR2RGB)
        rgb[~observed]=(235,235,235)
        axis.imshow(rgb)
        title='Baseline' if variant=='baseline' else 'Native 3D retry'
        frames=result['view_frames']
        axis.set_title(f'{title}: frames {frames[0]}–{frames[-1]}\nEstimated observed surface {result["observed_surface_pct"]:.2f}%',fontsize=12)
        axis.axis('off')
    comparison=next(row for row in report['comparisons'] if row['method']=='orb' and row['preprocess']=='highpass')
    for axis,name,title in zip(axes[1],('earlier_two_axis_photometric_retry','final_three_axis_photometric_retry'),
                               ('Earlier 2D retry','Final 3D retry')):
        variant=comparison['variants'][name]
        axis.imshow(cv2.cvtColor(target_view.image,cv2.COLOR_BGR2RGB))
        for point in variant['per_point']:
            observed=np.array(point['matched_target_crop_xy']);predicted=np.array(point['predicted_target_crop_xy'])
            axis.plot([observed[0],predicted[0]],[observed[1],predicted[1]],color='#66e0d4',alpha=.8,linewidth=1)
            axis.scatter(*observed,s=25,facecolors='none',edgecolors='#00e0ff',linewidths=1)
            axis.scatter(*predicted,s=30,marker='+',c='#fff27d',linewidths=1)
        stats=variant['all_mutual_matches']
        axis.set_title(f'{title}: frame 308→309 projection\nAll 23 mutual ORB matches: median {stats["median_px"]:.2f} px',fontsize=12)
        axis.set_xlim(0,target_view.image.shape[1]);axis.set_ylim(target_view.image.shape[0],0)
        axis.axis('off')
    legend=[Line2D([0],[0],marker='o',markerfacecolor='none',markeredgecolor='#00a6c8',linestyle='none',label='Automatic matched target'),
            Line2D([0],[0],marker='+',color='#a09000',linestyle='none',label='Photometric pose projection')]
    fig.legend(handles=legend,loc='lower center',bbox_to_anchor=(.5,.027),ncol=2,frameon=False)
    fig.text(.5,.013,'All mutual matches shown; some may be wrong. Coverage is estimated; no calibrated pose or surface truth is available.',
             ha='center',fontsize=9,color='#555555')
    fig.savefig(HERE/'fruit340_final_comparison.png',dpi=170)
    plt.close(fig)
    print('Saved fruit340_final_comparison.png.')


if __name__=='__main__':
    main()
