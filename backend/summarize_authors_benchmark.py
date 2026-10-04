"""Create a readable report and diagnostic figure from saved benchmark runs."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from benchmark_authors import ROOT, DATA, load_views, save_correspondence_view, stats


def load(name):
    return json.loads((ROOT/'runs'/name/'report.json').read_text())


def group_metrics(report, group=None):
    tracks=[t for t in report['tracks'] if group is None or t['group']==group]
    rows=[r for r in report['correspondences'] if group is None or r['group']==group]
    good=[r for r in rows if r['status']=='ok']
    return {'tracks':len(tracks),'geometry_ok':sum(t['geometry']['status']=='ok' for t in tracks),
            'maps':sum(t['map']['status']=='produced' for t in tracks),
            'labels':len(rows),'predicted':len(good),
            'errors_px':stats([r['error_px'] for r in good]),
            'baseline_px_same_subset':stats([r['center_translation_baseline_px'] for r in good]),
            'all_labels_within_5px':sum(r['error_px']<=5 for r in good),
            'pair_count':sum(t['views']-1 for t in tracks),
            'pairs_accepted':sum(p['status']=='ok' for t in tracks for p in t['pairs'])}


def first_failure(track):
    if track['geometry']['status']!='ok': return 'Shape / pose fit'
    reason=track['map'].get('reason','')
    if reason.startswith('Fruit has insufficient'): return 'Texture gate'
    if reason.startswith('Unreliable pair'): return 'Rotation pair gate'
    if reason.startswith('A pair rotation disagrees'): return 'Sequence uniformity gate'
    return reason or 'Map produced'


def figures(report, sphere):
    groups=['mandarins','oranges','tomatoes']
    fig,axes=plt.subplots(1,2,figsize=(12,4.2),layout='constrained')
    colors=['#ca7a22','#d98d2b','#be5147']
    x=np.arange(3)
    totals=[group_metrics(report,g)['labels'] for g in groups]
    predicted=[group_metrics(report,g)['predicted'] for g in groups]
    axes[0].bar(x,totals,color='#e1e4e7',label='All author labels')
    axes[0].bar(x,predicted,color=colors,label='Prediction available')
    for i,(n,d) in enumerate(zip(predicted,totals)):
        axes[0].text(i,d+4,f'{n}/{d}',ha='center')
    axes[0].set(xticks=x,xticklabels=[g.title() for g in groups],ylabel='Annotated correspondences',
                title='Most reference points receive no prediction',ylim=(0,220))
    axes[0].legend(frameon=False)
    counts=Counter(first_failure(t) for t in report['tracks'])
    axes[1].barh(list(counts),list(counts.values()),color=['#be5147','#ca7a22','#718091','#596678'])
    for i,n in enumerate(counts.values()): axes[1].text(n+.3,i,str(n),va='center')
    axes[1].set(xlabel='Fruit sequences',title='0 of 36 complete maps',xlim=(0,31))
    axes[1].invert_yaxis()
    for ax in axes:
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Author-data benchmark: existing algorithm, dataset rotation direction',fontsize=13)
    fig.savefig(ROOT/'benchmark_summary.png',dpi=170)
    plt.close(fig)

    # Chosen illustrations are explicitly examples, not aggregate proof.
    examples=[('accepted_example',report,'mandarins','obj0007',108),
              ('sphere_error_example',sphere,'mandarins','obj0006',80)]
    for name,source,group,obj,line in examples:
        row=next(r for r in source['correspondences'] if r['group']==group and r['object']==obj and r['line']==line)
        views=load_views(DATA/'rotation'/'data'/group/obj,0)
        save_correspondence_view(ROOT/f'{name}.png',views,row,np.array(row['prediction']))

    ref=cv2.cvtColor(cv2.imread(str(DATA/'maps/mandarin/unrolled_objM0001.png')),cv2.COLOR_BGR2RGB)
    fig,axes=plt.subplots(2,1,figsize=(10,6),layout='constrained')
    axes[0].imshow(ref); axes[0].set_title('Published author map: mandarin objM0001'); axes[0].axis('off')
    axes[1].set_facecolor('#f5eeee'); axes[1].set_xticks([]); axes[1].set_yticks([])
    axes[1].text(.5,.65,'Existing code produced no map',ha='center',va='center',fontsize=18,color='#9b2e2e')
    axes[1].text(.5,.38,'Stopped at: no consistent oblate pose sequence through pair 6',
                 ha='center',va='center',fontsize=11,wrap=True)
    axes[1].text(.5,.12,'Input: 14 views extracted without resizing from the authors\' published montage.',
                 ha='center',va='center',fontsize=10)
    fig.savefig(ROOT/'map_comparison.png',dpi=150)
    plt.close(fig)


def main():
    primary=load('dataset_orientation')
    sphere=load('sphere_diagnostic')
    plus=load('direction_plus_exact_black')
    sensitivity=load('current_settings')
    mapping=json.loads((ROOT/'map_reference/report.json').read_text())
    current_hash=hashlib.sha256(Path(__file__).with_name('algorithm.py').read_bytes()).hexdigest()
    assert current_hash==primary['algorithm_sha256']==sphere['algorithm_sha256']==plus['algorithm_sha256']
    assert len(primary['tracks'])==36 and len(primary['correspondences'])==497
    manifest=json.loads((ROOT/'source_manifest.json').read_text())
    # Verify downloaded source provenance again without contacting the network.
    for item in manifest['files']:
        assert hashlib.sha256((ROOT/item['file']).read_bytes()).hexdigest()==item['sha256'],item['file']
    labels_outside=[]
    for row in primary['correspondences']:
        for role in ('source','target'):
            path=DATA/'rotation/data'/row['group']/row['object']/f"im{row[role]:02d}.png"
            image=cv2.imread(str(path)); x,y=row[f'{role}_xy']
            if not (0<=x<image.shape[1] and 0<=y<image.shape[0]): labels_outside.append(row)
    assert not labels_outside, 'Ground-truth coordinate convention needs review'
    summary={label:{group:group_metrics(report,None if group=='all' else group)
                    for group in ['all','mandarins','oranges','tomatoes']}
             for label,report in [('dataset_orientation',primary),('sphere_diagnostic',sphere),
                                   ('direction_plus_exact_black',plus),('threshold8_plus_direction',sensitivity)]}
    summary.update(algorithm_sha256=current_hash,source_integrity_verified=True,
                   annotated_endpoints_inside_images=994, supplemental_mapping=mapping)
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    figures(primary,sphere)
    table=[]
    paper={'mandarins':6.5,'oranges':2.53,'tomatoes':5.2}
    for group in ['mandarins','oranges','tomatoes']:
        m=summary['dataset_orientation'][group]
        rms=f"{m['errors_px']['rms']:.2f}" if m['predicted'] else 'Not measurable'
        table.append(f"| {group.title()} | {m['tracks']} | {m['geometry_ok']}/{m['tracks']} | {m['maps']}/{m['tracks']} | {m['predicted']}/{m['labels']} | {rms} | {paper[group]} |")
    failure_counts=Counter(first_failure(t) for t in primary['tracks'])
    rows='\n'.join(f"| {t['group']}/{t['object']} | {t['views']} | {t['geometry']['status']} | {sum(p['status']=='ok' for p in t['pairs'])}/{t['views']-1} | {t['map'].get('reason',t['map']['status'])} |" for t in primary['tracks'])
    report=f'''# Author-data reconstruction benchmark — 1 October 2026

**Result: the current implementation does not pass the end-to-end reference-data test.**
With the dataset's rotation direction, it produces **0 maps from 36 fruit sequences**.
This failure is reproducible without the user's detector, tracker, defect model,
GrabCut, video decoding, GPU inference, API, or dashboard.

Production `algorithm.py` was not edited. Its SHA-256 is `{current_hash}`.
The new scripts and evidence live separately under `backend/diagnostics/authors-benchmark`.

## What was tested

- All 578 individual images in the pinned 2021 authors' repository: 15 mandarin,
  10 orange, and 11 tomato sequences. Five mandarin sequences have no point annotations;
  they still count in geometry/map completion.
- All 497 published point correspondences: 132 mandarin, 179 orange, 186 tomato.
  Both forward and backward annotations are respected; points are never used to fit rotations.
- Each accepted rotation lifts an annotated source pixel into 3D, rotates it and
  projects it into the target view. Error is Euclidean pixel distance; RMS is
  `sqrt(mean(error_px**2))`. Rejected predictions are counted separately, never assigned zero error.
- The per-fruit centre-translation baseline uses exactly the same predicted subset.
- Author images already have black backgrounds. Masks are derived from nonblack pixels,
  retaining the largest component and filling enclosed holes. These are derived masks,
  not independently supplied ground-truth silhouettes. Original pixels are not resized before fitting.
- The source images show downward feature motion. With this code's positive visible
  z coordinate and image y increasing downward, this needs x-axis direction -1.
  Direction +1 is a separate control, not the correctness score.
- First object of each category is marked calibration (49 labels); remaining 33
  sequences / 448 labels are marked evaluation. No learned parameter fitting was done.
  All 81 accepted predictions in the primary run belong to the evaluation split.
- Source download checksums and all 994 annotation endpoint bounds were verified.

## Measurements

| Fruit | Sequences | Shape fits | Maps | Available predictions / labels | Our RMS on available predictions (px) | Paper Table 4 RMS (px) |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(table)}

**Do not interpret the low mandarin RMS as outperforming the paper.** Our code only
returns 34 of its 132 mandarin correspondences. The paper's numbers are a reference
scale, not a matched-subset comparison: it describes about 200 labels per category,
whereas the public files contain the counts above. Overall prediction availability
is 81/497 (16.3%); held-out availability is 81/448 (18.1%). Full-map success is zero.

First failing stage per sequence: {dict(failure_counts)}.

![Benchmark summary](benchmark_summary.png)

## Controlled checks

| Check | Result | Meaning |
|---|---|---|
| Current auto shape, direction +1 | 9/36 shape fits; 0/36 maps; 3/497 predictions | Wrong direction for these 2021 images is harmful. |
| Auto shape, direction -1 | 9/36 shape fits; 0/36 maps; 81/497 predictions | Correcting direction does not repair reconstruction. |
| Force sphere, direction -1 (diagnostic only) | 36/36 shape fits; 0/36 maps; 294/497 predictions | Bypassing the oblate solver exposes further texture/sequence failures. |
| Black threshold 8 versus 0, direction +1 | Same fit/map/prediction counts | This small threshold change does not explain the baseline failure. |
| Exact geometry and exact 25-degree steps, symmetry-axis rotation | Map produced; 375 degrees recovered | Map stage can work in a favourable configuration. |
| Same exact inputs, equatorial-axis rotation | `No consistent angular progress` | A downstream coordinate-system defect remains even with perfect inputs. |

Forcing a sphere is not a proposed fix: its accepted mandarin predictions have RMS
10.19 px and errors up to 42.21 px. The sphere diagnostic changes the shape assumption,
not the production code or accuracy thresholds. Its accepted-subset overall RMS is
8.05 px; 203/497 correspondences still have no prediction.

An accurately aligned example from the primary run (mandarin obj0007, annotation 108,
0.19 px error; selected to illustrate a success, not represent all results):

![Accepted feature alignment](accepted_example.png)

A failure of the sphere approximation (mandarin obj0006, annotation 80, 42.21 px error;
selected to illustrate why bypassing the shape solver is insufficient):

![Sphere diagnostic error](sphere_error_example.png)

## Comparison with the papers

The [2021 paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) supplies the shape and
rotation method. The [2022 paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/) supplies
map construction. The following is a source/code review, not a claim to possess the authors' software.

| Component | Code comparison | Consequence |
|---|---|---|
| Silhouette covariance, sphere radius, oblate radii | The basic equations match (2021 Eqs. 1, 4, 5). | These formulas are not by themselves evidence that the whole pipeline is correct. |
| Green channel, 4x reduction, Gaussian high-pass, strong point selection | Broadly follows 2021 section 3.3. | Local minimum texture, minimum point and maximum point gates are extra settings. |
| Oblate pose ambiguity | Code replaces the paper's minor-axis trend/smoothing procedure with a constrained sign-sequence solver. | This custom stage rejects 27/36 primary sequences. It needs direct investigation. |
| Matching cost | Code divides absolute difference by a candidate-dependent texture scale; Eq. 17 uses mean absolute difference. | This can change the best rotation, not merely rescale a rejection threshold. |
| Pair and sequence acceptance | Code adds 1-degree minimum motion, error/texture limits, and a median-step uniformity gate. | A single rejected pair aborts the map. These choices are not validated by the dataset. |
| Map coordinate axes | 2022 section 2.1 places fruit y near the rotation axis. Code always makes oblate fruit y the short symmetry axis. | These differ for equatorial rolling. Exact-geometry diagnostic reproduces the failure. |
| Map sampling and blending | General parametrization and adjacent-view linear blending follow 2022 Eqs. 3 and 6. | Correct formulas do not rescue inconsistent axes or rejected rotations. |
| Grading | Local 350-degree, 65-percent and 10/20-percent settings are application choices. | No defect/grade ground truth was supplied in this benchmark; no grade accuracy is claimed. |

The exact-geometry diagnostic injects a known spheroid and analytical rotations into
map construction using scoped mocks, solely in the standalone benchmark process.
It does not measure detector accuracy or full reconstruction accuracy. At the
reference pose the short fruit axis is vertical. Rotation about that axis succeeds;
rotation about horizontal x fails. This isolates the map's coordinate assumption
from tracking, silhouette noise, motion estimation and the user's camera.

## Comparison with published maps

Two published FSMap mandarin examples were also checked. Their two-row montages were
split into 14 and 13 views at original pixel scale. View bounds are saved in
`map_reference/report.json`. These composite views have already been processed by
the authors; objM0005 contains visible background artifacts. They are supplementary
checks, not pristine raw-input benchmarks. Both abort at pose fitting. No output map
exists to score for pixel similarity, seam quality or defect-area agreement.

![Author map versus failed reconstruction](map_comparison.png)

The upper image is the authors' map from
[FSMap](https://github.com/csdemeras/FSMap), retained with its repository license and
source hash. The lower panel describes our actual failure; it is not a reconstructed map.

## Recommended next work

1. Keep this frozen baseline. Reproduce the exact-geometry equatorial case before changing any code.
2. Correct the map coordinate axes and associated spheroid radii together; a label swap alone is insufficient.
3. Compare a paper-faithful pose implementation against the current constrained solver on the calibration sequences.
4. Audit texture rejection and normalized matching cost; evaluate every change against held-out labels and completion rates.
5. Only after reference-data results are adequate, repeat with manually verified silhouettes from the user's conveyor.

Lowering grade thresholds cannot repair these earlier failures. Neither does an
attractive-looking map establish correct feature alignment or surface-area measurement.
This benchmark does not establish the user's tracker, silhouettes or defect model are accurate;
it establishes they are not necessary to reproduce the current reconstruction failures.

## Reproduce from the workspace root

```powershell
.\\backend\\venv\\Scripts\\python.exe -B backend/benchmark_authors.py download
.\\backend\\venv\\Scripts\\python.exe -B backend/benchmark_authors.py run --label current_settings --groups mandarins oranges tomatoes --direction 1 --mask-threshold 8
.\\backend\\venv\\Scripts\\python.exe -B backend/benchmark_authors.py run --label direction_plus_exact_black --groups mandarins oranges tomatoes --direction 1
.\\backend\\venv\\Scripts\\python.exe -B backend/benchmark_authors.py run --label dataset_orientation --groups mandarins oranges tomatoes --direction -1
.\\backend\\venv\\Scripts\\python.exe -B backend/benchmark_authors.py run --label sphere_diagnostic --groups mandarins oranges tomatoes --direction -1 --shape sphere
.\\backend\\venv\\Scripts\\python.exe -B backend/benchmark_mapping_reference.py
.\\backend\\venv\\Scripts\\python.exe -B backend/summarize_authors_benchmark.py
.\\backend\\venv\\Scripts\\python.exe -B -m unittest discover -s backend -p 'test_*.py'
```

Each run records settings, code snapshot/hash, every fruit failure, accepted rotations,
and every labelled correspondence. No detector weights are loaded. The four rotation
runs are CPU diagnostics; they never write to `backend/results` or affect the dashboard.

## Sources and integrity

- [2021 images and annotations](https://github.com/alalbiol/3d-rotation-estimation-fruits), commit
  `f20d6757052388c4f86048a0d5f7ad015c29bb08`.
- [2022 published maps](https://github.com/csdemeras/FSMap), commit
  `4e148a1b436374948a9102ad39cdc4d5b3e36eb3`.
- `source_manifest.json` records exact URLs, Git object checksums and SHA-256 hashes.
- XML/text copies of the open-access papers were fetched from Europe PMC under `papers/`.
- `summary.json` and each `runs/*/report.json` contain numerical results.

## Per-sequence primary results

| Sequence | Views | Shape | Accepted pairs | First map failure |
|---|---:|---|---:|---|
{rows}
'''
    (ROOT/'REPORT.md').write_text(report,encoding='utf-8')
    print(json.dumps({'report':str(ROOT/'REPORT.md'),'summary':summary['dataset_orientation'],
                      'production_algorithm_unchanged':True},indent=2))


if __name__ == '__main__':
    main()
