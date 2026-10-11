"""Scale, shape, physical coverage and visual evidence for the paired dense replay."""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')

import cv2
import numpy as np
from scipy.integrate import quad

import algorithm as a
from validate_dense_mapping import DEFAULT_OUTPUT, load_module, load_views, sha, stats, write


def continuous_area(radii, max_latitude_deg=90):
    """Independent quadrature of the same full ellipsoid Jacobian."""
    rx,ry,rz=radii
    def at_lat(l):
        c,t=np.cos(l),np.sin(l)
        def at_lon(p):
            return c*np.sqrt((ry*rz*c*np.cos(p))**2+(rx*rz*t)**2+(rx*ry*c*np.sin(p))**2)
        return 4*quad(at_lon,0,np.pi/2,epsabs=1e-7,epsrel=1e-8)[0]
    limit=np.deg2rad(max_latitude_deg)
    return 2*quad(at_lat,0,limit,epsabs=1e-6,epsrel=1e-8)[0]


def coverage_curve(radii, latitude_limit=60):
    """Ideal aligned rolling: the fusion span is measured travel + 90 degrees.

    Integrate the longitude-dependent area density, retaining the full surface
    denominator. This is an upper bound with ideal silhouettes, zero rocking,
    and valid supported projections, not a promise of real coverage.
    """
    lat=(np.arange(720)+.5)*np.pi/720-np.pi/2
    lon=(np.arange(1440)+.5)*2*np.pi/1440
    area=a._ellipsoid_jacobian(lat,lon,radii)
    band=area[np.abs(lat)<np.deg2rad(latitude_limit)].sum(axis=0)
    total=area.sum()
    # The first camera center is phi=90 degrees, with pre-roll starting phi=45.
    start=180
    arc=np.r_[band[start:],band[:start]]
    cumulative=np.cumsum(arc)/total*100
    result={}
    for target in (65,70,75,80,85):
        if cumulative[-1]<target:
            result[str(target)]=None
        else:
            supported_span=(np.searchsorted(cumulative,target)+1)*360/len(lon)
            result[str(target)]=max(0.,supported_span-90.)
    return dict(full_area=continuous_area(radii),band_fraction=continuous_area(radii,latitude_limit)/continuous_area(radii),
                ideal_required_rotation_deg=result,ideal_supported_longitude_plus_rotation_endpoints_deg=90.)


