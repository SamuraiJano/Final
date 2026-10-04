"""Pair all published author labels; unavailable predictions never count as correct."""
from pathlib import Path
import hashlib
import json

import numpy as np


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[3]
DIAGNOSTICS = PROJECT / 'backend/diagnostics'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):
    return row['group'], row['object'], row['line']


def main():
    baseline_path = DIAGNOSTICS / 'authors-benchmark/runs/operational_profile_v1/report.json'
    revised_path = DIAGNOSTICS / 'authors-benchmark/runs/adjacent_observable_profile_20261002/report.json'
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    revised = json.loads(revised_path.read_text(encoding='utf-8'))
    old = {key(row): row for row in baseline['correspondences']}
    new = {key(row): row for row in revised['correspondences']}
    assert old.keys() == new.keys() and len(old) == 497
    changed, pairs, lost, gained = [], [], [], []
    for label in sorted(old):
        before, after = old[label], new[label]
        for field in ('source', 'target', 'source_xy', 'target_xy'):
            assert before[field] == after[field]
        row = {field: before[field] for field in
               ('group', 'object', 'line', 'source', 'target', 'source_xy', 'target_xy')}
        row.update(baseline_status=before['status'], revised_status=after['status'])
        for prefix, value in [('baseline', before), ('revised', after)]:
            for field in ('prediction', 'error_px', 'reason'):
                if field in value:
                    row[f'{prefix}_{field}'] = value[field]
        if before['status'] == after['status'] == 'ok':
            difference = float(np.linalg.norm(np.asarray(before['prediction']) - after['prediction']))
            row['prediction_difference_px'] = difference
            row['error_change_px'] = after['error_px'] - before['error_px']
            if difference > 1e-9:
                changed.append(row.copy())
        elif before['status'] == 'ok':
            lost.append(row.copy())
        elif after['status'] == 'ok':
            gained.append(row.copy())
        pairs.append(row)
    report = {'method': 'Pair every published label by group, object, and original annotation line. '
                        'Unavailable predictions count toward the497-label denominator, never as correct.',
        'limitations': 'Development data already inspected; no held-out generalization or defect/grade accuracy.',
        'algorithm_sha256': {'baseline': baseline['algorithm_sha256'], 'revised': revised['algorithm_sha256']},
        'report_sha256': {'baseline': digest(baseline_path), 'revised': digest(revised_path)},
        'label_count': len(pairs), 'same_returned_label_count': sum(
            row['baseline_status'] == row['revised_status'] == 'ok' for row in pairs),
        'baseline_errors_px': baseline['summary']['all']['errors_px_conditional_on_prediction'],
        'revised_errors_px': revised['summary']['all']['errors_px_conditional_on_prediction'],
        'changed_prediction_count': len(changed),
        'changed_improved_count': sum(row['error_change_px'] < 0 for row in changed),
        'changed_worsened_count': sum(row['error_change_px'] > 0 for row in changed),
        'changed_predictions': changed, 'lost_predictions': lost,
        'gained_predictions': gained, 'all_label_pairs': pairs}
    (HERE / 'paired_prediction_comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print({name: report[name] for name in ('label_count', 'same_returned_label_count',
        'changed_prediction_count', 'changed_improved_count', 'changed_worsened_count')})


if __name__ == '__main__':
    main()
