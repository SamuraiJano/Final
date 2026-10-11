"""Timestamp selection contracts and model representation/geometry regression."""
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
import cv2
import numpy as np

import test_nine_view as fixtures
from test_nine_view import snapshot, box
from export_detector import preprocess, decode
from calibrate_timed_views import operation_ranges


class TimedViewsTests(unittest.TestCase):
    setUp = fixtures.NineViewTests.setUp
    open = fixtures.NineViewTests.open
    drain = fixtures.NineViewTests.drain
    def test_progressive_cpu_inference_keeps_four_timed_distinct_views(self):
        from nine_view import NineViewEngine
        engine=NineViewEngine(self.segmenter,batch_size=1,maximum_inflight=1,
            clock=self.clock,start_worker=False,progressive_timed=True,
            mask_provider=lambda view:np.ones(view.image.shape[:2],np.uint8))
        self.addCleanup(engine.close)
        cfg=snapshot(acquisition='timed',required_views=4,snapshot_interval_seconds=.4)
        engine.open('progressive',1,cfg,0.,self.clock.now)
        state=engine.fruit['progressive']
        with patch('nine_view.progress_at',side_effect=AssertionError('centre selector called')):
            for k in range(4):
                engine.observe('progressive',self.frame,box(.5),k*12,k*.4,self.clock.now)
                engine.dispatch()
                self.assertEqual(len(self.segmenter.futures),k+1)
                self.segmenter.futures[-1].set_result([fixtures.clear()])
                if k<3:self.assertIsNone(state.result)
        self.assertEqual(state.result['processed_crops'],4)
        self.assertTrue(state.result['evidence_complete'])
        self.assertEqual(state.result['view_frames'],[0,12,24,36])

    def test_hsv_silhouette_preserves_dark_defects_and_excludes_other_fruit(self):
        from nine_view import View,hsv_fruit_mask
        image=np.full((120,200,3),100,np.uint8)
        cv2.circle(image,(60,60),40,(0,140,240),-1)
        cv2.circle(image,(60,60),12,(0,0,0),-1)
        cv2.circle(image,(165,60),23,(0,140,240),-1)
        view=View(image,(20,20,100,100),0,0.,100.,0,None,{})
        mask=hsv_fruit_mask(view)
        self.assertEqual(mask[60,60],1)
        self.assertEqual(mask[60,165],0)
        self.assertEqual(mask[0,0],0)
        image[:]=100
        self.assertEqual(np.count_nonzero(hsv_fruit_mask(view)),0)

    def test_optimized_contact_preview_uses_jpeg_without_changing_metadata(self):
        from nine_view import View
        from inspection_export import write_nine_view
        view=View(np.full((32,32,3),180,np.uint8),(0,0,32,32),12,.4,100.4,0,None,{})
        frozen=SimpleNamespace(nine_view_result=dict(acquisition='timed',required_crops=4),
            nine_view_images=[view],evidence_level='contact_sheet',contact_sheet=True,
            tracking_history_by_id={},tracking_images_by_id={},algorithm_assignment={})
        with tempfile.TemporaryDirectory() as temporary,patch.dict('os.environ',{'FRUIT_CPU_OPTIMIZED':'1'}):
            output=Path(temporary)/'job';row=write_nine_view(frozen,1,output)
            self.assertTrue((output/'1/contact_sheet.jpg').is_file())
            self.assertEqual(row['view_evidence'][0]['frame'],12)
            self.assertEqual(cv2.imread(str(output/'1/contact_sheet.jpg')).shape,(540,540,3))

    def test_four_to_nine_timed_views_bypass_progress_and_close_without_exit(self):
        for required in range(4, 10):
            prior_jobs=len(self.segmenter.futures)
            key = f'run:{required}'
            cfg = snapshot(acquisition='timed', required_views=required,
                           snapshot_interval_seconds=.4)
            self.engine.open(key, required, cfg, 0., self.clock.now)
            state = self.engine.fruit[key]
            with patch('nine_view.progress_at', side_effect=AssertionError('centre selector called')):
                for k in range(required):
                    self.assertTrue(self.engine.observe(key, self.frame, box(.5), k*2, k*.4, self.clock.now))
                    # An extra incoming frame before the next timestamp is skipped.
                    self.engine.observe(key, self.frame, box(.5), k*2+1, k*.4+.05, self.clock.now)
                    if k<required-1:
                        self.engine.dispatch()
                        self.assertEqual(len(self.segmenter.futures),prior_jobs)  # wait for a complete sequence
            self.assertTrue(state.closed)
            self.drain()
            self.assertEqual(state.result['required_crops'], required)
            self.assertEqual(state.result['processed_crops'], required)
            self.assertTrue(state.result['evidence_complete'])
            self.assertEqual(state.result['acquisition'], 'timed')
            self.assertTrue(all(v['progress'] is None for v in state.result['selected_views']))

    def test_slow_consumer_does_not_burst_or_fill_missed_windows(self):
        state = self.open(acquisition='timed', required_views=4, snapshot_interval_seconds=.4)
        self.engine.observe('run:1', self.frame, box(.5), 0, .9, self.clock.now)
        self.engine.observe('run:1', self.frame, box(.5), 1, 1.2, self.clock.now)
        self.drain()
        self.assertEqual(state.result['missing_bins'], [0, 1])
        self.assertEqual(state.result['processed_crops'], 2)
        self.assertEqual(state.result['selected_crops'], 2)
        self.assertTrue(self.segmenter.futures)
        self.assertEqual(state.result['grade'], 'Class 1')
        self.assertIsNone(state.result['reason'])
        self.assertIsNone(state.result['acquisition_limitation'])
        self.assertEqual(state.result['rejected_crops']['missed_snapshot_window'], 2)

    def test_stopped_stream_grades_captured_view_without_new_repeated_fruit(self):
        from algorithm import NaartjiePipeline
        from inspection_pipeline import InspectionPipeline
        from inspection_config import InspectionConfiguration
        cfg=InspectionConfiguration();cfg.update(dict(algorithm='nine_view',nine_view=dict(
            region=(0,.05,1,.95),acquisition='timed',required_views=4,snapshot_interval_seconds=.2)))
        router=InspectionPipeline(NaartjiePipeline(self.segmenter),cfg.snapshot,run_id='stop',start_worker=False,
            mask_provider=lambda view: np.ones(view.image.shape[:2],np.uint8))
        self.addCleanup(router.close)
        router.stream_change=10.;router.timestamp=0.
        router._record(self.frame,1,box(.5),0)
        router.stream_change=0.;router.timestamp=.4
        router._record(self.frame,1,box(.5),1)
        state=router.nine.fruit['stop:1'];router.nine.expire()
        self.assertEqual(state.end_reason,'conveyor_stopped_or_scene_unchanged')
        router.nine.dispatch()
        self.segmenter.futures[-1].set_result([fixtures.clear()])
        router.nine.expire()
        self.assertEqual(state.result['grade'],'Class 1')
        self.assertEqual(state.result['processed_crops'],1)
        router._record(self.frame,2,box(.5),2)
        self.assertNotIn(2,router.routes)

    def test_partial_capture_grades_worst_processed_snapshot(self):
        state = self.open(acquisition='timed', required_views=4)
        self.engine.observe('run:1',self.frame,box(.5),0,0.,self.clock.now)
        self.engine.observe('run:1',self.frame,box(.5),1,.4,self.clock.now)
        self.engine.end('run:1','track_loss')
        self.engine.dispatch()
        shapes=[image.shape[:2] for image in self.segmenter.images[-1]]
        self.segmenter.futures[-1].set_result([fixtures.clear(),fixtures.defects(shapes[1],severity=.35)])
        self.engine.expire()
        self.assertEqual(state.result['grade'],'Class 3')
        self.assertEqual(state.result['processed_crops'],2)
        self.assertEqual(state.result['view_frames'],[0,1])
        self.assertEqual(state.result['missing_bins'],[2,3])
        self.assertFalse(state.result['evidence_complete'])
        self.assertEqual(state.result['grading_policy'],'available_views')
        self.assertIsNone(state.result['reason'])

    def test_late_publication_keeps_available_view_grade_and_measures_latency(self):
        from inspection_export import write_nine_view
        frozen=SimpleNamespace(nine_view_result=dict(grading_policy='available_views',grade='Class 2',
            status='graded_nine_view',grade_provisional=True,entry_capture_monotonic=100.,
            decision_deadline_monotonic=101.),nine_view_images=[],evidence_level='contact_sheet',
            contact_sheet=False,tracking_history_by_id={},tracking_images_by_id={},algorithm_assignment={})
        with tempfile.TemporaryDirectory() as temporary, patch('inspection_export.time.monotonic',return_value=102.):
            row=write_nine_view(frozen,1,Path(temporary)/'job')
        self.assertEqual(row['grade'],'Class 2')
        self.assertEqual(row['status'],'graded_nine_view')
        self.assertTrue(row['deadline_missed'])
        self.assertEqual(row['publication_latency_seconds'],2.)

    def test_switch_to_timed_keeps_active_progress_fruit_at_full_cadence(self):
        from algorithm import NaartjiePipeline
        from inspection_pipeline import InspectionPipeline
        from inspection_config import InspectionConfiguration
        cfg = InspectionConfiguration()
        cfg.update(dict(algorithm='nine_view', nine_view=dict(acquisition='timed')))
        surface = NaartjiePipeline(self.segmenter)
        router = InspectionPipeline(surface, cfg.snapshot, start_worker=False)
        self.addCleanup(router.close)
        router.routes[1] = dict(snapshot=snapshot(), published=False)
        router.detection_interval_seconds = .1
        router.next_detection = 1.
        with patch.object(surface, 'process_frame', return_value=[]) as process:
            router.process_frame(self.frame, 0, timestamp=.5)
            process.assert_called_once()
            self.assertIsNone(router.next_detection)
            router.routes[1]['published'] = True
            router.next_detection = 1.
            router.process_frame(self.frame, 1, timestamp=.6)
            self.assertEqual(process.call_count, 1)
            self.assertEqual(router.counters['timer_skipped_detector_frames'], 1)

    def test_contact_sheet_only_export_keeps_four_real_views_and_metadata(self):
        from nine_view import View
        from inspection_export import write_nine_view
        views = [View(np.full((32,32,3), k*50, np.uint8), (0,0,32,32), k*12,
                      k*.4, 100.+k*.4, k, None, {}, inference=dict(success=True)) for k in range(4)]
        frozen = SimpleNamespace(nine_view_result=dict(acquisition='timed',required_crops=4),
            nine_view_images=views[::-1], evidence_level='contact_sheet',contact_sheet=True,
            tracking_history_by_id={},tracking_images_by_id={},algorithm_assignment={})
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'job'
            row = write_nine_view(frozen, 1, output)
            self.assertEqual([v['frame'] for v in row['view_evidence']], [0,12,24,36])
            self.assertTrue(all(v['crop'] is None and v['defect_inference_ran'] for v in row['view_evidence']))
            self.assertEqual(sorted(p.name for p in (output/'1').iterdir()), ['contact_sheet.png','result.json'])
            self.assertEqual(cv2.imread(str(output/'1'/'contact_sheet.png')).shape, (540,540,3))
            self.assertEqual(json.loads((output/'1'/'result.json').read_text())['required_crops'], 4)