def calibration(output):
    manifest=json.loads((output/'inputs.json').read_text())
    module=load_module(output/'baseline_source/algorithm.py','scale_audit_baseline')
    source=json.loads((output/'baseline/settings.json').read_text())
    s=module.Settings(**source)
    rows=[]; counts={str(d):[] for d in (4,3,2,1)}; models=Counter()
    cv2.setNumThreads(1)
    for record in manifest['records']:
        if len(record['views'])<2:
            continue
        views=load_views(module,output,record)
        model=module.fit_spheroid(views,s)
        axes,radii=module._map_frame(model,s)
        geometry=coverage_curve(radii)
        models['sphere' if model.A==model.B else 'oblate']+=1
        full=[r['frame'] for r in record['tracking_history'] if not r['touches_frame_edge']]
        longest=current=0; previous=None
        for frame in full:
            current=current+1 if previous is not None and frame==previous+1 else 1
            longest=max(longest,current); previous=frame
        duration=max(0,longest-1)/manifest['fps']
        row=dict(track_id=record['track_id'],A=model.A,B=model.B,
                 flattening=(model.A-model.B)/model.A,map_radii_px=radii.tolist(),
                 visible_interval_sec=duration,usable_views=len(views),**geometry)
        row['minimum_rpm_for_80']=geometry['ideal_required_rotation_deg']['80']/360*60/duration if duration else None
        rows.append(row)
        for index in sorted({0,len(views)//2,len(views)-1}):
            v=views[index]; e=model.ellipses[index]
            for down in (4,3,2,1):
                ss=replace(s,image_downsample=down,highpass_sigma=5/down)
                high,mask=module._preprocess(v,down,5/down)
                h,w=high.shape; yy,xx=np.mgrid[:h,:w]
                delta=np.stack(((xx+.5)*v.image.shape[1]/w-.5-e.center[0],
                                (yy+.5)*v.image.shape[0]/h-.5-e.center[1]),axis=-1)
                interior=((delta@e.v_major/e.major)**2+(delta@e.v_minor/e.minor)**2<.66**2)&(mask>0)
                candidates=int(interior.sum())
                percentile=int(np.count_nonzero(interior&(np.abs(high)>=np.percentile(np.abs(high[interior]),97))))
                try:
                    points,_,_=module._relevant(v,model,index,ss)
                    selected=len(points)
                except module.MappingError:
                    selected=0
                counts[str(down)].append(dict(track_id=record['track_id'],frame=v.frame_index,
                   diameter_px=2*e.major,candidates=candidates,percentile_points=percentile,selected=selected))
        if len(rows)%50==0:
            print('Scale/geometry audited',len(rows),flush=True)
    summary=dict(records=len(rows),fps=manifest['fps'],model_counts=dict(models),
        flattening=stats([r['flattening'] for r in rows]),
        diameter_px=stats([r['diameter_px'] for r in counts['2']]),
        visible_interval_sec=stats([r['visible_interval_sec'] for r in rows]),
        minimum_rpm_for_80=stats([r['minimum_rpm_for_80'] for r in rows if r['minimum_rpm_for_80'] is not None]),
        band_fraction=stats([r['band_fraction'] for r in rows]),
        ideal_required_rotation_deg={str(t):stats([r['ideal_required_rotation_deg'][str(t)] for r in rows
                                                   if r['ideal_required_rotation_deg'][str(t)] is not None])
                                     for t in (65,70,75,80,85)},
        points={d:{key:stats([r[key] for r in values]) for key in ('candidates','percentile_points','selected')}
                for d,values in counts.items()})
    write(output/'calibration.json',dict(summary=summary,records=rows,point_counts=counts,
          assumptions='Ideal aligned rolling required-travel curves are acquisition upper bounds, '
                      'not measured fruit rotations. Shortest fitted B is only identifiable if its '
                      'pole becomes sufficiently parallel to the image plane.'))
    print(json.dumps(summary,indent=2))


def source_panel(output):
    cv2.setNumThreads(1)
    manifest=json.loads((output/'inputs.json').read_text())
    canvas=np.full((480,1000,3),245,np.uint8)
    module=load_module(output/'baseline/algorithm.py','panel_source_module')
    for j,track in enumerate([1,9]):
        record=next(r for r in manifest['records'] if r['track_id']==track)
        views=load_views(module,output,record)
        for k,i in enumerate([0,min(4,len(views)-1),min(8,len(views)-1),min(12,len(views)-1),len(views)-1]):
            view=views[i]; image=view.image; h,w=image.shape[:2]
            ratio=min(190/w,200/h); image=cv2.resize(image,None,fx=ratio,fy=ratio)
            x,y=200*k,240*j
            canvas[y+25:y+25+image.shape[0],x:x+image.shape[1]]=image
            cv2.putText(canvas,f'ID {track} f{view.frame_index}',(x+3,y+18),cv2.FONT_HERSHEY_SIMPLEX,.5,(20,20,20),1)
    cv2.imwrite(str(output/'source_pairs.png'),canvas)


def panels(output, variant='final'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    manifest=json.loads((output/'inputs.json').read_text())
    report=json.loads((output/variant/'report.json').read_text())
    module=load_module(output/variant/'algorithm.py','visual_audit_algorithm')
    s=module.Settings(**report['settings'])
    maps=sorted([r for r in report['records'] if 'observed_surface_pct' in r],key=lambda r:r['observed_surface_pct'])
    chosen=[]
    if maps:
        chosen=[('highest_real_coverage',maps[-1]),('median_real_coverage',maps[len(maps)//2]),
                ('low_real_coverage',maps[len(maps)//10])]
    failures=[r for r in report['records'] if r['usable_views']>=2 and 'observed_surface_pct' not in r]
    if failures:
        failures.sort(key=lambda r:r['usable_views'])
        chosen.append(('failed_real_record',failures[len(failures)//2]))
    destination=output/'visuals'; destination.mkdir(exist_ok=True)
    evidence=[]
    for label,row in chosen:
        record=next(r for r in manifest['records'] if r['track_id']==row['track_id'])
        views=load_views(module,output,record)
        model=module.fit_spheroid(views,s)
        selected=row.get('view_frames',[])
        illustrated=selected or [views[0].frame_index,views[len(views)//2].frame_index,views[-1].frame_index]
        view_rows=int(np.ceil(len(illustrated)/6))
        fig=plt.figure(figsize=(18,3*view_rows+8),layout='constrained')
        grid=GridSpec(view_rows+3,6,figure=fig,height_ratios=[3]*view_rows+[2.6,1.5,1.3])
        accepted={(r['source_frame'],r['target_frame']):r for r in row['selection_diagnostics'] if r['status']=='accepted'}
        progress={frame:angle for frame,angle in zip(selected,np.r_[0.,np.cumsum(np.abs(row.get('pair_rotations_deg',[])))])}
        point_info=[]
        for j,frame in enumerate(illustrated):
            index=next(i for i,v in enumerate(views) if v.frame_index==frame)
            view=views[index]
            settings=s
            pair=next((d for (f,t),d in accepted.items() if f==frame),None)
            if pair is None:
                pair=next((d for (f,t),d in accepted.items() if t==frame),None)
            if pair:
                settings=replace(s,image_downsample=pair.get('image_downsample',s.image_downsample),
                                 highpass_sigma=pair.get('highpass_sigma',s.highpass_sigma))
            ax=fig.add_subplot(grid[j//6,j%6])
            ax.imshow(cv2.cvtColor(view.image,cv2.COLOR_BGR2RGB))
            ax.contour(view.object_mask,levels=[.5],colors=['cyan'],linewidths=.7)
            try:
                points,values,_=module._relevant(view,model,index,settings)
                xy=points[:,:2]+model.ellipses[index].center
                ax.scatter(xy[:,0],xy[:,1],s=3,c='#77ff77',alpha=.8)
                point_info.append(dict(frame=frame,points=len(points),selected_rms=float(np.sqrt(np.mean(values**2)))))
            except module.MappingError as error:
                point_info.append(dict(frame=frame,reason=str(error)))
            detail=f' | residual {pair["error"]:.3f}' if pair else ''
            angle=f' | rolling sum {progress[frame]:.1f} deg' if frame in progress else ' | no supported pose'
            ax.set_title(f'frame {frame}{angle}\n{len(point_info[-1].get("points",[])) if isinstance(point_info[-1].get("points"),list) else point_info[-1].get("points",0)} texture points{detail}',fontsize=9)
            ax.axis('off')
        map_ax=fig.add_subplot(grid[view_rows,:3]); observed_ax=fig.add_subplot(grid[view_rows,3:])
        if 'observed_surface_pct' in row:
            folder=output/variant/str(row['track_id'])
            color=cv2.imread(str(folder/'surface_map.png'))
            observed=cv2.imread(str(folder/'observed_mask.png'),cv2.IMREAD_GRAYSCALE)>0
            display=cv2.cvtColor(color,cv2.COLOR_BGR2RGB); display[~observed]=[70,70,70]
            map_ax.imshow(display,aspect='auto'); map_ax.set_title('Surface map (grey = unknown; no filled skin)')
            observed_ax.imshow(observed,cmap='gray',vmin=0,vmax=1,aspect='auto')
            observed_ax.set_title(f'Actual observed support: {row["observed_surface_pct"]:.2f}% of full model')
            coordinates=np.load(folder/'map_coordinates.npz')
            longitude=coordinates['longitude']; latitude=coordinates['latitude']
            for ax in (map_ax,observed_ax):
                ax.set_xlabel(f'Longitude columns; {longitude[0]:.1f} to {longitude[-1]:.1f} deg')
                ax.set_ylabel(f'Latitude; {latitude[0]:.1f} to {latitude[-1]:.1f} deg')
            support=fig.add_subplot(grid[view_rows+1,:3])
            support.plot(longitude,observed.any(axis=0).astype(int),lw=1.5)
            support.set_ylim(-.1,1.1); support.set_title(f'Observed longitude: {row["observed_longitude_deg"]:.2f} deg')
            support.set_xlabel('Longitude (degrees)'); support.set_ylabel('Column has valid support')
            residual=fig.add_subplot(grid[view_rows+1,3:])
            residual.plot(selected[1:],row['pair_errors'],'o-',ms=3)
            residual.axhline(.58,c='red',ls='--',label='unchanged maximum residual')
            residual.set_ylim(0,.65); residual.set_xlabel('Target frame'); residual.set_ylabel('Normalized residual')
            residual.legend(fontsize=8)
            title=(f'{label}: record {row["track_id"]}, {row["observed_surface_pct"]:.2f}% surface / '
                   f'{row["observed_longitude_deg"]:.2f} deg longitude / '
                   f'{row["rotation_coverage_deg"]:.2f} deg measured rolling; '
                   f'{"complete coverage" if row["coverage_complete"] else "PARTIAL"}')
        else:
            for ax in (map_ax,observed_ax):
                ax.text(.5,.5,'Mapping rejected\nNo surface map or coverage value reported',ha='center',va='center',transform=ax.transAxes)
                ax.axis('off')
            title=f'{label}: record {row["track_id"]}; {row["usable_views"]} crops, no reliable measured sequence'
        note=fig.add_subplot(grid[view_rows+2,:]); note.axis('off')
        diagnostics=Counter(r['status'] for r in row['selection_diagnostics'])
        text=f'Identity: {row["identity_status"]}. Captured views: {row["usable_views"]}. Selection diagnostics: {dict(diagnostics)}.\n'
        text+='Cyan contours: fruit masks. Green dots: actual relevant texture points. All angles come from accepted image measurements.\n'
        text+='Geometry replay: no defect masks or grades. Real pose and surface-area ground truth are unavailable.'
        note.text(0,.9,text,fontsize=10,va='top')
        fig.suptitle(title,fontsize=13)
        path=destination/(label+'.png'); fig.savefig(path,dpi=130); plt.close(fig)
        evidence.append(dict(label=label,track_id=row['track_id'],file=str(path.relative_to(output)),
                             points=point_info,selected_frames=selected,
                             observed_surface_pct=row.get('observed_surface_pct')))
    write(output/'visuals.json',dict(variant=variant,panels=evidence,
        real_high_coverage_success_exists=any(r['observed_surface_pct']>=80 for r in maps)))
    if maps:
        row=maps[-1]
        selected=row['view_frames']
        chosen_pair=next(d for d in row['selection_diagnostics'] if d.get('status')=='accepted'
                         and d['source_frame']==selected[0] and d['target_frame']==selected[1])
        record=next(r for r in manifest['records'] if r['track_id']==row['track_id'])
        views=load_views(module,output,record)
        model=module.fit_spheroid(views,s)
        src=next(i for i,v in enumerate(views) if v.frame_index==chosen_pair['source_frame'])
        dst=next(i for i,v in enumerate(views) if v.frame_index==chosen_pair['target_frame'])
        actual=replace(s,image_downsample=chosen_pair['image_downsample'],
                       highpass_sigma=chosen_pair['highpass_sigma'])
        points,_,_=module._relevant(views[src],model,src,actual)
        R=cv2.Rodrigues(np.deg2rad(chosen_pair['rotation_vector_deg']))[0]
        target=points@R.T
        valid=(target@model.matrices[dst][:,2])>0
        xy0=points[:,:2]+model.ellipses[src].center
        xy1=target[:,:2]+model.ellipses[dst].center
        fig,axes=plt.subplots(1,2,figsize=(12,6),layout='constrained')
        for ax,index,xy,colour in zip(axes,(src,dst),(xy0,xy1),('lime','red')):
            ax.imshow(cv2.cvtColor(views[index].image,cv2.COLOR_BGR2RGB))
            ax.contour(views[index].object_mask,levels=[.5],colors=['cyan'],linewidths=.6)
            ax.scatter(xy[:,0],xy[:,1],s=8,c=colour,alpha=.75)
            ax.set_title(('Source texture points' if index==src else 'Predicted target positions')+
                         f': frame {views[index].frame_index}')
            ax.axis('off')
        fig.suptitle(f'REAL record {row["track_id"]}: directly measured vector '
                     f'{np.round(chosen_pair["rotation_vector_deg"],2).tolist()} deg; '
                     f'residual {chosen_pair["error"]:.3f}\n'
                     'Red positions are model predictions, not independently labelled correspondences.',fontsize=11)
        fig.savefig(destination/'accepted_pair_projection.png',dpi=130);plt.close(fig)
    print(json.dumps(evidence,indent=2))


def physical_evidence(output,variant='final'):
    manifest=json.loads((output/'inputs.json').read_text())
    calibration=json.loads((output/'calibration.json').read_text())
    report=json.loads((output/variant/'report.json').read_text())
    geometry={r['track_id']:r for r in calibration['records']}
    rows=[]; pair_rpm=[]
    fps=manifest['fps']
    for record in report['records']:
        if record['usable_views']<2:
            continue
        geo=geometry[record['track_id']]
        row=dict(track_id=record['track_id'],usable_views=record['usable_views'],
                 full_visible_sec=geo['visible_interval_sec'],minimum_rpm_for_80=geo['minimum_rpm_for_80'])
        if 'observed_surface_pct' in record:
            frames=record['view_frames']
            interval=(frames[-1]-frames[0])/fps
            row.update(selected_views=len(frames),measured_interval_sec=interval,
                       measured_rolling_deg=record['rotation_coverage_deg'],
                       measured_longitude_span_deg=record['map_longitude_span_deg'],
                       observed_longitude_deg=record['observed_longitude_deg'],
                       observed_surface_pct=record['observed_surface_pct'],
                       measured_rolling_rpm_over_supported_chain=record['rotation_coverage_deg']/6/interval)
            pair_rpm.extend(abs(angle)/6/((target-source)/fps)
                            for angle,source,target in zip(record['pair_rotations_deg'],frames,frames[1:]))
        rows.append(row)
    summary=dict(eligible_records=len(rows),fps=fps,
        measured_pair_rpm=stats(pair_rpm),
        measured_chain_rpm=stats([r['measured_rolling_rpm_over_supported_chain'] for r in rows if 'measured_interval_sec' in r]),
        measured_interval_sec=stats([r['measured_interval_sec'] for r in rows if 'measured_interval_sec' in r]),
        required_rpm_for_80=calibration['summary']['minimum_rpm_for_80'],
        statement='Rates describe only directly supported image pairs/chains. They are never extrapolated '
                  'across unavailable intervals. Failed registration is not proof of zero physical rotation. '
                  'This evidence cannot establish a physical upper bound on unseen rotation.')
    write(output/'physical_rotation.json',dict(summary=summary,records=rows))
    print(json.dumps(summary,indent=2))


def synthetic_evidence(output,variant='final'):
    from test_dense_mapping import render
    destination=output/('synthetic' if variant=='final' else 'synthetic_'+variant); destination.mkdir(exist_ok=True)
    module=load_module(output/variant/'algorithm.py','synthetic_evidence_algorithm')
    s=module.Settings(**json.loads((output/variant/'settings.json').read_text()))
    cases=[]
    cv2.setNumThreads(1)
    for oblate in (False,True):
        label='oblate' if oblate else 'sphere'
        folder=destination/label; folder.mkdir(exist_ok=True)
        angles=np.linspace(0,360,65)
        views=render(angles,oblate)
        yy,xx=np.mgrid[:210,:210]; X,Y=xx-104.5,yy-104.5
        A,B=82.,65. if oblate else 82.
        Z=A*np.sqrt(np.maximum(1-(X/B)**2-(Y/A)**2,0))
        camera=np.stack((X,Y,Z),axis=-1)
        inputs=[]
        for index,(angle,view) in enumerate(zip(angles,views)):
            t=np.deg2rad(angle)
            R=np.array([[1.,0.,0.],[0.,np.cos(t),-np.sin(t)],[0.,np.sin(t),np.cos(t)]])
            body=camera@R
            lon=np.rad2deg(np.arctan2(body[:,:,2],-body[:,:,1]))
            delta=(lon-90+180)%360-180
            defect=(np.abs(delta)<27)&(view.object_mask>0)
            view.defect_masks={'known_54_degree_wedge':defect.astype(np.uint8)}
            file=f'view_{index:03d}.npz'
            np.savez_compressed(folder/file,image=view.image,mask=view.object_mask,
                                defect=defect.astype(np.uint8),true_angle_deg=angle)
            inputs.append(dict(file=file,sha256=sha(folder/file),true_angle_deg=float(angle)))
        mapped=module.build_surface_map(views,s)
        cv2.imwrite(str(folder/'surface_map.png'),mapped.bgr_map)
        cv2.imwrite(str(folder/'observed_mask.png'),mapped.observed_mask*255)
        cv2.imwrite(str(folder/'defect_map.png'),mapped.defect_maps['known_54_degree_wedge']*255)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(2,3,figsize=(15,7),layout='constrained')
        for ax,index in zip(axes[0],(0,16,32)):
            ax.imshow(cv2.cvtColor(views[index].image,cv2.COLOR_BGR2RGB))
            ax.contour(views[index].object_mask,levels=[.5],colors='cyan',linewidths=.6)
            ax.set_title(f'SYNTHETIC frame {index}, true rotation {angles[index]:.1f} deg')
            ax.axis('off')
        axes[1,0].imshow(cv2.cvtColor(mapped.bgr_map,cv2.COLOR_BGR2RGB),aspect='auto')
        axes[1,0].set_title(f'Measured surface map: {mapped.observed_surface_pct:.3f}%')
        axes[1,1].imshow(mapped.observed_mask,cmap='gray',aspect='auto')
        axes[1,1].set_title(f'Observed longitude: {mapped.observed_longitude_deg:.2f} deg')
        axes[1,2].imshow(mapped.defect_maps['known_54_degree_wedge'],cmap='gray',aspect='auto')
        axes[1,2].set_title(f'Known wedge 15% / measured {mapped.defect_pct_of_observed:.3f}%')
        fig.suptitle(f'SYNTHETIC KNOWN TRUTH — {label}; measured rolling {mapped.rotation_coverage_deg:.2f} deg; '
                     f'{mapped.grade}. This is not a real successful fruit.',fontsize=12)
        fig.savefig(folder/'diagnostic_panel.png',dpi=120); plt.close(fig)
        accepted=[r for r in mapped.selection_diagnostics if r['status']=='accepted']
        errors=[]
        for pair in accepted:
            truth=angles[pair['target_frame']]-angles[pair['source_frame']]
            errors.append(abs(pair['rotation_vector_deg'][0]-truth))
        row=dict(model=label,true_radii_px=[A,B,A],true_rotation_deg=360.,
                 measured_rotation_deg=mapped.rotation_coverage_deg,
                 max_pair_rolling_error_deg=max(errors),observed_surface_pct=mapped.observed_surface_pct,
                 observed_longitude_deg=mapped.observed_longitude_deg,expected_defect_pct=15.,
                 measured_defect_pct=mapped.defect_pct_of_observed,grade=mapped.grade,
                 selected_frames=mapped.view_frames,selection_diagnostics=mapped.selection_diagnostics,
                 inputs=inputs)
        row['passed']=(abs(row['measured_rotation_deg']-360)<=8 and row['max_pair_rolling_error_deg']<=1.5
                       and row['observed_surface_pct']>=80 and row['observed_longitude_deg']>=350
                       and abs(row['measured_defect_pct']-15)<=1.5 and row['grade']=='Class 2')
        write(folder/'report.json',row); cases.append(row)
        print(label,{k:v for k,v in row.items() if k not in ('inputs','selection_diagnostics')},flush=True)
    summary=dict(algorithm_sha256=sha(output/variant/'algorithm.py'),cases=cases,
                 settings=json.loads((output/variant/'settings.json').read_text()),passed=all(r['passed'] for r in cases),
                 limitations='Known mathematical truth, exact silhouettes and synthetic texture. '
                             'No neural models or claims of real-field accuracy. Rotations are recovered from rendered images.')
    write(destination/'report.json',summary)
    if not summary['passed']:
        raise AssertionError('Rendered synthetic controls failed')


def pose_audit(output,variant):
    manifest=json.loads((output/'inputs.json').read_text())
    module=load_module(output/variant/'algorithm.py','pose_audit_algorithm')
    settings=module.Settings(**json.loads((output/variant/'settings.json').read_text()))
    rows=[]
    for record in manifest['records']:
        if len(record['views'])<2:
            continue
        views=load_views(module,output,record)
        row=dict(track_id=record['track_id'])
        for method in ('silhouette_trend','robust_trend','projected_trend'):
            model=module.fit_spheroid(views,replace(settings,pole_pose_method=method))
            row[method]=np.degrees(np.arccos(np.clip([abs(x@y) for x,y in
                zip(model.pole_axes,model.pole_axes[1:])],0,1))).tolist()
        rows.append(row)
    summary={method:dict(steps=stats([v for r in rows for v in r[method]]),
        jumps_over_search_cone=sum(int(v>np.hypot(settings.max_pair_angle_deg,settings.transverse_angle_deg))
            for r in rows for v in r[method])) for method in ('silhouette_trend','robust_trend','projected_trend')}
    write(output/'pose_trend_comparison.json',dict(algorithm_sha256=sha(output/variant/'algorithm.py'),
        input_manifest_sha256=sha(output/'inputs.json'),summary=summary,records=rows))
    print(json.dumps(summary,indent=2))


def pole_control(output,variant):
    from test_algorithm import AlgorithmTests
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    modules=dict(fixed_window=load_module(output/'final_v2/algorithm.py','fixed_window_control'),
                 adaptive_window=load_module(output/variant/'algorithm.py','adaptive_window_control'))
    parameters=json.loads((output/variant/'settings.json').read_text())
    pole=np.array([.75,.55,.36]);pole/=np.linalg.norm(pole)
    truth=[AlgorithmTests._rotation('x',k*35)@pole for k in range(65)]
    errors={};depth={};minor=None
    for label,module in modules.items():
        views=[module.FruitView(np.zeros((150,150,3),np.uint8),
               AlgorithmTests._silhouette(p),frame_index=k) for k,p in enumerate(truth)]
        control_parameters=dict(parameters)
        if label=='fixed_window':
            control_parameters['pole_pose_method']='robust_trend'
        model=module.fit_spheroid(views,module.Settings(**control_parameters))
        fitted=np.array([p if p@t>=0 else -p for p,t in zip(model.pole_axes,truth)])
        errors[label]=np.degrees(np.arccos(np.clip(np.sum(fitted*np.array(truth),axis=1),0,1))).tolist()
        depth[label]=fitted[:,2]
        minor=[e.minor for e in model.ellipses]
    assert max(errors['adaptive_window'])<5 and max(errors['fixed_window'])>45
    fig,axes=plt.subplots(3,1,figsize=(12,9),layout='constrained',sharex=True)
    axes[0].plot(minor,'o-',ms=3);axes[0].set_ylabel('Measured minor radius (px)')
    axes[0].set_title('Known synthetic 35-degree steps; minor-radius cycle can be shorter than seven frames')
    axes[1].plot(np.array(truth)[:,2],c='black',label='known pole depth')
    for label in errors:
        axes[1].plot(depth[label],label=label)
        axes[2].plot(errors[label],label=label)
    axes[1].set_ylabel('Pole depth component');axes[1].legend()
    axes[2].set_ylabel('Pole error (degrees)');axes[2].set_xlabel('Synthetic source frame')
    axes[2].legend()
    fig.suptitle('KNOWN-TRUTH GEOMETRY CONTROL: fixed minor trend versus final '+parameters['pole_pose_method'],fontsize=13)
    destination=output/('pole_control' if variant=='final_v3' else 'pole_control_'+variant);destination.mkdir(exist_ok=True)
    fig.savefig(destination/'rapid_turn.png',dpi=140);plt.close(fig)
    write(destination/'report.json',dict(passed=True,true_step_deg=35,
        active_settings=parameters,
        comparison='Fixed-window minor-radius trend versus current profile; not a one-factor ablation.',
        source_sha256={label:sha(output/('final_v2' if label=='fixed_window' else variant)/'algorithm.py')
                       for label in modules},errors_deg=errors,
        maximum_errors={label:max(values) for label,values in errors.items()},
        limitations='Synthetic geometry only. Ground-truth axes have equivalent signs; '
        'per-frame sign is aligned to truth for visualization. No rotations or coverage are supplied to production.'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('calibration','source-panel','panels','physical','synthetic','pose','pole-control'))
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--variant',default='final')
    args=parser.parse_args()
    if args.mode=='calibration':
        calibration(args.output.resolve())
    elif args.mode=='source-panel':
        source_panel(args.output.resolve())
    elif args.mode=='panels':
        panels(args.output.resolve(),args.variant)
    elif args.mode=='physical':
        physical_evidence(args.output.resolve(),args.variant)
    elif args.mode=='pose':
        pose_audit(args.output.resolve(),args.variant)
    elif args.mode=='pole-control':
        pole_control(args.output.resolve(),args.variant)
    else:
        synthetic_evidence(args.output.resolve(),args.variant)


if __name__=='__main__':
    main()
