"""Create report figures from frozen author bridge diagnostics, without inference."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    root = Path(__file__).resolve().parent / 'diagnostics' / 'authors-benchmark'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=root / 'bridge_runs' / 'selected_bridges_checks_20261002')
    parser.add_argument('--candidate', type=Path, default=root / 'bridge_runs' / 'candidate_bridge_guard_050_20261002')
    args = parser.parse_args()
    baseline = json.loads((args.baseline / 'report.json').read_text())
    candidate = json.loads((args.candidate / 'report.json').read_text())
    ordinary = json.loads((root / 'runs' / 'candidate_bridge_guard_050_20261002' / 'report.json').read_text())
    frozen = json.loads((root / 'runs' / 'operational_profile_v1' / 'report.json').read_text())
    output = args.baseline
    (output / 'evidence_builder_snapshot.py').write_bytes(Path(__file__).read_bytes())
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})
    fig, axes = plt.subplots(4, 2, figsize=(10, 11))
    for index, row in enumerate(baseline['bridge_endpoint_pairs']):
        group = {'mandarins': 'Mandarin', 'tomatoes': 'Tomato'}[row['group']]
        for column, endpoint in enumerate(('source', 'target')):
            frame = row[endpoint]
            path = root / 'data' / 'rotation' / 'data' / row['group'] / row['object'] / f'im{frame:02d}.png'
            # Author filenames use four digits, discover the exact file by frame index.
            paths = sorted(path.parent.glob('im*.png'))
            path = next(value for value in paths if int(value.stem[2:]) == frame)
            image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
            ax = axes[index, column]
            ax.imshow(image)
            point = row[f'{endpoint}_xy']
            ax.scatter(*point, marker='o', s=85, facecolors='none',
                       edgecolors='#fde047' if endpoint == 'source' else '#4ade80', linewidths=1.7)
            if endpoint == 'target':
                ax.scatter(*row['prediction'], marker='x', s=100, color='#f87171', linewidths=2)
                ax.set_title(f"Target {frame}: miss {row['error_px']:.2f} px", loc='left')
            else:
                ax.set_title(f"{group} {row['object']} · source {frame}", loc='left')
            ax.axis('off')
        checks = row['independent_checks']
        axes[index, 0].text(0, -.06, f"Author rows {', '.join(str(v) for v in row['author_annotation_lines'])}",
                            transform=axes[index, 0].transAxes, fontsize=9, va='top')
        axes[index, 1].text(0, -.06,
                            f"Accepted residual {next(d['error'] for t in baseline['tracks'] if t['group']==row['group'] and t['object']==row['object'] for d in t['selection_diagnostics'] if d['source_frame']==row['source'] and d['target_frame']==row['target']):.3f} / gate 0.580",
                            transform=axes[index, 1].transAxes, fontsize=9, va='top')
    fig.suptitle('Accepted skipped-view matches can miss the author’s labelled feature', fontsize=15, weight='bold')
    fig.text(.5, .025, 'Yellow: author source · Green: author target · Red: prediction\n'
             'Exact-coordinate chains of published labels; four available bridge cases, not independent held-out data.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=[0, .07, 1, .965], h_pad=1.9)
    fig.savefig(output / 'author_bridge_failures.png', dpi=300)
    fig.savefig(output / 'author_bridge_failures.pdf')
    plt.close(fig)

    status_counts = lambda report: Counter(track['map'].get('result_status', track['map']['status'])
                                           for track in report['tracks'])
    old_counts, new_counts = status_counts(frozen), status_counts(ordinary)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    width, xs = .35, np.arange(3)
    colors = ['#475569', '#0369a1']
    left_old = [20, 4, 16]
    left_new = [4, 0, 4]
    right_old = [old_counts['missing_defect_masks'], old_counts['insufficient_longitude_coverage'], old_counts['failed']]
    right_new = [new_counts['missing_defect_masks'], new_counts['insufficient_longitude_coverage'], new_counts['failed']]
    for ax, old, new, labels, title in (
            (axes[0], left_old, left_new, ['All selected\nbridges', 'Known bad\nlabelled bridges', 'Bridges without\nendpoint labels'], 'Selected nonadjacent transitions'),
            (axes[1], right_old, right_new, ['Coverage\neligible', 'Partial\nlongitude', 'Mapping\nfailed'], 'All 36 author sequences')):
        before = ax.bar(xs-width/2, old, width, label='Previous guard', color=colors[0])
        after = ax.bar(xs+width/2, new, width, label='Candidate guard ≤ 0.5', color=colors[1])
        ax.bar_label(before, padding=3)
        ax.bar_label(after, padding=3)
        ax.set_xticks(xs, labels)
        ax.set_title(title, loc='left', weight='bold')
        ax.set_ylim(0, max(old+new)*1.22)
        ax.spines[['top','right']].set_visible(False)
        ax.set_ylabel('Count')
    axes[0].legend(fontsize=8)
    fig.suptitle('The candidate excludes known bad bridges and reduces coverage availability', fontsize=13, weight='bold')
    fig.text(.5, .015, 'Recomputed selection can create different bridges. Remaining bridges are unverified.\n'
             'Coverage eligibility is not map accuracy; author data contain no defect truth. Threshold inspected on development data.',
             ha='center', fontsize=8)
    fig.tight_layout(rect=[0, .105, 1, .94])
    fig.savefig(output / 'bridge_guard_comparison.png', dpi=300)
    fig.savefig(output / 'bridge_guard_comparison.pdf')
    plt.close(fig)
    table = '\n'.join(
        f"| {row['group']}/{row['object']} | {row['source']} → {row['target']} | "
        f"{', '.join(str(v) for v in row['author_annotation_lines'])} | {row['error_px']:.2f} | "
        f"{row['independent_checks']['approx_lifted_endpoint_angular_separation_deg']:.2f} |"
        for row in baseline['bridge_endpoint_pairs'])
    text = f'''# Author bridge audit — 2 October 2026

The spheroid formulas remain consistent with the saved research methods. The
additional step that skips views and reconnects later texture matches needs
stronger validation: it accepted all four nonadjacent transitions for which exact
chains of author annotations supply endpoint truth, with errors of 16.41–41.38 px.
This finding supports a change to transition acceptance. It does not isolate all
geometry, texture or camera errors and does not establish field accuracy.

## What was tested

All 578 original images in 36 public author sequences were used with the frozen
operational settings: automatic sphere/oblate selection, x axis, negative author
rotation direction, bidirectional MAD, and rotating-view selection. No detector,
tracker, defect model or user's video was run in this audit. Masks were derived
from the authors' black backgrounds and are not silhouette ground truth.

All 497 published point labels span adjacent views. The existing benchmark scores
these adjacent estimates independently, so its 458/497 predictions and 5.103 px RMS
do not validate a later accepted nonadjacent bridge. This audit joins annotations
only when their `(view, x, y)` endpoints are **exactly equal**; it adds no interpolated
labels. Annotation line numbers are retained. Multiple possible feature positions
at either endpoint would be excluded as ambiguous.

Twenty nonadjacent bridges were selected; only four have exact chained feature
endpoints. The other sixteen are unverified. Four predictions returned, all missed
by more than the existing 5 px reporting indicator: RMS 29.291 px, median 25.549 px.
These four endpoint pairs are correlated with existing labels and are not a new
independent or held-out test set.

| Author sequence | Bridge | Annotation lines | Error px | Approx. lifted separation ° |
| --- | --- | --- | ---: | ---: |
{table}

![Four accepted bridges with available author endpoint labels](author_bridge_failures.png)

Figure 1. Original author pixels with source, target and predicted feature
positions. All four available labelled bridge cases are shown. Yellow is the
author source, green the author target, and red the algorithm prediction. Counts
and error are based on the unresized source coordinates.

Both endpoints of every case lie on a finite front-facing estimated surface.
The first two lifted angular separations exceed the search domain's maximum total
rotation magnitude `sqrt(55²+10²) = 55.90°`. This suggests that skipping views can
pass beyond the feasible rotation range and find a smaller apparent match. The
lifting depends on an approximate spheroid, so these are not measured 3D rotations.

Direct bridge rotation differs from independently estimated adjacent composition
by 34.29°, 26.57°, 4.73° and 6.53°. The first three compositions include at least
one residual-rejected pair and are diagnostic only. In the last case all four
adjacent residuals pass: composing them yields 8.55 px reprojection error, compared
with 16.41 px for the selected direct bridge. A cycle check could expose some
disagreement but would not certify every case. Relaxing failed pair gates is not
validated by this experiment.

## Isolated candidate and outcome

The isolated snapshot adds a maximum normalized residual of **0.5 only for a
nonadjacent transition**. Production code was unchanged during these runs. The
threshold was chosen after inspecting this development evidence; no held-out
accuracy improvement is claimed.

| Indicator | Previous selector | Candidate bridge residual ≤ 0.5 |
| --- | ---: | ---: |
| Original images / sequences | 578 / 36 | 578 / 36 |
| Geometry fits / maps, including partial | 36 / 34 | 36 / 34 |
| Ordinary independent adjacent predictions / labels | 458 / 497 | 458 / 497 |
| Ordinary independent adjacent RMS px | 5.103 | 5.103 |
| Original labels measurable on retained selected poses | 305 / 497 | 285 / 497 |
| Selected-pose RMS px, different returned subsets | 4.806 | 4.924 |
| Nonadjacent selected bridges | 20 | 4 |
| Accepted known bad labelled bridges | 4 | 0 |
| Remaining bridges with endpoint truth | 4 | 0 |
| Author maps meeting current coverage gates | 17 | 13 |
| Partial maps / mapping failures | 17 / 2 | 21 / 2 |

![Candidate selection and availability](bridge_guard_comparison.png)

Figure 2. The candidate is an exclusion safeguard. Recomputed selection can
create different bridges; the four remaining bridges have no exact chained
endpoint labels. Removing the four observed failures does not establish zero
remaining error. Adjacent RMS remains unchanged because its estimator was not
changed. Lower selected-pose availability and coverage eligibility are reported
instead of being hidden. No author grade accuracy is measured.

## Recommended next test

Do not rewrite the spheroid equations based on these results. Improve acceptance
of skipped transitions and test direct versus composed rotations, search-domain
limits, and repeated-feature ambiguity on analytic sequences with known variable
motion. Distinguish valid low-motion views from failed or unmeasured views before
joining a gap. On the user's camera, manually label feature correspondences and
loop closure on one fully rotating tracked naartjie; tracking alone supplies no
surface-motion truth. Different GrabCut masks and shape choices should be compared
on the **same frozen crops**, rather than interpreting a changed map as improved
accuracy without labels.

The 0.5 candidate can exclude observed bad bridges, but is a conservative
development safeguard rather than a demonstrated complete solution. The
unlabelled long gaps and inaccurate adjacent cases remain material limitations.

## Evidence and reproduce

- Full baseline audit: `report.json`, algorithm and validator snapshots here.
- Candidate bridge audit: `../candidate_bridge_guard_050_20261002/report.json`.
- Full candidate 36-object benchmark: `../../runs/candidate_bridge_guard_050_20261002/report.json`.
- Candidate snapshot: `../residual_guard_candidate_source/algorithm_snapshot.py`.
- Primary methods: [2021 spheroid and rotation paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/),
  [2022 surface map paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9323781/).
  Local saved copies are `../../papers/PMC8004661.txt` and `../../papers/PMC9323781.txt`.

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_author_bridges.py --label NEW_BASELINE
./backend/venv/Scripts/python.exe -B backend/validate_author_bridges.py --label NEW_CANDIDATE --algorithm-snapshot backend/diagnostics/authors-benchmark/bridge_runs/residual_guard_candidate_source/algorithm_snapshot.py
./backend/venv/Scripts/python.exe -B backend/benchmark_authors.py run --label NEW_FULL_CANDIDATE --groups mandarins oranges tomatoes --direction -1 --bidirectional --select-views --minimum-rotation 0 --minimum-longitude 350 --algorithm-snapshot backend/diagnostics/authors-benchmark/bridge_runs/residual_guard_candidate_source/algorithm_snapshot.py
```

The report snapshots and hashes identify the exact code and settings used. Later
source edits must not be cited as though these frozen runs tested them.
'''
    (output / 'BRIDGE_AUDIT.md').write_text(text, encoding='utf-8')
    files = ['report.json', 'algorithm_snapshot.py', 'validation_snapshot.py', 'benchmark_snapshot.py', 'evidence_builder_snapshot.py',
             'BRIDGE_AUDIT.md', 'author_bridge_failures.png', 'author_bridge_failures.pdf',
             'bridge_guard_comparison.png', 'bridge_guard_comparison.pdf']
    checks = {'figure_dpi': 300, 'pixel_errors_original_resolution': True,
              'files': {name: {'bytes': (output/name).stat().st_size,
                               'sha256': hashlib.sha256((output/name).read_bytes()).hexdigest()} for name in files}}
    (output / 'evidence_checks.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
    print(output / 'BRIDGE_AUDIT.md')


if __name__ == '__main__':
    main()
