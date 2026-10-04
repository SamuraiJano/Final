"""Independent known identities for conveyor association and pipeline isolation."""
from dataclasses import replace
import csv
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from conveyor_identity import ConveyorIdentityManager, ConveyorIdentitySettings
from fruit_identity import FruitIdentityGuard
from algorithm import FruitView, NaartjiePipeline


def box(x=100., y=100., width=60., height=60.):
    return [x, y, x+width, y+height]


class ConveyorIdentityTests(unittest.TestCase):
    def setUp(self):
        self.manager = ConveyorIdentityManager(ConveyorIdentitySettings())

    def update(self, frame, ids, boxes, time=None):
        return self.manager.update(boxes, ids, frame, (800, 800), frame/30 if time is None else time)

    def seed(self, raw_id=19):
        for frame in range(3):
            result = self.update(frame, [raw_id], [box(y=100+13*frame)])
        return result[0]['fruit_id']

    def test_normal_tracking_has_permanent_id_independent_of_tracker_numbers(self):
        identity = self.seed()
        result = self.update(3, [19], [box(y=139)])[0]
        self.assertEqual(identity, 1)
        self.assertEqual(result['fruit_id'], identity)
        self.assertFalse(result['identity_corrected'])
        state = self.manager.states[identity]
        self.assertEqual(state.current_tracker_id, 19)
        self.assertEqual(state.status, 'active')
        self.assertEqual(state.observations, 4)
        self.assertAlmostEqual(state.recent_velocity[1], 390)
        self.assertEqual([point[0] for point in state.history], [0, 1/30, 2/30, 3/30])

    def test_explicit_two_fruit_swap_follows_approaching_trajectories(self):
        for frame in range(3):
            result = self.update(frame, [5, 9], [box(x=100+frame*2, y=100+13*frame),
                                                box(x=220-frame*2, y=130+13*frame)])
        identities = [row['fruit_id'] for row in result]
        result = self.update(3, [9, 5], [box(x=106, y=139), box(x=214, y=169)])
        self.assertEqual([row['fruit_id'] for row in result], identities)
        self.assertTrue(all(row['identity_corrected'] for row in result))
        self.assertTrue(all(row['prediction_error'] < 1e-9 for row in result))

    def test_local_order_supports_correction_even_at_the_first_swap(self):
        original = self.update(0, [5, 9], [box(y=100), box(x=110, y=190)])
        result = self.update(1, [9, 5], [box(y=113.2), box(x=110, y=203.2)])
        self.assertEqual([row['fruit_id'] for row in result], [row['fruit_id'] for row in original])
        self.assertTrue(all(row['reason'] == 'trajectory_order_correction' for row in result))

    def test_independent_lanes_can_cross_in_y_without_identity_correction(self):
        identities = None
        for frame in range(4):
            result = self.update(frame, [5, 9], [box(x=100, y=100+20*frame), box(x=400, y=125+5*frame)])
            if identities is None:
                identities = [row['fruit_id'] for row in result]
            self.assertEqual([row['fruit_id'] for row in result], identities)
            self.assertFalse(any(row['identity_corrected'] for row in result))
        self.assertGreater(result[0]['cy'], result[1]['cy'])

    def test_temporarily_lost_fruit_recovers_with_a_new_tracker_id(self):
        identity = self.seed()
        self.update(3, [], [])
        self.assertEqual(self.manager.states[identity].status, 'lost')
        result = self.update(4, [93], [box(y=152)])[0]
        self.assertEqual(result['fruit_id'], identity)
        self.assertTrue(result['identity_corrected'])
        self.assertAlmostEqual(result['predicted_cy'], 182)
        self.assertEqual(self.manager.metadata[identity]['source_tracker_ids'], [19, 93])

    def test_real_new_fruit_gets_monotonic_id_that_is_never_reused(self):
        identity = self.seed()
        result = self.update(3, [19, 99], [box(y=139), box(x=500, y=20)])
        self.assertEqual([row['fruit_id'] for row in result], [identity, 2])
        self.manager.drop(identity)
        result = self.update(4, [19, 99], [box(x=200, y=300), box(x=500, y=33)])[0]
        self.assertEqual(result['fruit_id'], 3)

    def test_small_backwards_box_jitter_does_not_change_identity(self):
        identity = self.seed()
        result = self.update(3, [19], [box(y=125.5)])[0]
        self.assertEqual(result['fruit_id'], identity)
        self.assertAlmostEqual(result['prediction_error'], 13.5)
        self.assertEqual(self.manager.metadata[identity]['identity_status'], 'motion_consistent')

    def test_variable_timestamps_use_pixels_per_second_not_frame_number(self):
        times = [0., .032, .11, .147, .225]
        for frame, time in enumerate(times):
            result = self.update(frame, [19], [box(y=100+395.83*time)], time)[0]
            self.assertEqual(result['fruit_id'], 1)
            if frame:
                self.assertAlmostEqual(result['prediction_error'], 0, places=9)
                self.assertAlmostEqual(result['vy'], 395.83, places=8)
                self.assertEqual(result['timestamp_source'], 'timestamp')

    def test_missing_invalid_and_repeated_timestamps_fall_back_to_measured_fps(self):
        self.manager.set_frame_rate(25)
        for frame, stamp in enumerate((0., 0., float('nan'), None)):
            result = self.manager.update([box(y=100+15.8332*frame)], [19], frame, (800,800), stamp)[0]
            self.assertEqual(result['fruit_id'], 1)
            self.assertAlmostEqual(result['timestamp'], frame/25)
            self.assertEqual(result['timestamp_source'], 'timestamp' if frame == 0 else 'frame_rate_fallback')

    def test_large_backward_jump_cannot_contaminate_existing_fruit(self):
        identity = self.seed()
        result = self.update(3, [19], [box(y=20)])[0]
        self.assertNotEqual(result['fruit_id'], identity)
        self.assertEqual(result['reason'], 'motion_or_size_discontinuity')
        self.assertEqual(self.manager.metadata[identity]['identity_status'], 'uncertain')

    def test_expired_lost_identity_does_not_reopen(self):
        identity = self.seed()
        result = self.update(33, [19], [box(y=529)])[0]
        self.assertNotEqual(result['fruit_id'], identity)

    def test_buffer_boundary_is_inclusive_and_can_use_tracker_buffer(self):
        self.manager = ConveyorIdentityManager(ConveyorIdentitySettings(), lost_track_buffer_frames=5)
        identity = self.seed()
        result = self.update(7, [93], [box(y=191)])[0]
        self.assertEqual(result['fruit_id'], identity)
        self.assertEqual(self.manager.configuration()['effective_lost_track_buffer_frames'], 5)

    def test_one_to_one_association_and_permuted_detection_order(self):
        expected = []
        for reverse in (False, True):
            manager = ConveyorIdentityManager()
            first = manager.update([box(), box(x=300)], [5,9], 0, (800,800), 0)
            rows = [(9, box(y=113.2)), (5, box(x=300,y=113.2))]
            if reverse:
                rows.reverse()
            result = manager.update([item[1] for item in rows], [item[0] for item in rows], 1, (800,800), 1/30)
            expected.append({row['tracker_id']: row['fruit_id'] for row in result})
            self.assertEqual(len({row['fruit_id'] for row in result}), 2)
        self.assertEqual(expected[0], expected[1])
        self.assertEqual(expected[0], {9:1,5:2})

    def test_ambiguous_new_id_is_not_arbitrarily_attached(self):
        for frame in range(3):
            self.update(frame, [5, 9], [box(x=100,y=100+13*frame), box(x=120,y=100+13*frame)])
        result = self.update(3, [93], [box(x=110,y=139)])[0]
        self.assertNotIn(result['fruit_id'], (1,2))
        self.assertEqual(result['reason'], 'ambiguous_association')
        self.assertTrue(all(meta['identity_status'] == 'uncertain' for meta in self.manager.metadata.values()))

    def test_one_detection_cannot_take_two_fruit_ids(self):
        self.seed()
        result = self.update(3, [93,94], [box(x=99,y=139), box(x=101,y=139)])
        self.assertEqual(len(set(row['fruit_id'] for row in result)),2)
        self.assertTrue(all(row['reason']=='ambiguous_association' for row in result))

    def test_local_neighbour_geometry_is_scale_independent(self):
        a,b,c=box(),box(x=110,y=200),box(x=400,y=200)
        for scale in (.25,1,4):
            self.assertTrue(self.manager._local(np.array(a)*scale,np.array(b)*scale))
            self.assertFalse(self.manager._local(np.array(a)*scale,np.array(c)*scale))

    def test_lateral_separation_removes_previous_order_constraint(self):
        self.manager = ConveyorIdentityManager(replace(ConveyorIdentitySettings(),enable_motion_validation=False))
        self.update(0,[5,9],[box(y=100),box(x=110,y=200)])
        a,b=list(self.manager.states.values())
        self.assertFalse(self.manager._order_conflict(a,b,np.array(box(x=100,y=220)),np.array(box(x=400,y=120)),np.array([130,140]),np.array([140,240])))

    def test_scene_velocity_learns_only_after_confirmed_history(self):
        for frame in range(5):
            result = self.update(frame, [5,9,12], [box(x=100+200*i,y=100+10*frame) for i in range(3)])
        self.assertAlmostEqual(self.manager.scene_velocity[1],300)
        self.assertTrue(all(row['fruit_id'] == i+1 for i,row in enumerate(result)))

    def test_one_noisy_observation_does_not_dominate_velocity(self):
        for frame in range(8):
            y = 100+13*frame+(7 if frame==6 else 0)
            self.update(frame, [19], [box(y=y)])
        self.assertAlmostEqual(self.manager.states[1].recent_velocity[1],390)

    def test_edge_growth_keeps_identity_without_using_clipped_scene_velocity(self):
        for frame, bounds in enumerate(([100,0,120,3],[90,0,130,13],[90,0,130,25],[90,5,130,45])):
            result = self.update(frame,[19],[bounds])[0]
            self.assertEqual(result['fruit_id'],1)
        self.assertEqual(len(self.manager.scene_samples),0)

    def test_debug_csv_and_overlay_preserve_source_pixels(self):
        settings = replace(ConveyorIdentitySettings(),debug_identity_overlay=True,debug_identity_csv=True)
        self.manager = ConveyorIdentityManager(settings)
        frame = np.zeros((800,800,3),np.uint8)
        with tempfile.TemporaryDirectory() as name:
            self.manager.configure_debug(Path(name))
            self.update(0,[5,9],[box(),box(x=300)])
            with patch('sys.stdout',new_callable=io.StringIO) as stdout:
                self.update(1,[9,5],[box(y=113.2),box(x=300,y=113.2)])
                self.assertIn('IDENTITY CORRECTION',stdout.getvalue())
            overlay = self.manager.draw_debug(frame)
            self.manager.write_debug(frame)
            self.manager.close_debug()
            self.assertFalse(frame.any())
            self.assertTrue(overlay.any())
            with (Path(name)/'identity_debug.csv').open() as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),4)
            self.assertEqual(set(rows[0]),set(self.manager.CSV_FIELDS))
            self.assertEqual(rows[-1]['identity_corrected'],'True')
            self.assertTrue((Path(name)/'identity_debug.mp4').stat().st_size>0)
        json.dumps(self.manager.metadata)

    def test_production_corrections_do_not_print_or_create_debug_files(self):
        self.update(0,[5,9],[box(),box(x=300)])
        with patch('sys.stdout',new_callable=io.StringIO) as stdout:
            self.update(1,[9,5],[box(y=113.2),box(x=300,y=113.2)])
        self.assertEqual(stdout.getvalue(),'')

    def test_bad_boxes_duplicate_ids_and_nonincreasing_frames_rejected(self):
        for boxes,ids in [([box(),box()],[5,5]),([box()],[1.5]),([box()],[0]),([[0,0,0,1]],[1])]:
            with self.assertRaises(ValueError):
                self.update(0,ids,boxes)
        self.update(0,[1],[box()])
        with self.assertRaises(ValueError):
            self.update(0,[1],[box()])

    def test_configuration_and_environment_are_explicit_and_validated(self):
        with tempfile.TemporaryDirectory() as name:
            config=Path(name)/'settings.json'
            config.write_text(json.dumps({'enable_order_validation':False,'fallback_fps':25}))
            with patch.dict(os.environ,{'FRUIT_IDENTITY_CONFIG':str(config),'FRUIT_DEBUG_IDENTITY_CSV':'true'}):
                settings=ConveyorIdentitySettings.from_environment()
            self.assertFalse(settings.enable_order_validation)
            self.assertTrue(settings.debug_identity_csv)
            self.assertEqual(settings.fallback_fps,25)
        for values in ({'fallback_fps':0},{'history_observations':2},{'prediction_gate_diameters':float('nan')},{'enable_order_validation':1}):
            with self.assertRaises(ValueError):
                ConveyorIdentitySettings(**values)