class RepresentationTests(unittest.TestCase):
    def test_runtime_hsv_full_after_rgb_geometry_and_correct_channel_order(self):
        bgr = np.array([[[0, 0, 255], [255, 0, 0]]], np.uint8)
        rgb, geometry = preprocess(bgr, 'rgb')
        hsv, other = preprocess(bgr, 'hsv')
        expected = cv2.cvtColor(np.rint(rgb[0].transpose(1,2,0)*255).astype(np.uint8),cv2.COLOR_RGB2HSV_FULL)
        np.testing.assert_array_equal(np.rint(hsv[0].transpose(1,2,0)*255), expected)
        self.assertEqual(geometry, other)
        self.assertEqual(hsv.shape, (1,3,640,640))
        # Neutral RGB padding becomes H=0,S=0,V=114, not H=S=V=114.
        np.testing.assert_allclose(hsv[0,:,0,0], [0,0,114/255.])
        self.assertGreater(hsv[0,0,320,550]*255, 160)  # full-range blue hue

    def test_geometry_inverse_and_cpu_gpu_yolo_outputs_agree(self):
        geometry = (1/3,1/3,0,140)
        cpu = [np.array([[10,150,20,160,.9]],np.float32)]
        gpu = [np.array([[[10,150,20,160,.9,0]]],np.float32)]
        a=decode('yolo',cpu,.25,geometry,(1080,1920));b=decode('yolo',gpu,.25,geometry,(1080,1920))
        np.testing.assert_array_equal(a,b)
        np.testing.assert_allclose(a[0,:4],[30,30,60,60])

    def test_operation_ranges_exclude_stopped_tail_and_transition(self):
        times=np.arange(.2,10.1,.2).tolist()
        ranges,_=operation_ranges(times,[20.]*30+[8.,4.]+[0.]*18,10.)
        self.assertEqual(len(ranges),1)
        self.assertLessEqual(ranges[0][1],5.6+1e-6)
        self.assertEqual(operation_ranges(times,[0.]*50,10.)[0],[])


if __name__ == '__main__':
    unittest.main()
