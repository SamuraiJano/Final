"""Correct a static chart annotation; preserve original exports and all scores."""
import json
from pathlib import Path
import sys

FOLDER = Path(__file__).resolve().parent
BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
from validate_photometric_motion_controls import stationary_result_figure, report_text
from validate_motion_resolution import sha256, write_json


def main():
    original_report = FOLDER/'report.json'
    report = json.loads(original_report.read_text(encoding='utf-8'))
    assert 'plot_annotation_correction' not in report
    (FOLDER/'report_before_plot_correction.json').write_bytes(original_report.read_bytes())
    for name in ('stationary_observability.png', 'stationary_observability.pdf', 'PHOTOMETRIC_MOTION_CONTROLS.md'):
        source = FOLDER/name
        source.with_name(source.stem+'_original'+source.suffix).write_bytes(source.read_bytes())
    helper = BACKEND/'validate_photometric_motion_controls.py'
    (FOLDER/'plot_annotation_source.py').write_bytes(helper.read_bytes())
    stationary_result_figure(FOLDER, report)
    (FOLDER/'PHOTOMETRIC_MOTION_CONTROLS.md').write_text(report_text(report), encoding='utf-8')
    report['plot_annotation_correction'] = {
        'reason': 'The shared previous figure helper unconditionally wrote No stationary map or grade. '
                  'Texture A actually produced a partial map; corrected chart explicitly shows actual '
                  'returned measurements, endpoint availability, map status and grade.',
        'original_exports_preserved_with_suffix': '_original',
        'execution_source_and_all_control_results_unchanged': True,
        'original_report_sha256': sha256(FOLDER/'report_before_plot_correction.json'),
        'plot_helper_sha256': sha256(FOLDER/'plot_annotation_source.py'),
        'postprocessing_script_sha256': sha256(Path(__file__))}
    write_json(original_report, report)
    unchanged = json.loads(original_report.read_text(encoding='utf-8'))
    unchanged.pop('plot_annotation_correction')
    assert unchanged == json.loads((FOLDER/'report_before_plot_correction.json').read_text(encoding='utf-8'))
    write_json(FOLDER/'sha256.json', {str(path.relative_to(FOLDER)): sha256(path)
               for path in FOLDER.rglob('*') if path.is_file() and path.name != 'sha256.json'})
    print(json.dumps(report['plot_annotation_correction'], indent=2))


if __name__ == '__main__': main()
