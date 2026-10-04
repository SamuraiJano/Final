"""Apply the app's partial-map grading policy without repeating model inference."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4

from algorithm import Settings, _grade_map

ROOT = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_job_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{32}', args.source_job_id):
        parser.error('Use the original saved job ID')
    source = ROOT / 'results' / args.source_job_id
    original = json.loads((source / 'report.json').read_text(encoding='utf-8'))
    settings = Settings(**original['metrics']['geometry_settings'])
    settings.grade_partial_maps = True
    job_id = uuid4().hex
    output = ROOT / 'results' / job_id
    original_hash = digest(source / 'report.json')
    # Publish the aggregate only after every derived record is ready.
    shutil.copytree(source, output, ignore=shutil.ignore_patterns('report.json', 'report.tmp'))
    report = json.loads(json.dumps(original).replace(
        f'/results/{source.name}/', f'/results/{job_id}/'))
    for row in report['fruits']:
        row['strict_grading_status'] = row['status']
        row['strict_grading_reason'] = row.get('reason')
        row.update(grade_provisional=False, grade_scope=None, coverage_complete=False)
        if row.get('surface_map'):
            if not (output / str(row['track_id']) / 'surface_map.png').is_file():
                raise ValueError('A declared map is missing')
            coverage = row['observed_surface_pct'] / 100
            longitude = row['observed_longitude_deg']
            rotation = row['rotation_coverage_deg']
            max_pair = max(abs(value) for value in row['pair_rotations_deg'])
            defect = row.get('defect_pct_of_observed')
            has_evidence = bool(row.get('defect_maps')) or settings.defect_observations_complete
            grade, status = _grade_map(defect if has_evidence else None, coverage,
                                      longitude, rotation, max_pair, settings)
            row.update(grade=grade, status=status, grade_provisional=status == 'graded_partial',
                       grade_scope='observed_surface' if grade else None,
                       coverage_complete=(coverage >= settings.minimum_surface_coverage and
                                          longitude >= settings.minimum_longitude_coverage_deg and
                                          rotation >= settings.minimum_rotation_coverage_deg),
                       defect_observations_complete=settings.defect_observations_complete)
            if grade:
                row.pop('reason', None)
            if status == 'graded_partial':
                row['grade_note'] = ('Provisional grade based on the observed surface; '
                                     'unseen areas were not assessed.')
        (output / str(row['track_id']) / 'result.json').write_text(
            json.dumps(row, indent=2), encoding='utf-8')
    changed_images = [path.relative_to(source).as_posix() for path in source.rglob('*.png')
                      if digest(path) != digest(output / path.relative_to(source))]
    if changed_images or digest(source / 'report.json') != original_hash:
        raise ValueError('Original report or map images changed')
    for name in ('algorithm.py', 'main.py'):
        (output / f'grading_{name}.snapshot').write_bytes((ROOT / name).read_bytes())
    report.update(job_id=job_id, created_at=datetime.now(timezone.utc).isoformat(),
                  analysis_kind='saved_map_regrading', derived_from_job_id=source.name,
                  mapping_created_at=original['created_at'],
                  grading_policy={'allow_partial_maps': True, 'grade_scope': 'observed_surface',
                                  'settings': asdict(settings),
                                  'source_sha256': digest(ROOT / 'algorithm.py'),
                                  'method': 'Reuse saved defect percentages; no detection, segmentation or motion rerun.'})
    temporary = output / 'report.tmp'
    temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
    temporary.replace(output / 'report.json')
    summary = {'job_id': job_id, 'source_job_id': source.name,
               'created_at': report['created_at'], 'original_report_sha256': original_hash,
               'grading_source_sha256': report['grading_policy']['source_sha256'],
               'mapping_source_sha256': original['metrics']['algorithm_sha256'],
               'records': len(report['fruits']),
               'grades': dict(Counter(row.get('grade') or 'ungraded' for row in report['fruits'])),
               'provisional_grades': sum(row['grade_provisional'] for row in report['fruits']),
               'verified_unchanged_pngs': len(list(source.rglob('*.png'))),
               'model_calls_in_this_update': 0, 'original_report_unchanged': True}
    evidence = ROOT / 'diagnostics/algorithm-revision/partial_grades_20261003'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'regrading_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (evidence / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
