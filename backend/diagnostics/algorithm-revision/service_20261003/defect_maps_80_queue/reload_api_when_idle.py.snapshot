"""Wait for one recorded video; optionally hand off to the guarded API restart.

Default mode only reports ready_for_restart. The opt-in restart is guarded but
not atomic: another client must not start a video during the final handoff.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

import restart_owned_api as restart


ROOT = restart.ROOT
PYTHON = ROOT / 'backend/venv/Scripts/python.exe'
SERVICE = ROOT / 'backend/diagnostics/algorithm-revision/service_20261003'
EXPECTED = {
    'backend/algorithm.py': 'f10e8393f1af64f67023f9519fcbf1b117d91418c1955ec44c2bd329fa22e657',
    'backend/main.py': '3e6496ca136ce4ac837dc492aac966745117bd0dd8c3f0180fd952933045d363',
    'backend/map_visualization.py': 'c26bd9a73484b93b8a870c46d7f8c1a6885aa33c4273fc82df1ec65c3ffbaaa9',
    'backend/render_saved_defect_maps.py': 'b7de33092f15cc5a6a7a416e1db508edc26b950b9bc58f7140a6eb7eba385099',
}
COMPLETED_JOB = '5582c6f789f1497abd45cfc08f2b4863'
OLD_MAIN = '76a66ac90ad2549775bce28f0ecb66b4348a4a0829219c770eb08349230d5f89'
TERMINAL = {'idle', 'complete', 'cancelled', 'error'}
LIVE_IDLE = {'idle', 'stopped', 'error'}


def decide(analysis, live, run_id, last_frame=None):
    """A different identity or decreasing progress stops this queue."""
    if analysis.get('run_id') != run_id:
        raise RuntimeError('Analysis run ID changed; refusing the queued restart')
    frame = analysis.get('frames_processed')
    if type(frame) is not int or frame < 0:
        raise RuntimeError('Analysis progress is invalid')
    if last_frame is not None and frame < last_frame:
        raise RuntimeError('Analysis progress decreased; refusing the queued restart')
    action = 'ready' if analysis.get('state') in TERMINAL and live.get('state') in LIVE_IDLE else 'wait'
    return action, frame


def confirm_ready(first_ready, action, now):
    first_ready = (first_ready if first_ready is not None else now) if action == 'ready' else None
    return first_ready, first_ready is not None and now - first_ready >= 20


def validate_report(report, job_id, frames):
    metrics = report.get('metrics', {})
    if report.get('job_id') != job_id or metrics.get('frames') != frames:
        raise RuntimeError('Completed job identity or frame count does not match the queued job')
    if metrics.get('algorithm_sha256') != EXPECTED['backend/algorithm.py']:
        raise RuntimeError('Completed job algorithm does not match the queued job')
    if metrics.get('geometry_settings', {}).get('minimum_surface_coverage') != .65:
        raise RuntimeError('Completed job does not have the expected original 65% policy')


def verify_saved_report(job_id, frames):
    source = ROOT / 'backend/results' / job_id
    validate_report(json.loads((source / 'report.json').read_text(encoding='utf-8')), job_id, frames)
    check_hashes({f'backend/results/{job_id}/algorithm.py.snapshot': EXPECTED['backend/algorithm.py'],
                  f'backend/results/{job_id}/main.py.snapshot': OLD_MAIN}, ROOT)


def safe_environment():
    return {**restart.os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
            'OPENBLAS_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1',
            'YOLO_CONFIG_DIR': str(ROOT / 'backend/runtime/ultralytics')}


def check_hashes(expected, root=ROOT):
    for relative, wanted in expected.items():
        if restart.digest(root / relative) != wanted:
            raise RuntimeError(f'Recorded source changed: {relative}')


def verify_owned(previous, expected):
    check_hashes(expected)
    api, _ = restart.verified_tree(previous['api'])
    dashboard, _ = restart.verified_tree(previous['dashboard'])
    if {item.pid for item in api} & {item.pid for item in dashboard}:
        raise RuntimeError('Recorded API and dashboard process trees overlap')
    listeners = [item.pid for item in api for connection in item.net_connections(kind='tcp')
                 if connection.status == restart.psutil.CONN_LISTEN and connection.laddr.port == 8000]
    if len(listeners) != 1:
        raise RuntimeError('Port 8000 does not have exactly one recorded API listener')


def self_test(folder):
    """Scripted CPU-only checks. No HTTP calls, processes or inference."""
    import tempfile
    import unittest
    from unittest.mock import patch

    class Decisions(unittest.TestCase):
        def sample(self, state='processing', run_id='same', frame=10, live='idle', last=None):
            return decide({'state': state, 'run_id': run_id, 'frames_processed': frame},
                          {'state': live}, 'same', last)

        def test_processing_waits(self):
            self.assertEqual(self.sample(), ('wait', 10))

        def test_same_run_complete_is_ready(self):
            self.assertEqual(self.sample('complete'), ('ready', 10))

        def test_two_terminal_observations_need_twenty_seconds(self):
            first, confirmed = confirm_ready(None, 'ready', 100)
            self.assertFalse(confirmed)
            self.assertFalse(confirm_ready(first, 'ready', 119.99)[1])
            self.assertTrue(confirm_ready(first, 'ready', 120)[1])

        def test_active_sample_resets_confirmation(self):
            self.assertEqual(confirm_ready(100, 'wait', 120), (None, False))

        def test_terminal_states_are_ready_without_cancelling(self):
            for state in TERMINAL:
                self.assertEqual(self.sample(state), ('ready', 10))

        def test_active_live_waits(self):
            for live in ('starting', 'running', 'stopping', 'unknown'):
                self.assertEqual(self.sample('complete', live=live), ('wait', 10))

        def test_unknown_analysis_state_waits(self):
            self.assertEqual(self.sample('unknown'), ('wait', 10))

        def test_other_active_run_aborts(self):
            with self.assertRaises(RuntimeError):
                self.sample(run_id='different')

        def test_other_terminal_run_aborts(self):
            with self.assertRaises(RuntimeError):
                self.sample('complete', run_id='different')

        def test_cleared_identity_aborts(self):
            with self.assertRaises(RuntimeError):
                self.sample('idle', run_id=None)

        def test_decreasing_frames_aborts(self):
            with self.assertRaises(RuntimeError):
                self.sample(frame=9, last=10)

        def test_invalid_frames_abort(self):
            for frame in (-1, None, '10', True):
                with self.assertRaises(RuntimeError):
                    self.sample(frame=frame)

        def test_changed_source_aborts(self):
            with tempfile.TemporaryDirectory(dir=folder) as temporary:
                base = Path(temporary)
                (base / 'source.py').write_text('before', encoding='utf-8')
                expected = {'source.py': restart.digest(base / 'source.py')}
                check_hashes(expected, base)
                (base / 'source.py').write_text('after', encoding='utf-8')
                with self.assertRaises(RuntimeError):
                    check_hashes(expected, base)

        def test_owned_identity_failure_aborts_before_http_or_restart(self):
            with patch(__name__ + '.check_hashes'), patch.object(restart, 'verified_tree',
                    side_effect=RuntimeError('Recorded PID was reused')), patch.object(restart, 'get') as get:
                with self.assertRaises(RuntimeError):
                    verify_owned({'api': {}, 'dashboard': {}}, {})
                get.assert_not_called()

        def test_completed_job_identity_frames_algorithm_and_policy_are_bound(self):
            valid = {'job_id': COMPLETED_JOB, 'metrics': {'frames': 797,
                     'algorithm_sha256': EXPECTED['backend/algorithm.py'],
                     'geometry_settings': {'minimum_surface_coverage': .65}}}
            validate_report(valid, COMPLETED_JOB, 797)
            for target in ('job_id', 'frames', 'algorithm_sha256', 'minimum_surface_coverage'):
                wrong = json.loads(json.dumps(valid))
                if target == 'job_id':
                    wrong['job_id'] = 'different'
                elif target == 'minimum_surface_coverage':
                    wrong['metrics']['geometry_settings'][target] = .8
                else:
                    wrong['metrics'][target] = None
                with self.assertRaises(RuntimeError):
                    validate_report(wrong, COMPLETED_JOB, 797)

        def test_completed_job_missing_or_changed_source_snapshot_aborts(self):
            with tempfile.TemporaryDirectory(dir=folder) as temporary:
                base = Path(temporary)
                saved = base / 'backend/results' / COMPLETED_JOB
                saved.mkdir(parents=True)
                report = {'job_id': COMPLETED_JOB, 'metrics': {'frames': 797,
                          'algorithm_sha256': EXPECTED['backend/algorithm.py'],
                          'geometry_settings': {'minimum_surface_coverage': .65}}}
                (saved / 'report.json').write_text(json.dumps(report), encoding='utf-8')
                (saved / 'algorithm.py.snapshot').write_bytes((ROOT / 'backend/algorithm.py').read_bytes())
                original_main = ROOT / 'backend/results' / COMPLETED_JOB / 'main.py.snapshot'
                (saved / 'main.py.snapshot').write_bytes(original_main.read_bytes())
                with patch(__name__ + '.ROOT', base):
                    verify_saved_report(COMPLETED_JOB, 797)
                    (saved / 'main.py.snapshot').write_text('different source', encoding='utf-8')
                    with self.assertRaises(RuntimeError):
                        verify_saved_report(COMPLETED_JOB, 797)
                    (saved / 'main.py.snapshot').unlink()
                    with self.assertRaises(FileNotFoundError):
                        verify_saved_report(COMPLETED_JOB, 797)

    with (folder / 'tests.txt').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Decisions))
    summary = {'tests': result.testsRun, 'passed': result.wasSuccessful(),
               'http_requests': 0, 'processes_started': 0, 'processes_stopped': 0,
               'inference_requested': False, 'script_sha256': restart.digest(Path(__file__))}
    (folder / 'tests.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', choices=['3cd9d9cd-ec24-4e82-bad4-85644b7f5dd1'],
                        default='3cd9d9cd-ec24-4e82-bad4-85644b7f5dd1')
    parser.add_argument('--previous-launch', type=Path, default=SERVICE / 'partial_policy_resume/launch.json')
    parser.add_argument('--folder', type=Path, default=SERVICE / 'defect_maps_80_queue')
    parser.add_argument('--restart-folder', type=Path, default=SERVICE / 'defect_maps_80')
    parser.add_argument('--poll-seconds', type=int, default=20, choices=range(20, 61))
    parser.add_argument('--max-hours', type=float, default=2)
    parser.add_argument('--restart-when-idle', action='store_true')
    parser.add_argument('--completed-job-id', choices=[COMPLETED_JOB],
                        help='Apply saved-map colours and 80% policy to this exact completed job before restart')
    parser.add_argument('--expected-frames', type=int, choices=[797], default=797)
    parser.add_argument('--check-once', action='store_true', help='GET-only single observation; never restart')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    folder, previous_path, restart_folder = args.folder.resolve(), args.previous_launch.resolve(), args.restart_folder.resolve()
    for path in (folder, previous_path, restart_folder):
        path.relative_to(ROOT / 'backend/diagnostics')
    if not 0 < args.max_hours <= 2:
        parser.error('--max-hours must be greater than zero and at most two')
    folder.mkdir(parents=True, exist_ok=True)
    if args.self_test:
        return self_test(folder)
    # Exclusive creation prevents a second queue from sharing state or handing off.
    lock = folder / 'queue.lock'
    with lock.open('x', encoding='utf-8') as stream:
        stream.write(str(restart.os.getpid()))
    state = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'starting',
             'run_id': args.run_id, 'restart_opted_in': args.restart_when_idle and not args.check_once,
             'analysis_cancelled': False, 'inference_requested': False, 'previous_launch': str(previous_path),
             'restart_folder': str(restart_folder), 'poll_seconds': args.poll_seconds,
             'atomic_restart': False, 'limitation': 'A new run can start between the final GET and termination.'}
    if args.completed_job_id:
        state.update(completed_job_id=args.completed_job_id, expected_frames=args.expected_frames,
                     job_binding_reason='Sole incomplete saved job observed during this run; API has one analysis lock. '
                                        'Status does not directly expose saved job ID; completed report and snapshots are checked.')

    def save(status, **values):
        state.update(status=status, checked_at=datetime.now(timezone.utc).isoformat(), **values)
        temporary = folder / 'state.tmp'
        temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
        temporary.replace(folder / 'state.json')
        with (folder / 'polls.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(state) + '\n')
        print(json.dumps({'status': status, 'frames_processed': state.get('analysis', {}).get('frames_processed'),
                          'error': state.get('error')}), flush=True)

    try:
        previous = json.loads(previous_path.read_text(encoding='utf-8'))
        if Path(previous['workspace']).resolve() != ROOT or previous['status'] != 'ready':
            raise RuntimeError('Previous launch does not describe this ready workspace')
        if args.restart_when_idle and not args.check_once and restart_folder.exists():
            raise RuntimeError('Restart output folder already exists; refusing a second restart')
        expected = {**EXPECTED, str(previous_path.relative_to(ROOT)): restart.digest(previous_path),
                    'scripts/restart_owned_api.py': restart.digest(ROOT / 'scripts/restart_owned_api.py'),
                    'scripts/start_detached_services.py': restart.digest(ROOT / 'scripts/start_detached_services.py'),
                    str(Path(__file__).resolve().relative_to(ROOT)): restart.digest(Path(__file__))}
        state['source_hashes'] = expected
        deadline, first_ready, last_frame = time.monotonic() + args.max_hours * 3600, None, None
        while time.monotonic() < deadline:
            verify_owned(previous, expected)
            analysis, live = restart.get('analysis/status'), restart.get('live/status')
            action, last_frame = decide(analysis, live, args.run_id, last_frame)
            first_ready, confirmed = confirm_ready(first_ready, action, time.monotonic())
            save('ready_for_restart' if confirmed else 'waiting', analysis=analysis, live=live,
                 terminal_confirmed=confirmed)
            if args.check_once:
                return 0
            if confirmed:
                if not args.restart_when_idle:
                    return 0
                if args.completed_job_id and analysis['state'] == 'complete':
                    source_report = ROOT / 'backend/results' / args.completed_job_id / 'report.json'
                    if not source_report.is_file():
                        save('waiting_for_saved_report')
                        time.sleep(args.poll_seconds)
                        continue
                    verify_saved_report(args.completed_job_id, args.expected_frames)
                    verify_owned(previous, expected)
                    before_render = restart.get('analysis/status')
                    if decide(before_render, restart.get('live/status'), args.run_id, last_frame)[0] != 'ready':
                        raise RuntimeError('Inference became active before rendering saved outputs')
                    evidence = folder / 'completed_job_display'
                    render = [str(PYTHON), '-B', str(ROOT / 'backend/render_saved_defect_maps.py'),
                              args.completed_job_id, '--evidence', str(evidence)]
                    save('rendering_saved_outputs', renderer_command=render)
                    with (folder / 'render_stdout.txt').open('w', encoding='utf-8') as stdout, \
                            (folder / 'render_stderr.txt').open('w', encoding='utf-8') as stderr:
                        rendered = subprocess.run(render, cwd=ROOT, env=safe_environment(),
                                                  stdout=stdout, stderr=stderr, check=False)
                    if rendered.returncode:
                        raise RuntimeError(f'Saved-map rendering failed with exit code {rendered.returncode}')
                    state['completed_job_display'] = json.loads((evidence / 'summary.json').read_text(encoding='utf-8'))
                elif args.completed_job_id:
                    state['saved_render_skipped'] = 'The queued video ended without complete status.'
                # Final same-run/source/ownership check; the original helper then
                # repeats its own source, tree, analysis and live guards twice.
                verify_owned(previous, expected)
                final_analysis, final_live = restart.get('analysis/status'), restart.get('live/status')
                if decide(final_analysis, final_live, args.run_id, last_frame)[0] != 'ready':
                    raise RuntimeError('Inference became active before the restart handoff')
                if restart_folder.exists():
                    raise RuntimeError('Restart output folder already exists; refusing a second restart')
                command = [str(PYTHON), '-B', str(ROOT / 'scripts/restart_owned_api.py'),
                           '--previous-launch', str(previous_path), '--folder', str(restart_folder),
                           '--expected-algorithm-sha256', EXPECTED['backend/algorithm.py'],
                           '--expected-main-sha256', EXPECTED['backend/main.py']]
                save('handoff', analysis=final_analysis, live=final_live, command=command)
                with (folder / 'restart_stdout.txt').open('w', encoding='utf-8') as stdout, \
                        (folder / 'restart_stderr.txt').open('w', encoding='utf-8') as stderr:
                    completed = subprocess.run(command, cwd=ROOT, env=safe_environment(),
                                               stdout=stdout, stderr=stderr, check=False)
                if completed.returncode:
                    raise RuntimeError(f'Guarded restart failed with exit code {completed.returncode}; see restart_stderr.txt')
                save('restarted', restart_launch=str(restart_folder / 'launch.json'))
                return 0
            time.sleep(args.poll_seconds)
        save('timed_out', error='The same run did not become idle within the allowed wait; no restart attempted')
        return 1
    except Exception as error:
        save('aborted', error=str(error))
        return 1
    finally:
        lock.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
