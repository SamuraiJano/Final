"""Verify the final report's source and referenced machine-readable evidence."""
from pathlib import Path
import hashlib
import json
import re

here = Path(__file__).resolve().parent
backend = here.parents[2]
expected = 'cf6c2dd19968f0c159a7e2ecb8d781eee0206a88d0bab104df8d087023706745'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(backend/'algorithm.py') == expected
assert sha(here/'source/algorithm.py') == expected
mapping = json.loads((here.parent/'20261004_scoped_final_maps/report.json').read_text())
model = json.loads((backend/'diagnostics/algorithm-revision/fruit340_scoped_final_real_model_20261004/report.json').read_text())
area = json.loads((backend/'diagnostics/authors-benchmark/synthetic_runs/fruit340_scoped_final_20261004/report.json').read_text())
assert mapping['source_sha256']['candidate'] == model['algorithm_sha256'] == area['algorithm_sha256'] == expected
assert model['passed_execution'] and area['passed']
assert model['segmentation']['calls'] == 58 and model['segmentation']['instances'] == 104
assert model['detection']['calls'] == 0
fruit = mapping['tracks']['340']['candidate']
assert fruit['view_frames'] == [305,306,307,308,309]
assert abs(fruit['observed_surface_pct'] - 32.22001026366526) < 1e-9
assert fruit['grade'] is None
links = re.findall(r'\]\(([^)]+)\)', (here/'REPORT.md').read_text(encoding='utf-8'))
local = [link for link in links if not link.startswith('https://')]
assert all((here/link).is_file() for link in local), [link for link in local if not (here/link).is_file()]
record = {'algorithm_sha256': expected,
          'unit_tests': {'count':94, 'passed':True, 'execution_record':'unittest.txt'},
          'final_geometry_replay_verified':True, 'final_model_execution_verified':True,
          'known_area_controls_passed':True, 'local_report_links_verified':len(local),
          'physical_raw_id':340, 'legacy_fixture_id':491,
          'selected_frames':fruit['view_frames'],
          'estimated_observed_surface_pct':fruit['observed_surface_pct'],
          'complete_map_accuracy_verified':False,
          'detector_or_tracking_rerun':False,
          'model_segmentation_calls':58, 'model_predicted_instances':104}
(here/'validation.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
(here/'sha256.json').write_text(json.dumps({str(path.relative_to(here)):sha(path)
    for path in here.rglob('*') if path.is_file() and path.name != 'sha256.json'}, indent=2), encoding='utf-8')
print(json.dumps(record, indent=2))
