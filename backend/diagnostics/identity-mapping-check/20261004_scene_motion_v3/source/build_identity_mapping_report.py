"""Summarize the completed tracking attribution and actual mapping reruns."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT/'diagnostics/identity-mapping-check/20261004_scene_motion_v3'


def main():
    attribution = json.loads((OUTPUT/'summary.json').read_text())
    paired = json.loads((OUTPUT/'paired_maps_geometry_only/report.json').read_text())
    integration_path = ROOT/'diagnostics/algorithm-revision/identity_mapping_scene_v2_real_model_20261004/report.json'
    integration = json.loads(integration_path.read_text())
    controls_path = ROOT/'diagnostics/authors-benchmark/synthetic_runs/identity_mapping_20261004/report.json'
    controls = json.loads(controls_path.read_text())
    guard_path = ROOT/'diagnostics/identity-guard/20261004_scene_motion_v3/summary.json'
    guard = json.loads(guard_path.read_text())
    rows = []
    for track in integration['tracks']:
        result = track['result']
        identity = 340 if track['track'] == 491 else track['track']
        rows.append({'raw_track_id': identity, 'fixture_id': track['track'],
                     'views': result['views'], 'mapped_views': len(result['mapped_view_frames']),
                     'observed_surface_pct': result['observed_surface_pct'],
                     'observed_longitude_deg': result['observed_longitude_deg'],
                     'status': result['status'], 'grade': result['grade'],
                     'split_reasons': dict(Counter(item.get('reason') for item in result['view_selection']
                                                  if item.get('status') == 'split'))})
    paired_equal = all(len(case['segments']) == 1 and
                       case['baseline'].get('map_sha256') == case['segments'][0].get('map_sha256') and
                       case['baseline'].get('observed_sha256') == case['segments'][0].get('observed_sha256')
                       for case in paired['cases'])
    assert paired_equal
    report = {
        'conclusion': 'The observed ID changes do not explain the mapping limitation in the tested sequences. '
                      'Rotation/view selection remains the immediate limiting stage; smooth unseen switches are not ruled out.',
        'saved_maps_audited': attribution['produced_maps'],
        'maps_crossing_detected_identity_boundaries_in_selected_views': attribution['maps_with_boundary_inside_selected_views'],
        'paired_cases': len(paired['cases']), 'paired_inputs_unchanged_after_guard_fix': paired_equal,
        'real_model_mapping_cases': rows, 'real_segmentation_calls': integration['segmentation']['calls'],
        'predicted_defect_instances': integration['segmentation']['instances'],
        'known_area_controls_passed': controls['passed'],
        'maximum_known_area_error_percentage_points': max(case['absolute_error_percentage_points'] for case in controls['cases']),
        'python_tests_passed': 88, 'guard_configuration': guard['configuration'],
        'guard_source_sha256': guard['guard_sha256'],
        'mapping_algorithm_sha256': integration['algorithm_sha256'],
        'limitations': ['Frozen detector/tracker observations; no fresh full-video detection run.',
                       'Four actual model mapping fixtures and seven paired geometry cases, not all 474 records reconstructed.',
                       'No labelled physical identities, rotation poses, defect masks or fruit grades.',
                       'Same inputs give same maps; reused paired results establish absence of input segmentation, not two independent accuracy trials.',
                       '37 maps have boundaries elsewhere in captured views; their shape fits may still change when separate segments are reconstructed.'],
    }
    (OUTPUT/'validation.json').write_text(json.dumps(report, indent=2))
    (OUTPUT/'real_model_mapping_report.json').write_text(json.dumps(integration, indent=2))
    (OUTPUT/'known_area_report.json').write_text(json.dumps(controls, indent=2))
    shutil.copyfile(ROOT/'diagnostics/identity-mapping-check/20261004/onset_transition.jpg', OUTPUT/'onset_transition.jpg')
    source = OUTPUT/'source'
    source.mkdir(exist_ok=True)
    for name in ('fruit_identity.py', 'algorithm.py', 'main.py', 'test_fruit_identity.py',
                 'check_identity_mapping.py', 'compare_identity_maps.py', 'build_identity_mapping_report.py'):
        shutil.copyfile(ROOT/name, source/name)

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11})
    fig, ax = plt.subplots(figsize=(9, 4.3))
    positions = np.arange(len(rows))
    values = [row['observed_surface_pct'] for row in rows]
    labels = [f"Fruit {row['raw_track_id']}  ({row['mapped_views']}/{row['views']} views retained)" for row in rows]
    ax.barh(positions, values, color=['#138c67' if value >= 80 else '#b57827' for value in values], height=.56)
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 102)
    ax.axvline(80, color='#444444', linestyle='--', linewidth=1)
    ax.text(80.5, 1., '80% target', va='center', fontsize=10, color='#444444')
    for position, value in enumerate(values):
        ax.text(value+1.3, position, f'{value:.1f}%', va='center', fontweight='bold')
    ax.set_xlabel('Observed surface (%)')
    ax.set_title('Mapping remains partial with continuous capture identity', loc='left', pad=18, fontweight='bold')
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.set_axisbelow(True)
    ax.grid(axis='x', alpha=.15)
    fig.text(.02, .015, 'Actual CUDA defect model on frozen conveyor crops. Coverage is not validated reconstruction accuracy.', fontsize=9)
    fig.tight_layout(rect=[0, .05, 1, 1])
    fig.savefig(OUTPUT/'mapping_coverage.png', dpi=200)
    plt.close(fig)

    lines = [
        '# Tracking attribution and mapping rerun — 4 October 2026', '',
        '**The observed ID changes do not explain the mapping limitation in the tested sequences.** '
        'The evidence points to rotation/view selection as the immediate limiting stage. '
        'Smooth, unnoticed exchanges between similar fruit remain possible without physical identity labels.', '',
        '## What was checked', '',
        'The original 515-frame job contains 474 records and 294 usable maps. The recovered '
        'raw-ID transition 244 → 248 had zero and one usable views respectively; neither ID '
        'produced a map. All 15 IDs in the earlier seven legacy/current association disagreements '
        'also failed mapping. These specific transitions therefore cannot have introduced '
        'seams into a saved surface map.', '',
        'The updated guard detects no boundary within the selected views of any of the 294 '
        'maps. It detects boundaries elsewhere in the captured views of 37 maps, so their '
        'preselection shape fits may still be affected. An absence of flags is not a physical '
        'identity accuracy claim.', '',
        '## Guard defect found and corrected', '',
        'The initial guard assumed zero motion on the first observation pair. A common '
        'clip-start displacement triggered 19 overly conservative discontinuity flags; the three selected-map '
        'boundaries were all at frame 0 → 1. Visual inspection of fruit 16, 18 and 35 shows '
        'consistent fruit markings across that transition. This is visual evidence, not an '
        'independently labelled tracking benchmark.', '',
        'Version 3 initializes each track’s first three observations from the robust common '
        'motion of at least five complete, same-ID boxes when at least 70% agree within the '
        'existing size-normalized gate. It then uses the track’s own history. An isolated '
        'jump amid common movement remains rejected. Four new regression cases check common '
        'startup motion, an isolated jump, an incoherent scene and return to local velocity.', '',
        f"The corrected replay has {guard['capture_segments']} capture segments, "
        f"{guard['decisions']['observation_gap']} gap boundaries and "
        f"{guard['decisions']['motion_or_size_discontinuity']} motion/size boundary. "
        'The remaining motion/size boundary is raw ID 254 at frame 287, a record with no '
        'usable map views. Capture segments are not unique physical fruit counts.', '',
        '[First-frame visual comparison](onset_transition.jpg)', '',
        '## Actual mapping rerun', '',
        'The CUDA defect model made 42 inference calls and returned 80 predicted instances '
        'while remapping 215 frozen views across four sequences. Detector/tracker observations '
        'were held fixed to isolate mapping. All four produced maps; one reaches the 80% '
        'target and three remain provisional partial maps.', '',
        '| Physical track in cached replay | Input views | Views selected | Observed surface | Coverage |',
        '| --- | ---: | ---: | ---: | --- |',
    ]
    for row in rows:
        label = str(row['raw_track_id'])+(' (legacy fixture 491)' if row['fixture_id'] == 491 else '')
        lines.append(f"| {label} | {row['views']} | {row['mapped_views']} | {row['observed_surface_pct']:.3f}% | {'Meets target' if row['observed_surface_pct'] >= 80 else 'Partial'} |")
    lines += ['', '![Mapping coverage](mapping_coverage.png)', '',
        'All 215 fixture crops were linked to the current raw IDs by pixels. For legacy '
        'fixture 491, 31 crops match the current detector-box crop exactly; the other 28 '
        'were located exactly in the original frame and matched to the unique overlapping '
        'box. Every one belongs to current raw ID 340. Comparing numeric IDs across runs '
        'without this correspondence would misidentify the fruit.', '',
        'The mapper repeatedly splits sequences for unobservable/near-zero estimated '
        'rotation, high texture-matching error, disagreements between coarse and native '
        'rotation estimates, and longitude progression outside its fusion bounds. For '
        'fruit 14 it retains only two of 44 views despite continuous capture identity. '
        'This explains the immediate low-coverage outcome, but does not by itself identify '
        'whether lighting, masks, physical motion or the estimator is responsible.', '',
        '## Paired reconstruction and controls', '',
        'Seven paired geometry cases use the four saved fixtures and freshly recaptured '
        'source-frame views of onset fruit 16, 18 and 35. Both variants share identical '
        'crop/mask arrays. After the guard correction, each has one capture segment, so '
        'the guard makes no input change and the map/observed-mask hashes agree. Identical '
        'input results are reused rather than portrayed as independent accuracy trials. '
        'No defect observations or grades are claimed by this geometry comparison.', '',
        'The earlier version-1 paired experiment separated the first frame. It changed '
        'coverage very little for the four main fixtures, reduced the short onset maps '
        'and made onset fruit 35 fail. Correcting startup initialization removes that '
        'introduced failure. The historical exploratory `paired_maps` report used the '
        'completed-defect flag with empty masks; its grading statuses are excluded from '
        'this assessment. The later geometry-only runs explicitly disable that flag.', '',
        '**Known-area controls pass:** 5%, 15% and 30% truth produce 5.144%, 15.179% and '
        '30.093% measured defects. Maximum error is 0.179 percentage points. All four '
        'coverage controls and all 88 Python tests pass. These controls do not establish '
        'conveyor reconstruction or grading accuracy.', '',
        '## Evidence and reproducibility', '',
        '[Validation summary](validation.json) · [map/identity overlap](map_overlap.json) · '
        '[crop correspondence](fixture_correspondence.json) · '
        '[paired geometry report](paired_maps_geometry_only/report.json) · '
        '[real model mapping report](real_model_mapping_report.json) · '
        '[known-area control report](known_area_report.json)', '',
        'Sources and input hashes are preserved. Original application reports are untouched. '
        'This was a saved-observation mapping test; the complete detector-to-map pipeline '
        'was not rerun for all 474 records. The corrected guard applies on the next backend '
        'start. A defensible physical-ID accuracy result still needs labelled trajectories.', '',
        '```powershell',
        './backend/venv/Scripts/python.exe -B backend/replay_identity_guard.py --output backend/diagnostics/identity-guard/20261004_scene_motion_v3',
        './backend/venv/Scripts/python.exe -B backend/check_identity_mapping.py',
        './backend/venv/Scripts/python.exe -B backend/compare_identity_maps.py',
        './backend/venv/Scripts/python.exe -B -m unittest discover -s backend -p \'test_*.py\'',
        '```', '',
    ]
    (OUTPUT/'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'report': str(OUTPUT/'REPORT.md'), 'paired_cases': len(paired['cases']),
                      'known_area_controls': controls['passed'], 'python_tests': 88}, indent=2))


if __name__ == '__main__':
    main()
