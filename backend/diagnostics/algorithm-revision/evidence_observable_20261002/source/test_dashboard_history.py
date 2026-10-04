"""Class filtering must include results beyond the old 60-record cutoff."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main


class DashboardHistoryTests(unittest.TestCase):
    def test_late_grade_remains_searchable_and_motion_diagnostics_stay_in_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'example'
            run.mkdir()
            fruits = [{'track_id': number, 'grade': None, 'status': 'mapping_failed'}
                      for number in range(60)]
            fruits.append({'track_id': 125, 'grade': 'Class 1', 'status': 'graded',
                           'view_selection': [{'status': 'accepted'}],
                           'mapped_view_frames': [1, 2],
                           'view_evidence': [{'frame': 1, 'crop': '/results/example/125/crop.png'}]})
            source = json.dumps({'fruits': fruits, 'source_name': 'test.mp4'})
            report = run / 'report.json'
            report.write_text(source, encoding='utf-8')
            with patch.object(main, 'RESULTS', root):
                result = main.dashboard()
            self.assertEqual(result['summary']['classes']['Class 1'], 1)
            graded = [fruit for fruit in result['recent_fruits'] if fruit.get('grade')]
            self.assertEqual([fruit['track_id'] for fruit in graded], [125])
            self.assertEqual(graded[0]['mapped_view_frames'], [1, 2])
            self.assertEqual(graded[0]['view_evidence'][0]['frame'], 1)
            self.assertNotIn('view_selection', graded[0])
            self.assertEqual(report.read_text(encoding='utf-8'), source)


if __name__ == '__main__':
    unittest.main()
