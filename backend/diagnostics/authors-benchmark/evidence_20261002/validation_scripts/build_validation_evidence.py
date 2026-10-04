"""Create publication-quality figures and an auditable validation report.

Reads frozen experimental results. It does not rerun inference or edit evidence.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone,timedelta
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import textwrap
import zipfile

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

from benchmark_authors import ROOT,DATA


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def rgb(path):
    image=cv2.imread(str(path))
    if image is None:raise FileNotFoundError(path)
    return cv2.cvtColor(image,cv2.COLOR_BGR2RGB)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    parser.add_argument('--api-run',default='full_original_20261002')
    parser.add_argument('--software-checks',default='final_20261002')
    args=parser.parse_args()
    out=ROOT/args.label;out.mkdir(parents=True,exist_ok=False)
    baseline=read(ROOT/'runs/dataset_orientation/report.json')
    forward=read(ROOT/'runs/paper_reconstruction_v1/report.json')
    final=read(ROOT/'runs/operational_profile_v1/report.json')
    synthetic_root=ROOT/'synthetic_runs/longitude_coverage_control_v1'
    synthetic=read(synthetic_root/'report.json')
    pipeline_root=ROOT.parent/'pipeline-runs/original_video_symmetric_v1'
    pipeline=read(pipeline_root/'report.json')
    api_root=ROOT.parent/'api-runs'/args.api_run
    api_summary=read(api_root/'summary.json') if (api_root/'summary.json').exists() else None
    api_report=read(api_root/'response.json') if api_summary else None
    checks_root=ROOT.parent/'software-checks'/args.software_checks
    checks=read(checks_root/'summary.json') if (checks_root/'summary.json').exists() else None
    test_log=(checks_root/'python_tests.txt').read_text(encoding='utf-8') if checks else ''
    test_count=re.search(r'Ran (\d+) tests',test_log)
    software_test_count=int(test_count.group(1)) if test_count else None
    final_status=Counter(t['map'].get('result_status',t['map']['status']) for t in final['tracks'])
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'figure.facecolor':'white','savefig.facecolor':'white',
                         'axes.titleweight':'bold','axes.labelcolor':'#263b43','text.color':'#263b43'})
    figures=[]
    pdf=PdfPages(out/'validation_figures.pdf')
    def save(fig,name,title,caption):
        fig.suptitle(title,fontsize=15,fontweight='bold',x=.04,ha='left',y=.985)
        fig.text(.04,.025,textwrap.fill(caption,145),fontsize=8,va='bottom')
        fig.savefig(out/f'{name}.png',dpi=300)
        fig.savefig(out/f'{name}.pdf')
        pdf.savefig(fig)
        figures.append({'file':f'{name}.png','title':title,'caption':caption})
        plt.close(fig)
    green='#237c61';orange='#c48129';red='#b5444b';blue='#336a9a'

    fig,ax=plt.subplots(1,3,figsize=(12,5));fig.subplots_adjust(top=.81,bottom=.26,wspace=.48)
    labels=['Baseline','Revised']
    for panel,key,total,title in ((ax[0],'geometry_ok',36,'Geometry fits'),(ax[1],'maps_produced',36,'Maps produced'),
                                  (ax[2],'predicted_correspondences',497,'Label predictions returned')):
        vals=[baseline['summary']['all'][key],final['summary']['all'][key]]
        bars=panel.bar(labels,vals,color=[red,green],width=.55)
        panel.set_ylim(0,total*1.18);panel.set_title(title);panel.set_ylabel('Count')
        for bar,value in zip(bars,vals):panel.text(bar.get_x()+bar.get_width()/2,value+total*.035,f'{value}/{total}',ha='center')
        panel.grid(axis='y',alpha=.2);panel.set_axisbelow(True)
    save(fig,'01_before_after','Reference dataset: before and after',
         f'All 36 public sequences and all 497 labelled correspondences are included. Revised maps include partial maps: '
         f'{final_status.get("missing_defect_masks",0)} meet the current coverage gates, '
         f'{final_status.get("insufficient_longitude_coverage",0)} lack circumference coverage, '
         f'{final_status.get("insufficient_surface_coverage",0)} lack area coverage, and 2 fail. Author data have no defect-class truth; no fruit grades are validated here.')

    fig,ax=plt.subplots(figsize=(10,5.5));fig.subplots_adjust(top=.82,bottom=.25,left=.1,right=.96)
    for report,label,color in ((baseline,'Baseline',red),(forward,'Paper-based repairs',orange),(final,'Bidirectional matching',green)):
        errors=np.sort([r['error_px'] for r in report['correspondences'] if r['status']=='ok'])
        x=np.r_[0,errors,110];y=np.r_[0,np.arange(1,len(errors)+1)/497*100,len(errors)/497*100]
        ax.step(x,y,where='post',label=label,color=color,lw=2)
    ax.axvline(5,color=blue,ls='--',lw=1);ax.set(xlim=(0,40),ylim=(0,100),
        xlabel='Maximum allowed projection error (pixels)',ylabel='Percentage of ALL 497 labels')
    ax.legend(loc='lower right');ax.grid(alpha=.2)
    save(fig,'02_error_distribution','Accuracy and availability must be reported together',
         'Each curve counts all 497 labels in its denominator, including rejected predictions. The revised method returns 458 predictions: RMS 5.103 px, median 2.264 px, maximum 35.930 px. It predicts 367/497 labels within 5 px. These are development-set results; labels were not used to fit rotations, but the dataset was inspected during development.')

    good=[row for row in final['correspondences'] if row['status']=='ok']
    selected=[]
    for group in ('mandarins','oranges','tomatoes'):
        rows=[r for r in good if r['group']==group];median=np.median([r['error_px'] for r in rows])
        selected.append((min(rows,key=lambda r:abs(r['error_px']-median)),'Nearest group median'))
    selected.append((max(good,key=lambda r:r['error_px']),'Largest returned error'))
    fig,axes=plt.subplots(4,2,figsize=(10,12));fig.subplots_adjust(top=.92,bottom=.08,hspace=.38,wspace=.12)
    selection_records=[]
    for row_axes,(row,selection) in zip(axes,selected):
        folder=DATA/'rotation/data'/row['group']/row['object']
        files={int(p.stem[2:]):p for p in folder.glob('im*.png')}
        a,b=row_axes
        a.imshow(rgb(files[row['source']]));b.imshow(rgb(files[row['target']]))
        a.scatter(*row['source_xy'],s=140,facecolors='none',edgecolors='#ffff00',lw=2)
        b.scatter(*row['target_xy'],s=150,facecolors='none',edgecolors='#50ff50',lw=2)
        b.scatter(*row['prediction'],s=150,marker='x',color='#ff3535',lw=2)
        a.set_title(f"{row['group']} / {row['object']} / view {row['source']}",fontsize=10)
        b.set_title(f"{selection}: {row['error_px']:.2f} px (view {row['target']})",fontsize=10)
        for panel in row_axes:panel.axis('off')
        selection_records.append({'group':row['group'],'object':row['object'],'annotation_line':row['line'],'selection':selection,'error_px':row['error_px']})
    save(fig,'03_labelled_correspondences','Author-labelled feature projections: representative and worst cases',
         'Yellow: annotated source feature. Green: author target label. Red: predicted target. The first three rows are selected by proximity to each category median error; the last is the largest returned error, so successes are not shown alone. Original image coordinates and author labels are retained in the JSON results.')

    fig,axes=plt.subplots(2,2,figsize=(11,7));fig.subplots_adjust(top=.86,bottom=.17,hspace=.3)
    axes[0,0].text(.5,.5,'Baseline: equatorial rotation\nFAILED\nNo consistent angular progress',ha='center',va='center',color=red,fontsize=14)
    axes[0,1].imshow(rgb(ROOT/'mapping_runs/paper_pose_cost_map_v1/exact_x_map.png'))
    axes[1,0].imshow(rgb(ROOT/'mapping_runs/paper_pose_cost_map_v1/exact_y_map.png'))
    axes[1,1].text(.5,.5,'Exact inputs\nA = 55 px, B = 40 px\n16 views, 25° per step\nExpected total = 375°\nRecovered total = 375°',ha='center',va='center',fontsize=13)
    for panel,title in zip(axes.ravel(),('Before: roller along equator','After: roller along equator','After: roller along symmetry axis','Analytical control')):
        panel.set_title(title);panel.axis('off')
    save(fig,'04_map_geometry_control','Isolating the map-coordinate defect',
         'Geometry and rotations are supplied analytically in this control. Repairing the map reference axis and its associated radii fixes the equatorial-rolling failure. This tests downstream mapping independently of texture estimation, tracking and neural models.')

    fig,axes=plt.subplots(3,2,figsize=(11,8));fig.subplots_adjust(top=.9,bottom=.15,hspace=.38,wspace=.2)
    for row_axes,case in zip(axes,synthetic['cases']):
        value=case['expected_pct_of_observed'];folder=synthetic_root/f'defect_{value:.0f}pct'
        row_axes[0].imshow(rgb(folder/'defect_overlay.png'));row_axes[1].imshow(rgb(folder/'mapped_defect.png'))
        row_axes[0].set_title(f"Truth {value:.0f}% → measured {case['measured_pct_of_observed']:.3f}%")
        row_axes[1].set_title(f"{case['grade']} / area error {case['absolute_error_percentage_points']:.3f} points")
        for panel in row_axes:panel.axis('off')
    save(fig,'05_known_defect_areas','Known defect areas and grade arithmetic',
         'A rendered sphere with exact geometry, exact rotations and true longitude-wedge masks is used. Repeated observations of one defect are fused into one map. The predeclared tolerance is one percentage point; all three cases pass. These are synthetic mapping controls, not measurements of the defect model’s accuracy.')

    fig,axes=plt.subplots(2,2,figsize=(11,7));fig.subplots_adjust(top=.87,bottom=.17,hspace=.3)
    for panel,case in zip(axes.ravel(),synthetic['coverage_controls']):
        panel.imshow(rgb(synthetic_root/f'coverage_{case["true_rotation_deg"]:.0f}deg/observed_mask.png'))
        panel.set_title(f"Motion {case['true_rotation_deg']:.0f}° / observed longitude {case['observed_longitude_deg']:.1f}°\n{'Grade allowed' if case['grade'] else 'Grade withheld'}",fontsize=11)
        panel.set_xticks([]);panel.set_yticks([])
        for spine in panel.spines.values():spine.set_visible(True);spine.set_color('#899b94')
    save(fig,'06_motion_vs_coverage','Physical rotation differs from observed map coverage',
         'The 2022 paper includes approximately 45° of pre-roll and post-roll. In an ideal control, 270° of physical motion therefore supports 360° of longitude. White denotes observed pixels. The 250° and 100° controls remain ungraded. Production requires 350° observed longitude and 65% area; unseen polar caps are not claimed as observed.')

    fig,axes=plt.subplots(2,1,figsize=(11,7));fig.subplots_adjust(top=.87,bottom=.19,hspace=.35)
    axes[0].imshow(rgb(DATA/'maps/mandarin/unrolled_objM0001.png'))
    axes[1].imshow(rgb(ROOT/'mapping_runs/paper_pose_cost_map_v1/objM0001/our_map.png'))
    axes[0].set_title('Published author map: objM0001')
    axes[1].set_title('Independent implementation: fixed 360° output')
    for panel in axes:panel.axis('off')
    save(fig,'07_author_map_comparison','Supplementary visual comparison with an author map',
         'The source is a published montage, split into 14 crops without resizing the source pixels. The author map and the independent output use different longitude extents and are displayed at different scales. This is a qualitative comparison, not pixel-level equivalence, SSIM validation, or reproduction of the paper’s classifier.')

    fruit=next(r for r in pipeline['fruits'] if r['track_id']==5)
    folder=pipeline_root/'5'
    crops=sorted(folder.glob('frame_*_crop.png'));crop=crops[len(crops)//2];prefix=crop.stem.removesuffix('_crop')
    fig,axes=plt.subplots(2,3,figsize=(12,8));fig.subplots_adjust(top=.87,bottom=.17,hspace=.35,wspace=.12)
    paths=[crop,folder/f'{prefix}_fruit_mask.png',folder/f'{prefix}_defect_overlay.png',
           folder/'surface_map.png',folder/'observed.png',folder/'defect_skin_wrinkling.png']
    titles=['1. Detector / tracker crop','2. GrabCut fruit silhouette','3. Defect model overlay',
            '4. Reconstructed partial map','5. Observed-area mask','6. Mapped skin-wrinkling mask']
    for panel,path,title in zip(axes.ravel(),paths,titles):panel.imshow(rgb(path));panel.set_title(title,fontsize=11);panel.axis('off')
    save(fig,'08_actual_model_pipeline','The exact user video: saved intermediate stages',
         f'Track 5 is selected as a diagnostic example, not as a representative accuracy sample. '
         f'The actual D-FINE models ran on CUDA. This run’s deterministic first 32 usable IDs produced 20 partial maps, 12 failures and zero grades. '
         f'Track 5: {fruit["rotation_coverage_deg"]:.1f}° measured motion, {fruit["observed_longitude_deg"]:.1f}° observed longitude. Red overlays are model predictions, not ground truth.')

    trial=ROOT.parent/'replay-runs/accumulated_steps_v1/5/surface_map.png'
    if trial.exists():
        fig,axes=plt.subplots(1,2,figsize=(12,5));fig.subplots_adjust(top=.82,bottom=.25,wspace=.18)
        axes[0].imshow(rgb(folder/'surface_map.png'));axes[1].imshow(rgb(trial))
        axes[0].set_title('Retained configuration: partial map / no grade')
        axes[1].set_title('Rejected trial: apparent repeated landmark')
        for panel in axes:panel.axis('off')
        save(fig,'09_rejected_trial','Producing a complete-looking image is not sufficient validation',
             'An experimental accumulation of small rotations increased the numerical coverage, but visual inspection showed an apparent repeated landmark in the reconstructed map. This experiment was not enabled in production. Its source snapshot and failed validation evidence remain available. Visual inspection is qualitative and does not replace labelled 3D ground truth.')

    if api_summary:
        statuses=api_summary['statuses']
        status_names={'graded':'Grade assigned', 'insufficient_longitude_coverage':'Insufficient circumference',
                      'insufficient_surface_coverage':'Insufficient area', 'mapping_failed':'Mapping failed',
                      'insufficient_views':'Insufficient views', 'missing_defect_masks':'Missing defect masks'}
        keys=sorted(statuses,key=lambda name:statuses[name],reverse=True)
        fig,ax=plt.subplots(figsize=(11,6));fig.subplots_adjust(top=.83,bottom=.24,left=.31,right=.9)
        bars=ax.barh([status_names.get(key,key.replace('_',' ').capitalize()) for key in keys],
                     [statuses[key] for key in keys],color=[green if key=='graded' else orange for key in keys])
        ax.invert_yaxis();ax.set_xlabel('Tracked records, including incomplete and failed tracks')
        ax.set_xlim(0,max(statuses.values())*1.2);ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
        for bar,key in zip(bars,keys):
            ax.text(bar.get_width()+max(statuses.values())*.025,bar.get_y()+bar.get_height()/2,
                    f'{statuses[key]} ({statuses[key]/api_summary["fruits"]*100:.1f}%)',va='center')
        save(fig,'10_full_video_outcomes','Complete original video: every reported outcome',
             f'All 515 frames were submitted through the running application API, using the actual detector, tracker and segmenter. '
             f'The run returned {api_summary["fruits"]} tracked records; these are not manually verified unique fruit counts. '
             f'{statuses.get("graded",0)} received algorithm-assigned grades. The other outcomes are retained. Grade availability is not classification accuracy.')

        graded=sorted((row for row in api_report['fruits'] if row.get('grade')),key=lambda row:row['track_id'])
        if graded:
            sample=graded[0]
            actual_folder=ROOT.parent.parent/'results'/api_summary['job_id']/str(sample['track_id'])
            fig,axes=plt.subplots(2,3,figsize=(12,8));fig.subplots_adjust(top=.87,bottom=.18,hspace=.33,wspace=.14)
            for panel,view in zip(axes[0],sample['view_evidence']):
                panel.imshow(rgb(actual_folder/Path(view['overlay']).name))
                panel.set_title(f"Frame {view['frame']}: predicted defects",fontsize=10);panel.axis('off')
            union=None
            for url in sample['defect_maps'].values():
                mask=cv2.imread(str(actual_folder/Path(url).name),cv2.IMREAD_GRAYSCALE)>0
                union=mask if union is None else union|mask
            for panel,key,title in ((axes[1,0],'surface_map','Reconstructed surface'),
                                    (axes[1,1],'observed_mask','Observed-area mask')):
                panel.imshow(rgb(actual_folder/Path(sample[key]).name));panel.set_title(title);panel.axis('off')
            axes[1,2].imshow(union,cmap='gray',vmin=0,vmax=1);axes[1,2].set_title('Union of predicted defect masks');axes[1,2].axis('off')
            save(fig,'11_full_video_graded_example',f"Track {sample['track_id']}: first graded ID in the full run",
                 f"Selected by smallest graded track ID, not by visual quality. {sample['views']} captured views, "
                 f"{len(sample['mapped_view_frames'])} used; {sample['rotation_coverage_deg']:.1f} degrees measured motion, "
                 f"{sample['observed_longitude_deg']:.1f} degrees observed longitude, {sample['observed_surface_pct']:.2f}% observed area, "
                 f"{sample['defect_pct_of_observed']:.2f}% predicted defect on observed area: {sample['grade']}. "
                 'This demonstrates complete pipeline execution; the motion, masks and grade have not been independently labelled as correct.')
            shutil.copytree(actual_folder,out/f'full_video_track_{sample["track_id"]}')

        mapped=[row for row in api_report['fruits'] if row.get('observed_longitude_deg') is not None]
        fig,ax=plt.subplots(figsize=(10,6));fig.subplots_adjust(top=.84,bottom=.25,left=.1,right=.95)
        for accepted,color,label in ((False,orange,'Map without grade'),(True,green,'Algorithm-assigned grade')):
            rows=[row for row in mapped if bool(row.get('grade'))==accepted]
            ax.scatter([row['observed_longitude_deg'] for row in rows],
                       [row['observed_surface_pct'] for row in rows],s=35,alpha=.65,color=color,label=f'{label} (n={len(rows)})')
        ax.axvline(350,color=blue,ls='--',lw=1);ax.axhline(65,color=blue,ls='--',lw=1)
        ax.set(xlim=(0,370),ylim=(0,100),xlabel='Observed longitude (degrees)',ylabel='Observed area (%)')
        ax.legend(loc='upper left');ax.grid(alpha=.2)
        save(fig,'12_full_video_coverage','Where full-video maps stop before grading',
             f'Every one of the {len(mapped)} returned maps is plotted, including partial maps. Dashed lines are the 350-degree longitude and 65% area gates. '
             'Tracks for which mapping failed have no coverage coordinates and are counted separately in Figure 10. Numerical coverage alone does not establish correct reconstruction.')

    pdf.close()
    summary={'generated_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
             'algorithm_sha256':final['algorithm_sha256'],'author_summary':final['summary'],
             'author_map_statuses':dict(final_status),'synthetic':synthetic,
             'selected_video_outcomes':pipeline['outcomes'],'full_api_run':api_summary,
             'software_checks':checks,'software_test_count':software_test_count,
             'figure_selection':selection_records,'figures':figures}
    (out/'evidence_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    rows=[]
    for group in ('mandarins','oranges','tomatoes'):
        item=final['summary'][group];error=item['errors_px_conditional_on_prediction']
        paper={'mandarins':6.5,'oranges':2.53,'tomatoes':5.2}[group]
        rows.append(f"| {group.title()} | {item['tracks']} | {item['maps_produced']} | {item['predicted_correspondences']}/{item['labelled_correspondences']} | {error['rms']:.3f} | {error['median']:.3f} | {paper} |")
    api_text=('The complete-video API test is still running. Its result is not claimed here.' if api_summary is None else
              f"The complete original video was submitted through the actual application API. It recorded {api_summary['fruits']} fruit records. "
              f"Statuses: `{api_summary['statuses']}`. Grades: `{api_summary['grades']}`. "
              f"Saved application job: `{api_summary['job_id']}`. These are algorithm outputs, not manually validated classifications.")
    api_diagnostics=''
    if api_report:
        failures=Counter(row.get('reason','Unknown') for row in api_report['fruits'] if row['status']=='mapping_failed')
        failure_rows='\n'.join(f'| {reason} | {count} |' for reason,count in failures.most_common())
        metrics=api_report['metrics']
        api_diagnostics=(f"\nThe full video returned **{api_summary['statuses'].get('graded',0)}/{api_summary['fruits']} algorithm-assigned grades** "
                         f"({api_summary['statuses'].get('graded',0)/api_summary['fruits']*100:.2f}% availability). "
                         "This percentage measures returned grades, not grading accuracy.\n\n"
                         f"Analysis took {metrics['analysis_duration_sec']/60:.2f} minutes for a {metrics['video_duration_sec']:.1f}-second video. "
                         "The measured pipeline does not support real-time grading at this throughput.\n\n"
                         "| Mapping-failure reason | Records |\n|---|---:|\n"+failure_rows+'\n\n'
                         f"Detector calls: {metrics['detection']['calls']}; predicted instances: {metrics['detection']['instances']}. "
                         f"Segmenter calls: {metrics['segmentation']['calls']}; predicted instances: {metrics['segmentation']['instances']}. "
                         "These are inference/prediction counts, not unique fruit or unique defects.\n")
    report=f'''# Reconstruction validation and evidence

Generated: {summary['generated_at']}. All logged local times are SAST (UTC+02:00).

## Outcome and scope

The independent reconstruction implementation now fits all 36 author sequences and
produces 34 maps, including partial maps; the frozen baseline produced no maps.
It returns 458/497 labelled point predictions with RMS 5.103 px and median 2.264 px.
The deterministic first-32-track test produced **zero eligible grades**; it was not
the complete video. Full-video outcomes are reported below. Reliable grading
accuracy on the actual conveyor has **not been established**. The requested midnight
deadline was not met; this report does not claim otherwise.

{api_text}

{api_diagnostics}

## What was tested and with what

1. **Author-labelled motion:** all 578 original images in 36 sequences (15 mandarin,
   10 orange, 11 tomato); all 497 published correspondences (132/179/186).
   Five mandarin sequences have no point labels but remain in map-completion counts.
2. **Analytical geometry controls:** known oblate shape and rotations about either
   equatorial or symmetry axes; 16 views at 25° increments, expected total 375°.
3. **Known defect-area controls:** rendered sphere, known 5%, 15%, 30% masks and exact
   motion. The maximum measured area error was 0.179 percentage points, within the
   declared 1-point tolerance. All three expected grade classes passed.
4. **Coverage controls:** known 375°, 270°, 250°, 100° motion; full longitude was observed
   for the first two, while the latter two correctly remained ungraded.
5. **Model integration:** actual D-FINE detector, TrackTrack, GrabCut and the user's
   D-FINE-seg checkpoint on the exact 515-frame video
   `C:/Users/USER/Pictures/Camera Roll/WIN_20260818_13_29_43_Pro.mp4`.
   The recorded 32-track subset is the first 32 IDs with usable complete crops.
6. **Software regression:** {software_test_count} unit/integration-contract checks, including visibility,
   coordinate geometry, stationary-fruit rejection, missing-transition isolation,
   deferred segmentation, tracker identity, cancellation and inspection-history
   filtering beyond the old 60-result cutoff. Test, production-build and lint logs
   are retained in `software_checks/`, including exit codes and tested source hashes.
   A separate headless Edge check opened the real saved report, filtered Class 1,
   inspected track 125 and loaded all nine source evidence images without a page
   error. Its screenshots and observations are retained in `ui_checks/`.
7. **Optimization parity:** 42 real author pairs, scalar versus batched search;
   identical accepted rotations and rejection reasons, 8.71x faster search in this
   local microbenchmark. This is not an end-to-end speed claim.

## Method and denominators

Author masks were derived from nonblack pixels, retaining the largest component
and filling its external contour. They are not author-supplied mask ground truth.
No detector or defect network was used in the author reconstruction benchmark.
Coordinates were evaluated at the original image resolution. Annotated source points
were lifted onto the fitted spheroid, transformed by the estimated rotation and
projected into the target image. Forward and backward annotation order was respected.
Error is Euclidean pixel distance; RMS is `sqrt(mean(error_px**2))`.
Rejected predictions are counted as unavailable and never assigned zero error.

The declared calibration objects were the first object in each category (49 labels).
The remaining split has 448 labels. Because the dataset was inspected during ongoing
development, the revised results are **development-set results**, not a pristine held-out
test or an unbiased claim of field accuracy. Adjacent-pair point tests do not validate
every nonadjacent bridge introduced by view selection.

| Fruit | Sequences | Maps, including partial | Predictions / labels | RMS px | Median px | Paper Table 4 RMS px |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

The paper's values provide context, not a matched-subset comparison: it describes
roughly 200 labels per category, while the public files contain the counts above.
The revised method predicts **367/497 labels within 5 px (73.84%)** and leaves 39
unpredicted. Maximum returned error is 35.930 px. Numerical coverage eligibility is
not proof that a map is geometrically accurate or that its grade is correct.

## Comparison with the research and retained changes

The [2021 method](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) estimates shape and
motion; the [2022 method](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/) constructs
surface maps. The available author repositories provide data and an annotation viewer;
the reconstruction algorithm itself was not found in those repositories. This project
is an independent implementation, not a copy of unpublished author software.

| Component | Finding and retained implementation |
|---|---|
| Spheroid reference frame | The short symmetry axis is not always the roller axis. Map axes, radii and area weights now remain consistent. |
| Silhouette pose | A custom exact rigid-pose gate rejected 27/36 reference sequences. The retained method follows the paper's silhouette trend. |
| Matching objective | The paper uses unnormalized MAD. The original normalized objective was different. MAD now drives search; normalized residuals gate matches. |
| Matching robustness | Bidirectional MAD is a separately evaluated engineering extension. It reduces large errors, with availability reported alongside error. |
| View spacing | Fruit can slip. Constant pair rotations are not required. Later texture matches which pass the residual gate may bypass unusable views; disconnected segments are not joined. These are algorithmic checks, not ground-truth verification. |
| Rotation versus coverage | Endpoint pre/post-roll observes additional surface. The gate uses actual observed longitude, while physical rotation remains a separate measurement. |
| Defect model | The user's checkpoint runs on each retained map-contributing crop. Deferred inference avoids processing discarded views, but occurs before the final coverage check, so partial maps can also contain predicted defects. |
| Grading | Area thresholds 10% and 20% are local engineering settings. The 2022 paper's learned map classifier is a different grading method. Its classification accuracy cannot be claimed for this pipeline. |

Current coverage gates are at least 350° observed map longitude and 65% observed
area. Latitude is restricted to ±60°; the polar caps remain unobserved. Grade 1 is
below 10% defect on observed area; Grade 2 is 10–20% inclusive; Grade 3 exceeds 20%.
These numerical settings are not a validated commercial grading specification.

## Exact-video findings and remaining discrepancy

The original clip has 515 distinct frames at 29.746 fps; global duplicate-frame
filtering does not explain its failures. In the 32-track integration test, 20 partial
maps and 12 failures were saved. Detection and segmentation calls completed, but
reconstruction did not establish sufficient reliable coverage for a grade.
Some crops visibly rotate while the motion matcher underestimates their motion.
Reflections, silhouette/pose noise and local matching ambiguity are plausible causes;
their individual causal contributions have not been experimentally isolated.

{api_text}

The dashboard's 711 Review entries in the original screenshot are historical
records from three saved runs. A new analysis adds a new report; it does not alter
those old records. The history previously stopped at 60 records BEFORE applying
class filters, which could hide later graded fruit. History now exposes all saved
records to filtering while keeping verbose motion diagnostics in the download.

The paper uses diffuse illumination to avoid highlights. This video has visible glare.
The setup also contains occluded, truncated, briefly observed and nonrotating fruit.
Those conditions must be separated from algorithm failures. A controlled next test
should use one identifiable fruit, a fixed overhead camera, diffuse lighting and a
manually verified complete turn. Mark 10–20 corresponding points across its rotation,
and record repeated features at loop closure. Only then can motion accuracy and
defect de-duplication on this camera be established. A separate labelled defect/grade
test is needed to measure the user's neural model and final grading accuracy.

Optical-flow matching, smooth pose selection, frame thinning and small-motion
accumulation were tried as isolated experiments. They did not provide convincing
improvement; the accumulation trial showed apparent feature duplication despite
greater numerical coverage. These trials are preserved but excluded from the retained
production algorithm. A complete-looking map was not accepted as proof of correctness.

## Evidence provenance and reproducibility

Retained algorithm SHA-256: `{final['algorithm_sha256']}`.
Detector SHA-256: `{pipeline['detector_sha256']}`.
Segmenter SHA-256: `{pipeline['segmenter_sha256']}`.
Exact video SHA-256: `{pipeline['video_sha256']}`.

Pinned author repositories:

- [Rotation data](https://github.com/alalbiol/3d-rotation-estimation-fruits/tree/f20d6757052388c4f86048a0d5f7ad015c29bb08), commit `f20d6757052388c4f86048a0d5f7ad015c29bb08`.
- [Surface map data](https://github.com/csdemeras/FSMap/tree/4e148a1b436374948a9102ad39cdc4d5b3e36eb3), commit `4e148a1b436374948a9102ad39cdc4d5b3e36eb3`.

The original files, licenses and per-file SHA-256 / Git blob checksums are retained
under `data/` and `source_manifest.json`. Every experimental run has its own settings,
source snapshot and results. Historical results have not been overwritten.
See `DEVELOPMENT_LOG.md` for the sequence of successful and unsuccessful experiments.

Run from the project root in PowerShell, using a NEW label each time:

```powershell
./backend/venv/Scripts/python.exe -B -m unittest discover -s backend -p 'test_*.py'
./backend/venv/Scripts/python.exe -B backend/benchmark_authors.py run --label NEW_AUTHOR_RUN --groups mandarins oranges tomatoes --direction -1 --bidirectional --select-views --minimum-rotation 0 --minimum-longitude 350
./backend/venv/Scripts/python.exe -B backend/validate_synthetic_mapping.py --label NEW_SYNTHETIC_RUN
./backend/venv/Scripts/python.exe -B backend/validate_pipeline_video.py 'C:/Users/USER/Pictures/Camera Roll/WIN_20260818_13_29_43_Pro.mp4' --label NEW_VIDEO_RUN --track-limit 32 --bidirectional
./backend/venv/Scripts/python.exe -B backend/validate_api_video.py 'C:/Users/USER/Pictures/Camera Roll/WIN_20260818_13_29_43_Pro.mp4' --label NEW_FULL_API_RUN
./backend/venv/Scripts/python.exe -B backend/validate_software_checks.py --label NEW_SOFTWARE_CHECKS
```

To replay an archived experimental implementation, `benchmark_authors.py` and
`replay_pipeline_crops.py` accept `--algorithm-snapshot PATH`. Source hashes and
settings must match the intended experiment; do not substitute a later implementation
while citing an earlier result. The dashboard totals aggregate historical saved runs;
old Review records are not retroactively reclassified by editing code.

## Figure captions

'''
    for number,item in enumerate(figures,1):
        report+=f"### Figure {number}. {item['title']}\n\n{item['caption']}\n\n![{item['title']}]({item['file']})\n\n"
    (out/'VALIDATION_REPORT.md').write_text(report,encoding='utf-8')
    cards=''.join(f'<section><h2>{i+1}. {html.escape(item["title"])}</h2><a href="{item["file"]}"><img src="{item["file"]}" alt="{html.escape(item["title"])}"></a><p>{html.escape(item["caption"])}</p></section>' for i,item in enumerate(figures))
    webpage=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Fruit reconstruction validation evidence</title><style>body{{font:16px/1.6 system-ui,sans-serif;color:#243d39;background:#f3f5f1;margin:0}}main{{max-width:1150px;margin:auto;padding:36px 24px}}h1{{font-size:36px;line-height:1.2}}h2{{font-size:23px}}section{{background:white;padding:24px;margin:28px 0;border:1px solid #dce5dd;border-radius:8px}}img{{width:100%;height:auto}}a{{color:#237c61}}.notice{{border-left:5px solid #c48129;padding:12px 20px;background:#fff8e9}}small{{color:#60766c}}</style><main><small>TEST EVIDENCE · 2 OCTOBER 2026</small><h1>Fruit reconstruction validation</h1><p class="notice">Reference reconstruction improved. Reliable grading on the user's conveyor has not yet been established. Partial maps and failures are included.</p><p><a href="VALIDATION_REPORT.md">Full methodology and findings</a> · <a href="validation_figures.pdf">PDF figures</a> · <a href="evidence_summary.json">Machine-readable results</a></p>{cards}</main></html>'''
    (out/'index.html').write_text(webpage,encoding='utf-8')
    for name,path in (('author_results.json',ROOT/'runs/operational_profile_v1/report.json'),
                      ('author_algorithm_snapshot.py',ROOT/'runs/operational_profile_v1/algorithm_snapshot.py'),
                      ('source_manifest.json',ROOT/'source_manifest.json'),
                      ('video_subset_results.json',pipeline_root/'report.json'),
                      ('development_log.md',ROOT/'DEVELOPMENT_LOG.md')):
        shutil.copyfile(path,out/name)
    if api_summary:
        shutil.copyfile(api_root/'response.json',out/'full_video_api_results.json')
        shutil.copyfile(api_root/'summary.json',out/'full_video_api_summary.json')
        shutil.copyfile(api_root/'request.json',out/'full_video_api_request.json')
        snapshots=ROOT.parent.parent/'results'/api_summary['job_id']
        for path in snapshots.glob('*.snapshot'):
            shutil.copyfile(path,out/path.name)
    if checks:
        shutil.copytree(checks_root,out/'software_checks')
    licenses=out/'source_licenses';licenses.mkdir()
    for group in ('rotation','maps'):
        shutil.copyfile(DATA/group/'LICENSE',licenses/f'{group}_LICENSE')
    ui_root=ROOT.parent/'ui-checks/final_20261002'
    if ui_root.exists():shutil.copytree(ui_root,out/'ui_checks')
    source_folder=out/'validation_scripts';source_folder.mkdir()
    for name in ('benchmark_authors.py','benchmark_mapping_reference.py','validate_synthetic_mapping.py',
                 'validate_rotation_search_parity.py','validate_pipeline_video.py','replay_pipeline_crops.py',
                 'validate_api_video.py','validate_software_checks.py','build_validation_evidence.py'):
        shutil.copyfile(ROOT.parent.parent/name,source_folder/name)
    with zipfile.ZipFile(out/'report_evidence.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in out.rglob('*'):
            if path.is_file() and path.name!='report_evidence.zip':archive.write(path,path.relative_to(out))
    print(json.dumps({'directory':str(out),'figures':len(figures),'full_video_complete':api_summary is not None},indent=2))


if __name__=='__main__':main()