class ConveyorPipelineTests(unittest.TestCase):
    def test_mapping_views_use_stable_fruit_id_across_swap_and_missed_frame(self):
        detector=SimpleNamespace(names={0:'fruit'},tracker=SimpleNamespace(max_time_lost=30))
        pipeline=NaartjiePipeline(SimpleNamespace(names={0:'spot'}),detector)
        frame=np.zeros((800,800,3),np.uint8)
        def capture(image,identity,bounds,index):
            pipeline.views_by_id.setdefault(identity,[]).append(FruitView(image.copy(),frame_index=index))
            return True
        schedules=[(0,[5,9],[box(),box(x=300)]),(1,[5,9],[box(y=113),box(x=300,y=113)]),
                   (2,[9,5],[box(y=126),box(x=300,y=126)]),(3,[],[]),
                   (4,[93,5],[box(y=152),box(x=300,y=152)])]
        with patch.object(pipeline,'add_tracked_detection',side_effect=capture):
            for index,ids,bounds in schedules:
                detector.track=lambda *a,**kw:[SimpleNamespace(boxes=SimpleNamespace(id=np.array(ids),cls=np.zeros(len(ids)),xyxy=np.array(bounds).reshape(-1,4)))]
                pipeline.process_frame(frame,index,timestamp=index/30)
        self.assertEqual(set(pipeline.views_by_id),{1,2})
        self.assertEqual([view.frame_index for view in pipeline.views_by_id[1]],[0,1,2,4])
        self.assertEqual([row['raw_track_id'] for row in pipeline.tracking_history_by_id[1]],[5,5,9,93])
        self.assertEqual([row['timestamp'] for row in pipeline.tracking_history_by_id[1]],[0,1/30,2/30,4/30])
        self.assertEqual(pipeline.identity_guard.configuration()['effective_lost_track_buffer_frames'],30)

    def test_disabled_conveyor_manager_restores_existing_guard(self):
        pipeline=NaartjiePipeline(SimpleNamespace(names={0:'spot'}),identity_settings=ConveyorIdentitySettings(conveyor_identity_validation=False))
        self.assertIsInstance(pipeline.identity_guard,FruitIdentityGuard)

    def test_uploaded_video_forwards_decoded_variable_pts_and_closes_debug(self):
        import cv2
        import main
        times=[0.,.032,.12]
        class Video:
            index=-1
            released=False
            def isOpened(self): return True
            def read(self):
                self.index+=1
                return (True,np.zeros((400,400,3),np.uint8)) if self.index<len(times) else (False,None)
            def get(self,prop):
                return 30 if prop==cv2.CAP_PROP_FPS else len(times) if prop==cv2.CAP_PROP_FRAME_COUNT else times[self.index]*1000
            def release(self): self.released=True
        video=Video()
        detector=SimpleNamespace(names={0:'fruit'},tracker=SimpleNamespace(max_time_lost=30))
        detector.track=lambda *a,**kw:[SimpleNamespace(boxes=SimpleNamespace(id=np.array([19]),cls=np.array([0]),xyxy=np.array([box(y=100+395.83*times[video.index])])))]
        pipeline=NaartjiePipeline(SimpleNamespace(names={0:'spot'}),detector)
        histories=[]
        def finish(candidate,identity,_output):
            histories.append(candidate.tracking_history_by_id[identity].copy())
            candidate.drop_track(identity)
        with tempfile.TemporaryDirectory() as name, patch.object(main,'_make_pipeline',return_value=(pipeline,detector,pipeline.segmenter)), patch.object(main.cv2,'VideoCapture',return_value=video), patch.object(main,'_finish_track',side_effect=finish), patch.object(pipeline,'add_tracked_detection',return_value=False), patch.object(pipeline,'close_identity_debug',wraps=pipeline.close_identity_debug) as close:
            rows=main.analyze_video(Path('test.mp4'),Path(name))
        self.assertEqual(rows,[])
        self.assertTrue(video.released)
        close.assert_called_once()
        self.assertEqual(len(histories),1)
        self.assertEqual([row['timestamp'] for row in histories[0]],times)
        self.assertEqual([row['fruit_id'] for row in histories[0]],[1,1,1])
        self.assertEqual(pipeline.identity_guard.fps,30)


if __name__=='__main__':
    unittest.main()
