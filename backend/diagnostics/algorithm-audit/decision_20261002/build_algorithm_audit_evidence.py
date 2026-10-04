"""Bundle isolated algorithm-decision tests without altering production results."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    args=parser.parse_args()
    backend=Path(__file__).resolve().parent
    diagnostics=backend/'diagnostics'
    author=diagnostics/'authors-benchmark'
    output=diagnostics/'algorithm-audit'/args.label
    output.mkdir(parents=True,exist_ok=False)
    collections={
        'corrected_tracks':diagnostics/'algorithm-audit/corrected_tracks_20261002',
        'longitude_failure':diagnostics/'algorithm-audit/longitude_failure_491_20261002',
        'dominance_candidate':diagnostics/'algorithm-audit/rotation_dominance_20261002',
        'author_bridge_baseline':author/'bridge_runs/selected_bridges_checks_20261002',
        'author_bridge_candidate':author/'bridge_runs/candidate_bridge_guard_050_20261002',
        'author_candidate_full_benchmark':author/'runs/candidate_bridge_guard_050_20261002',
        'candidate_bridge_source':author/'bridge_runs/residual_guard_candidate_source',
    }
    for name,source in collections.items():
        shutil.copytree(source,output/name)
    license_folder=output/'author_provenance';license_folder.mkdir()
    for name in ('rotation_LICENSE','maps_LICENSE'):
        shutil.copy2(author/'evidence_20261002/source_licenses'/name,license_folder/name)
    shutil.copy2(author/'source_manifest.json',license_folder/'source_manifest.json')
    shutil.copy2(author/'runs/operational_profile_v1/report.json',output/'author_full_baseline.json')
    for name in ('algorithm.py','main.py','dfine_segmenter.py','validate_algorithm_decision.py',
                 'validate_author_bridges.py','validate_longitude_failure.py',
                 'validate_rotation_dominance.py','build_longitude_failure_figure.py',
                 'benchmark_authors.py','build_author_bridge_evidence.py',
                 'build_algorithm_audit_evidence.py'):
        if (backend/name).is_file():shutil.copy2(backend/name,output/name)
    corrected=json.loads((output/'corrected_tracks/report.json').read_text())
    baseline=json.loads((output/'author_bridge_baseline/report.json').read_text())
    candidate=json.loads((output/'author_bridge_candidate/report.json').read_text())
    prior_original=json.loads((output/'author_full_baseline.json').read_text())
    full_candidate=json.loads((output/'author_candidate_full_benchmark/report.json').read_text())
    s0,s1=baseline['summary'],candidate['summary']
    a0,a1=s0['original_published_labels'],s1['original_published_labels']
    bridge_rows='\n'.join(f'| {row["group"]}/{row["object"]} | {row["source"]}→{row["target"]} | '
                          f'{row["error_px"]:.2f} | {", ".join(map(str,row["author_annotation_lines"]))} |'
                          for row in baseline['bridge_endpoint_pairs'])
    case=next(row for row in corrected['tracks'] if row['corrected_id']==98)
    sensitivity='\n'.join(f'| {row["name"]} | {row.get("rotation_deg",0):.2f} | {row.get("longitude_deg",0):.2f} |'
                          for row in case['variants'])
    def eligible(report):
        return sum(row.get('map',{}).get('result_status')=='missing_defect_masks' for row in report['tracks'])
    number_baseline=eligible(prior_original);number_candidate=eligible(full_candidate)
    assert (number_baseline,number_candidate)==(17,13)
    document=f'''# Does the reconstruction algorithm need to change?

Recorded {datetime.now(timezone(timedelta(hours=2))).isoformat()}.

## Decision

**Yes: the motion-matching and view-selection adaptation needs correction and
validation.** The current tests have not identified a new algebraic error in the
spheroid equations, image lifting, surface coordinates or area Jacobian. They do
identify accepted bad skipped-frame matches and a mismatch between accepted
rotation vectors and the map's required longitude order.

The two tested quick safeguards remain experimental. Neither establishes accurate
conveyor reconstruction. Production algorithm/API/model-adapter bytes are unchanged
from the beginning of this audit. Existing saved maps and grades are not replaced.
The user's detection and defect-segmentation checkpoints are unchanged.

## 1. Verify motion on author data, including skipped frames

All 497 published correspondences connect adjacent images. The earlier benchmark
reported 458 predictions with RMS 5.103 pixels by checking adjacent estimates. That
result did not validate every longer transition introduced by the selector.

This audit reconstructs label chains only where one published target coordinate
exactly equals another published source coordinate for the same fruit and image.
No coordinate interpolation, fitted motion or model prediction supplies the endpoint
truth. The original annotation line numbers and chain paths are retained.

The production selector retained {s0['nonadjacent_selected_bridges']} nonadjacent
transitions across the 36 sequences. Only four had exact chained feature endpoints.
All four were accepted by the residual gate, but missed the endpoints by more than
five pixels:

| Author fruit | Image pair | Endpoint error, pixels | Original annotation lines |
| --- | --- | ---: | --- |
{bridge_rows}

The four-endpoint RMS is 29.291 pixels. All endpoints lift finitely onto the visible
side of the estimated surface. Two lifted endpoint separations exceed the search's
maximum total angle (~55.90°); this is a model-based indication of an insufficient
search domain, not measured physical rotation. A long unknown gap can alias to an
apparently acceptable small rotation. Sixteen other baseline bridges have no exact
chain verification and must not be counted as correct.

The chained observations are correlated development evidence, separate from the
original 497-label denominator. Four labelled bridges do not establish general
bridge accuracy. [Detailed author audit](author_bridge_baseline/BRIDGE_AUDIT.md)
and its raw JSON retain projections, masks, chain provenance and composition checks.

## 2. Reproduce an actual map-ordering failure

Original fruit 491 is replayed using the cached original detector boxes and exact
video, without neural inference. All 75 box observations match the earlier tracking
cache exactly. Fresh GrabCut yields 59 usable crops versus the historical 60;
three retained mask comparisons have IoU 0.9953–0.9997. Thus this is a reproducible
failure on fresh masks, not byte-identical replay of every historical mask.

At frames 305→306, the selector accepts Rodrigues components x = +3.005° and
y = −5.262°, yet the map's fruit-fixed longitude moves backwards by 1.782°.
The selector tests the magnitude of the configured rolling component, whereas
surface fusion requires a consistently ordered longitude trajectory. Sideways
motion exceeds forward rolling motion in this accepted pair. The later order check
then rejects the entire selected segment.

![Actual source crops and the backwards map transition](longitude_failure/longitude_failure_comparison.png)

A sphere control avoids that ordering error but reaches only 214.58° observed
longitude. Changing every naartjie to a sphere is not supported by this outcome.
No manually measured motion truth was available to distinguish real wobble from
a false transverse texture match. [Full trace and methodology](longitude_failure/AUDIT.md).

## 3. Hold actual corrected-track crops fixed and change one assumption

The corrected tracker output is matched to original baseline IDs 125, 1 and 14.
These are one formerly numerically graded example and the first two recorded
objects, not a random or held-out sample. Each configuration receives identical
preserved crops and masks. Detection and defect inference are not rerun.

Corrected ID 98 has 66 complete crops, frames 62–127, while its tracked identity
spans frames 51–138. Its partial edge observations preserve tracking but do not
provide the complete silhouette required by the spheroid estimator.

| Same corrected fruit 98 | Estimated rotation | Observed longitude |
| --- | ---: | ---: |
{sensitivity}

The current x/positive/auto/d4 setting yields 241.03° estimated rolling motion and
335.59° observed longitude. The historical ID 125 run reported 380.96° / 360°.
That historical comparison changes both detector boxes and stochastic mask
extraction; it cannot isolate the cause. The within-experiment variants DO hold
all images and masks fixed and show substantial estimator/selection sensitivity.

All 15 combinations on the three corrected tracks remain below the 350° longitude
gate. Neither changing axis, direction, shape nor resolution demonstrated a reliable
full map. Coverage is not geometric accuracy. There are no defect masks or grades
in these tests. Each plotted cumulative curve starts at zero for its retained
segment; configurations can retain different starting frames.

![Identical crops under isolated assumptions](corrected_tracks/algorithm_sensitivity.png)

## 4. Test proposed safeguards before enabling them

**Skipped-frame residual guard:** an isolated algorithm snapshot rejects a bridge
over more than one captured-view index when normalized residual exceeds 0.5.
The threshold was chosen after inspecting these development failures; it is not
an independently validated confidence boundary.

- Nonadjacent bridges decrease {s0['nonadjacent_selected_bridges']}→{s1['nonadjacent_selected_bridges']}.
  All four known bad chained bridges are excluded. The remaining four lack exact
  chain truth, so this is not a measured zero-error bridge result.
- Predictions for original adjacent labels whose endpoints survive selection
  decrease {a0['returned_predictions']}→{a1['returned_predictions']}/497.
  Conditional RMS changes {a0['errors_px_conditional_on_prediction']['rms']:.3f}→
  {a1['errors_px_conditional_on_prediction']['rms']:.3f} pixels; these are different
  subsets, not an improvement comparison on a fixed denominator.
- The independent adjacent benchmark remains exactly 458/497 and 5.103 pixels RMS.
  Geometry still fits 36/36 and maps are still produced for 34/36, but coverage-eligible
  maps decrease {number_baseline}→{number_candidate}; partial maps increase 17→21.
- The guard still accepts some long gaps with unverified endpoints. A stricter
  residual alone does not resolve unknown angular motion or texture ambiguity.

**Rolling-axis dominance guard:** an isolated wrapper rejects a pair when a
transverse Rodrigues component exceeds the configured rolling component. On the
same frozen fruit-491 inputs, the ordering failure becomes an ordered partial map
with 124.58° longitude. Corrected fruit 98 stays at 335.59°; fruit 1 increases from
110.66° to 147.31°, while fruit 14 decreases from 151.90° to 118.44°. None of the four
becomes coverage eligible. This guard fixes a specific incompatible transition but
has not demonstrated motion accuracy or an overall reconstruction improvement.

Both candidates and their before/after JSON remain in this package. They are not
enabled in the running application.

## What should change next

The next implementation should verify a skipped-frame join before using it in
surface fusion, distinguish measured small motion from failed/unmeasured motion,
and test the resulting fruit-fixed trajectory before accepting a connected segment.
An eight-image gap cap cannot express the same angular bound on the author sequence
and a densely sampled conveyor clip. Confidence must include motion ambiguity and
support across intermediate views, with evaluated prediction availability.

Use the four exact author chains, all original labels, and the reproduced 491
ordering failure as regression cases. Then use independently marked conveyor
landmarks and a verified complete turn to evaluate motion; visible image repetition
or a complete-looking map alone is insufficient. Defect-model and final-grade
accuracy remain separate tests after reconstruction passes.

The live-camera scheduler is a separate setup issue: it retains only the latest
camera frame and performs mapping in the processing loop. The recorded-video
tests do not establish that every live sensor frame is processed. A live queue,
timing and scheduling test is required before claiming immediate real-time entry
tracking or grading.

## Evidence and reproducibility

This folder retains real crops/masks/NPZ inputs, projected author points, selection
and longitude traces, all variants, candidate source, production source snapshots,
300-dpi PNG/PDF figures and checksums. Original author datasets, video and model
weights remain at their workspace paths; the full datasets are not duplicated here.
Source manifest URLs and checksums identify the pinned author data.

The research basis is the [2021 rotation method](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/)
and [2022 surface-map method](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
This project is an independent implementation with an added capture/view-selection
stage. The new failures do not establish that the authors' unavailable source code
contains the same defects.

Run the isolated tests from the project root, using fresh labels:

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_algorithm_decision.py --label NEW_SENSITIVITY
./backend/venv/Scripts/python.exe -B backend/validate_longitude_failure.py --label NEW_LONGITUDE
./backend/venv/Scripts/python.exe -B backend/validate_rotation_dominance.py --label NEW_DOMINANCE
```

The author bridge audit's exact commands, reference report and candidate source
hash are in `author_bridge_baseline/BRIDGE_AUDIT.md` and the accompanying JSON.
The previous sealed reports and their historical grades remain unchanged.
'''
    (output/'ALGORITHM_DECISION.md').write_text(document,encoding='utf-8')
    figures=[('Author skipped-frame errors',path) for path in sorted((output/'author_bridge_baseline').glob('*.png'))]
    figures+=[('Actual backwards map transition',output/'longitude_failure/longitude_failure_comparison.png'),
              ('Same crops, isolated algorithm assumptions',output/'corrected_tracks/algorithm_sensitivity.png')]
    sections=''.join(f'<section><h2>{html.escape(title)}</h2><a href="{path.relative_to(output).as_posix()}">'
                    f'<img src="{path.relative_to(output).as_posix()}" alt="{html.escape(title)}"></a></section>'
                    for title,path in figures)
    (output/'index.html').write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Algorithm decision evidence</title><style>body{{font:17px/1.6 system-ui;background:#f5f6f3;color:#14231b;margin:0}}main{{max-width:1100px;margin:auto;padding:32px 24px}}h1{{line-height:1.2}}img{{width:100%;background:white}}section{{margin:44px 0}}a{{color:#176847}}</style>
<main><p>Actual author labels and original conveyor crops · Isolated geometry tests</p><h1>The motion-selection stage needs correction</h1>
<p>Four accepted skipped-frame author matches miss their labelled endpoints by 16–41 pixels. A real conveyor transition produces backwards map longitude. Two tested safeguards remain experimental.</p>
<p><a href="ALGORITHM_DECISION.md">Full testing report and decision</a> · <a href="algorithm_audit_evidence.zip">Evidence ZIP</a></p>
<p>Production code is unchanged. These tests contain no defect inference or new grade claims.</p>{sections}</main></html>''',encoding='utf-8')
    for name,expected in corrected['source_sha256'].items():
        if name in ('algorithm.py','main.py','dfine_segmenter.py'):
            assert hashlib.sha256((backend/name).read_bytes()).hexdigest()==expected
    summary={'built_at':datetime.now(timezone(timedelta(hours=2))).isoformat(),
             'production_sources_unchanged':True,'decision':'Correct and validate motion matching/view selection; candidates remain isolated.',
             'labelled_bad_bridges':4,'conveyor_tracks_in_shape_controls':3,'shape_control_combinations':15,
             'dominance_guard_tracks':4,'neural_models_rerun':False,'new_grade_claims':False}
    (output/'audit_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    files=sorted(path for path in output.rglob('*') if path.is_file())
    sums=''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(output).as_posix()+'\n' for path in files)
    (output/'SHA256SUMS.txt').write_text(sums,encoding='utf-8')
    with zipfile.ZipFile(output/'algorithm_audit_evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files+[output/'SHA256SUMS.txt']:archive.write(path,path.relative_to(output).as_posix())
    with zipfile.ZipFile(output/'algorithm_audit_evidence.zip') as archive:
        assert archive.testzip() is None
        print(json.dumps({**summary,'zip_files':len(archive.namelist()),'zip_bytes':(output/'algorithm_audit_evidence.zip').stat().st_size},indent=2))


if __name__=='__main__':main()
