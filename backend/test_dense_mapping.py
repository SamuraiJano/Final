"""Geometry and dense-keyframe controls; analytical truth is independent of matching."""
from dataclasses import replace
import unittest
from unittest.mock import patch

import cv2
import numpy as np

import algorithm as a


def rotation_x(degrees):
    t = np.deg2rad(degrees)
    return np.array([[1., 0., 0.], [0., np.cos(t), -np.sin(t)], [0., np.sin(t), np.cos(t)]])


def render(angles, oblate=False, noisy=False):
    """Orthographic, textured sphere/oblate with a camera-x symmetry pole.

    Unlike z>0 shortcuts for tilted ellipsoids, all front quadratic roots form
    the silhouette. Rotation is supplied only to this independent renderer.
    """
    A, B, size = 82., 65. if oblate else 82., 210
    center = np.array([104.5, 104.5])
    yy, xx = np.mgrid[:size, :size]
    x, y = xx-center[0], yy-center[1]
    disc = 1.-(x/B)**2-(y/A)**2
    mask = disc >= 0
    z = A*np.sqrt(np.maximum(disc, 0))
    camera = np.stack((x, y, z), axis=-1)
    rng = np.random.default_rng(817)
    views = []
    for frame, angle in enumerate(angles):
        body = camera @ rotation_x(angle)
        fx, fy, fz = np.moveaxis(body, -1, 0)
        intensity = (145 + 24*np.sin(.19*fx+.13*fy+.21*fz)
                     + 28*np.cos(.11*fx-.27*fy+.17*fz)
                     + 20*np.sin(.31*fx+.09*fy-.13*fz)
                     + 18*np.cos(.07*fx+.21*fy+.29*fz))
        if noisy:
            intensity += rng.normal(0, 1., intensity.shape)
        channel = np.uint8(np.clip(intensity, 0, 255))
        # Orange colour keeps the glare exclusion control physically meaningful;
        # a monochrome fruit would classify its entire bright skin as glare.
        image = np.stack((np.uint8(channel*.25),channel,
                          np.uint8(np.clip(channel.astype(float)*1.3+30,0,255))),axis=-1)
        image[~mask] = 0
        views.append(a.FruitView(image, mask.astype(np.uint8), frame_index=frame))
    return views


def settings(**changes):
    return a.Settings(**{**dict(spheroid_type='auto', rotation_axis='x', rotation_direction=1,
             max_pair_angle_deg=40, transverse_angle_deg=10, image_downsample=2,
             highpass_sigma=2.5, relevant_ellipse_fraction=None, bidirectional_matching=True,
             native_matching_cost='aligned_mad', minimum_view_rotation_deg=20,
             adaptive_keyframes=True, select_rotating_views=True,
             minimum_surface_coverage=.80, minimum_longitude_coverage_deg=350,
             maximum_pair_gap_deg=40), **changes})


class DenseGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cv2.setNumThreads(1)

    def test_robust_pole_tracks_known_turns_both_axes_and_directions(self):
        from test_algorithm import AlgorithmTests
        for axis in ('x','y'):
            for direction in (-1,1):
                pole=np.array([.75,.55,.36]) if axis=='x' else np.array([.55,.75,.36])
                pole/=np.linalg.norm(pole)
                truth=[AlgorithmTests._rotation(axis,direction*k*4)@pole for k in range(91)]
                views=[a.FruitView(np.zeros((150,150,3),np.uint8),
                       AlgorithmTests._silhouette(p),frame_index=k) for k,p in enumerate(truth)]
                fitted=a.fit_spheroid(views,settings(pole_pose_method='robust_trend',
                    rotation_axis=axis,rotation_direction=direction))
                error=np.degrees(np.arccos(np.clip([abs(x@y) for x,y in
                    zip(truth,fitted.pole_axes)],0,1)))
                self.assertLess(float(error.max()),2.)

    def test_uncertain_silhouette_derivative_does_not_flip_depth(self):
        rng=np.random.default_rng(71)
        ellipses=[a.Ellipse(np.array([100.,100.]),82+rng.normal(0,.3),
                  72+(.04 if i%2 else -.04),np.array([1.,0.]),np.array([0.,1.]))
                  for i in range(65)]
        for method in ('robust_trend','projected_trend'):
            poles=a._oblate_poles(ellipses,82.,65.,settings(pole_pose_method=method))
            angles=np.degrees(np.arccos(np.clip([abs(x@y) for x,y in zip(poles,poles[1:])],0,1)))
            self.assertLess(float(angles.max()),1.)

    def test_pole_window_preserves_rapid_turns(self):
        from test_algorithm import AlgorithmTests
        for axis in ('x','y'):
            for direction in (-1,1):
                for step in (8,15,20,25,30,35,40):
                    with self.subTest(axis=axis,direction=direction,step=step):
                        pole=np.array([.75,.55,.36]) if axis=='x' else np.array([.55,.75,.36])
                        pole/=np.linalg.norm(pole)
                        truth=[AlgorithmTests._rotation(axis,direction*k*step)@pole for k in range(65)]
                        views=[a.FruitView(np.zeros((150,150,3),np.uint8),
                            AlgorithmTests._silhouette(p),frame_index=k) for k,p in enumerate(truth)]
                        fitted=a.fit_spheroid(views,settings(pole_pose_method='projected_trend',
                            rotation_axis=axis,rotation_direction=direction))
                        error=np.degrees(np.arccos(np.clip([abs(x@y) for x,y in
                            zip(truth,fitted.pole_axes)],0,1)))
                        # min(projected minor) estimates B from finitely sampled
                        # silhouettes; at 20/40-degree spacing its bias accounts
                        # for up to 4.5 degrees even with the correct sign.
                        self.assertLess(float(error.max()),5.)

    def test_silhouette_trend_uses_actual_irregular_frame_times(self):
        times=np.array([0,1,2,4,7,8,10])
        ellipses=[a.Ellipse(np.zeros(2),82.,65+.02*t*t,
                           np.array([1.,0.]),np.array([0.,1.])) for t in times]
        slopes=a._silhouette_slopes(ellipses,times,settings(pole_pose_method='robust_trend'))
        np.testing.assert_allclose(slopes,.04*times,atol=1e-10)

    def test_projected_pole_sign_handles_both_searched_components(self):
        from test_algorithm import AlgorithmTests
        for axis in ('x','y'):
            for direction in (-1,1):
                for main,side in ((6,3),(6,-3),(10,5),(10,-5),(20,10),(20,-10)):
                    with self.subTest(axis=axis,direction=direction,main=main,side=side):
                        vector=np.array([direction*main,side,0.]) if axis=='x' else np.array([side,direction*main,0.])
                        R=cv2.Rodrigues(np.deg2rad(vector))[0]
                        pole=np.array([.75,.55,.36]) if axis=='x' else np.array([.55,.75,.36])
                        pole/=np.linalg.norm(pole)
                        truth=[pole]
                        for _ in range(64):
                            truth.append(R@truth[-1])
                        views=[a.FruitView(np.zeros((150,150,3),np.uint8),
                            AlgorithmTests._silhouette(p),frame_index=k) for k,p in enumerate(truth)]
                        fitted=a.fit_spheroid(views,settings(pole_pose_method='projected_trend',
                            rotation_axis=axis,rotation_direction=direction))
                        error=np.degrees(np.arccos(np.clip([abs(x@y) for x,y in
                            zip(truth,fitted.pole_axes)],0,1)))
                        self.assertLess(float(error.max()),5.)

    def test_projected_pole_does_not_enable_incompatible_camera_axis_retry(self):
        views=render([0,7],True)
        s=settings(pole_pose_method='projected_trend',max_pair_angle_deg=20)
        model=a.fit_spheroid(views,s)
        calls=[]
        def measured(source,target,model,index,profile,**kwargs):
            calls.append((profile.image_downsample,kwargs.get('inplane_angle_deg',0.)))
            if profile.image_downsample>1:
                raise a.MappingError('Coarse observation unavailable')
            return rotation_x(7*profile.rotation_direction),.2
        with patch.object(a,'_search_rotation',side_effect=measured):
            R,error=a.estimate_rotation(*views,model,0,s,{})
        self.assertAlmostEqual(error,.2)
        self.assertTrue(all(inplane==0 for down,inplane in calls))

    def test_jacobian_equals_numerical_cross_product(self):
        lat = np.linspace(-1.4, 1.4, 21)
        lon = np.linspace(-2.9, 3.0, 23)
        for radii in ([82., 82., 82.], [82., 65., 82.], [65., 82., 82.], [53., 67., 81.]):
            rx, ry, rz = radii
            ll, pp = np.meshgrid(lat, lon, indexing='ij')
            def surface(l, p):
                return np.stack((rx*np.cos(l)*np.cos(p), ry*np.sin(l), rz*np.cos(l)*np.sin(p)), axis=-1)
            eps = 1e-6
            dl = (surface(ll+eps, pp)-surface(ll-eps, pp))/(2*eps)
            dp = (surface(ll, pp+eps)-surface(ll, pp-eps))/(2*eps)
            numerical = np.linalg.norm(np.cross(dl, dp), axis=-1)
            np.testing.assert_allclose(a._ellipsoid_jacobian(lat, lon, radii), numerical, rtol=1e-8)

    def test_sphere_band_has_full_surface_denominator(self):
        lat = (np.arange(18000)+.5)*np.pi/18000-np.pi/2
        jacobian = a._ellipsoid_jacobian(lat, np.array([0.]), [82., 82., 82.])
        fraction = jacobian[np.abs(lat)<np.deg2rad(60)].sum()/jacobian.sum()
        self.assertAlmostEqual(100*fraction, 86.6025403784, places=7)

    def test_covariance_recovers_semiaxes_and_center(self):
        view = render([0], True)[0]
        ellipse = a._ellipse(view.object_mask)
        np.testing.assert_allclose(ellipse.center, [104.5, 104.5], atol=.01)
        self.assertAlmostEqual(ellipse.major, 82, delta=.15)
        self.assertAlmostEqual(ellipse.minor, 65, delta=.15)

    def test_height_and_visibility_for_tilted_oblate(self):
        pole = np.array([.65, .20, .73]); pole /= np.linalg.norm(pole)
        matrix = np.eye(3)/82**2+(1/48**2-1/82**2)*np.outer(pole, pole)
        yy, xx = np.mgrid[-70:71:5, -70:71:5]
        z = a._height(matrix, xx.ravel(), yy.ravel())
        good = np.isfinite(z)
        points = np.column_stack((xx.ravel()[good], yy.ravel()[good], z[good]))
        np.testing.assert_allclose(np.einsum('ni,ij,nj->n', points, matrix, points), 1., atol=1e-12)
        self.assertTrue(np.all(points @ matrix[:, 2] >= -1e-12))
        # Tilted front-visible surfaces can have negative z. A z>0 test would
        # incorrectly discard these, whereas the production normal test keeps them.
        self.assertTrue(np.any(points[:, 2] < 0))
        center = np.array([100., 100.])
        view = a.FruitView(np.ones((210,210,3),np.uint8), np.ones((210,210),np.uint8))
        projected = points.copy(); projected[:, :2] += center
        _, valid, _ = a._sample_view(view, projected, [], matrix, center)
        self.assertTrue(valid.all())
        b = 2*(matrix[0,2]*points[:,0]+matrix[1,2]*points[:,1])
        back = points.copy(); back[:,2] = -b/matrix[2,2]-points[:,2]; back[:,:2] += center
        _, hidden, _ = a._sample_view(view, back, [], matrix, center)
        self.assertFalse(hidden.any())

    def test_known_visible_hemisphere_sphere(self):
        view = a.FruitView(np.ones((210,210,3),np.uint8), np.ones((210,210),np.uint8))
        points = np.array([[104.5,104.5,82.], [104.5,104.5,-82.], [186.5,104.5,0.]])
        _, valid, _ = a._sample_view(view, points, [], np.eye(3)/82**2, np.array([104.5,104.5]))
        np.testing.assert_array_equal(valid, [True,False,False])

    def test_fractional_outside_image_is_not_observed(self):
        view=a.FruitView(np.ones((20,20,3),np.uint8),np.ones((20,20),np.uint8))
        points=np.array([[-.1,10,3],[19.1,10,3],[10,-.1,3],[10,19.1,3],[10,10,3.]])
        _,valid,_=a._sample_view(view,points,[],np.eye(3),np.array([10.,10.]))
        np.testing.assert_array_equal(valid,[False,False,False,False,True])

    def test_normal_cone_keeps_points_visible_for_search_rotations(self):
        views = render([0,20], True)
        s = settings()
        model = a.fit_spheroid(views, s)
        points, _, _ = a._relevant(views[0], model, 0, s)
        self.assertGreater(len(points), 12)
        for u in (0,20,40):
            for v in (-10,0,10):
                R = cv2.Rodrigues(np.deg2rad([u,v,0.]))[0]
                rotated_normals = (points @ model.matrices[0]) @ R.T
                self.assertTrue(np.all(rotated_normals[:,2] > 0))

    def test_zero_rotation_never_generates_observed_travel(self):
        views = render([0]*17)
        with self.assertRaises(a.MappingError) as context:
            a.build_surface_map(views, settings())
        self.assertFalse(any(r.get('status')=='accepted' for r in context.exception.diagnostics))

    def test_stationary_pixel_noise_does_not_create_a_turn(self):
        with self.assertRaises(a.MappingError) as context:
            a.build_surface_map(render([0]*17, noisy=True), settings())
        self.assertFalse(any(r.get('status')=='accepted' for r in context.exception.diagnostics))

    def test_known_20_and_40_degree_pairs_sphere_and_oblate(self):
        for oblate in (False,True):
            for angle in (20.,40.):
                with self.subTest(oblate=oblate, angle=angle):
                    views = render([0,angle], oblate)
                    # A minimum at the configured search edge stays rejected;
                    # a 45-degree search makes 40 degrees an interior control.
                    s = settings(max_pair_angle_deg=45)
                    model = a.fit_spheroid(views,s)
                    measured, residual = a.estimate_rotation(*views,model,0,s)
                    vector = np.rad2deg(cv2.Rodrigues(measured)[0]).ravel()
                    self.assertAlmostEqual(vector[0],angle,delta=1.5)
                    self.assertLess(abs(vector[1]),1.5)
                    self.assertLess(residual,.58)

    def test_dense_full_revolution_recovers_measured_rotation_and_coverage(self):
        for oblate in (False,True):
            with self.subTest(oblate=oblate):
                result = a.build_surface_map(render(np.linspace(0,360,65),oblate),settings())
                self.assertAlmostEqual(result.rotation_coverage_deg,360,delta=8)
                self.assertGreaterEqual(result.observed_longitude_deg,350)
                self.assertGreaterEqual(result.observed_surface_pct,80)
                self.assertLess(result.observed_surface_pct,90)
                self.assertLessEqual(len(result.view_frames),18)
                self.assertIsNone(result.grade)  # no synthetic segmentation evidence
                self.assertTrue(result.coverage_complete)

    def test_skipped_candidates_do_not_supply_any_rotation(self):
        views = render([0]*9)
        s = settings(keyframe_minimum_rotation_deg=8)
        model = a.fit_spheroid(views,s)
        calls = []
        def measured(source,target,*args):
            calls.append((source.frame_index,target.frame_index))
            return rotation_x(10 if target.frame_index==8 else 2),.1
        with patch.object(a,'estimate_rotation',side_effect=measured), patch.object(a,'_verify_keyframe_rotation'):
            selected, _, rotations, _, records = a._select_rotating_views(views,model,s)
        self.assertEqual([v.frame_index for v in selected],[0,8])
        self.assertEqual(len(rotations),1)
        self.assertTrue(all(source==0 for source,_ in calls))
        accepted=next(r for r in records if r['status']=='accepted')
        self.assertEqual(accepted['skipped_candidate_frames'],list(range(1,8)))
        self.assertAlmostEqual(accepted['rotation_deg'],10)

    def test_unavailable_candidate_can_be_remeasured_directly(self):
        views = render([0]*9)
        s = settings(); model = a.fit_spheroid(views,s)
        def measured(source,target,*args):
            if target.frame_index<8:
                raise a.MappingError('Unreliable pair: rotation 0 deg is too small')
            self.assertEqual(source.frame_index,0)
            return rotation_x(20),.1
        with patch.object(a,'estimate_rotation',side_effect=measured), patch.object(a,'_verify_keyframe_rotation'):
            selected, _, rotations, _, _ = a._select_rotating_views(views,model,s)
        self.assertEqual([v.frame_index for v in selected],[0,8])
        self.assertEqual(len(rotations),1)

    def test_missing_frames_cannot_be_bridged(self):
        views=render([0]*12)
        for i,v in enumerate(views):
            v.frame_index=i if i<5 else i+10
        s=settings(); model=a.fit_spheroid(views,s)
        with patch.object(a,'estimate_rotation',return_value=(rotation_x(20),.1)), patch.object(a,'_verify_keyframe_rotation'):
            selected,_,_,_,records=a._select_rotating_views(views,model,s)
        self.assertTrue(any(r['status']=='split' and 'Missing' in r['reason'] for r in records))
        self.assertTrue(all((r['source_frame']<5)==(r['target_frame']<5)
                            for r in records if r['status']=='accepted'))

    def test_short_missing_silhouette_uses_one_direct_measurement(self):
        views=render([0]*7)
        for i,v in enumerate(views):
            v.frame_index=i if i<3 else i+1
        s=settings(keyframe_candidate_spacing=1,keyframe_minimum_rotation_deg=3,maximum_view_index_gap=2)
        model=a.fit_spheroid(views,s)
        calls=[]
        def measured(source,target,*args):
            calls.append((source.frame_index,target.frame_index))
            if target.frame_index<4:
                raise a.MappingError('Unobservable change')
            return rotation_x(10),.1
        with patch.object(a,'estimate_rotation',side_effect=measured),patch.object(a,'_verify_keyframe_rotation'):
            selected,_,rotations,_,records=a._select_rotating_views(views,model,s)
        self.assertEqual(calls[2],(0,4))
        self.assertEqual(selected[1].frame_index,4)
        self.assertEqual(len(rotations),len(selected)-1)
        self.assertFalse(any(r['status']=='split' for r in records))

    def test_anchor_window_cannot_be_exceeded_by_a_missing_candidate(self):
        views=render([0]*5)
        for v,f in zip(views,[0,1,2,3,9]):
            v.frame_index=f
        s=settings(keyframe_candidate_spacing=1,keyframe_minimum_rotation_deg=3,maximum_view_index_gap=8,
                   maximum_keyframe_index_gap=8)
        model=a.fit_spheroid(views,s)
        def measured(source,target,*args):
            self.assertLessEqual(target.frame_index-source.frame_index,8)
            raise a.MappingError('No observable texture change')
        with patch.object(a,'estimate_rotation',side_effect=measured):
            with self.assertRaises(a.MappingError) as context:
                a._select_rotating_views(views,model,s)
        self.assertTrue(any('window exceeded' in r.get('reason','') for r in context.exception.diagnostics))

    def test_final_application_profile_on_stationary_and_dense_truth(self):
        import main
        s=main._mapping_settings(1)
        self.assertEqual((s.image_downsample,s.highpass_sigma,s.native_point_preblur_sigma),(2,2.5,0))
        self.assertEqual((s.minimum_surface_coverage,s.minimum_longitude_coverage_deg),(.8,350))
        self.assertEqual(s.max_pair_error,.58)
        for noisy in (False,True):
            with self.assertRaises(a.MappingError):
                a.build_surface_map(render([0]*17,noisy=noisy),s)
        result=a.build_surface_map(render(np.linspace(0,360,65)),s)
        self.assertGreaterEqual(result.observed_surface_pct,80)
        self.assertGreaterEqual(result.observed_longitude_deg,350)
        self.assertAlmostEqual(result.rotation_coverage_deg,360,delta=8)

    def test_inverse_disagreement_never_becomes_accepted(self):
        views=render([0,20]); s=settings(); model=a.fit_spheroid(views,s)
        with patch.object(a,'_search_rotation',side_effect=[(rotation_x(20),.1),(rotation_x(-32),.1)]):
            with self.assertRaisesRegex(a.MappingError,'disagree'):
                a._verify_keyframe_rotation(*views,model,rotation_x(20),s,{})

    def test_longitude_seam_and_defect_union_with_known_geometry(self):
        views=render(np.arange(0,361,20))
        for view in views:
            view.defect_masks={'test':view.object_mask.copy()}
        s=settings(adaptive_keyframes=False,select_rotating_views=False,defect_observations_complete=True)
        with patch.object(a,'estimate_rotation',return_value=(rotation_x(20),.1)):
            result=a.build_surface_map(views,s)
        self.assertGreater(result.observed_surface_pct,85)
        self.assertAlmostEqual(result.observed_longitude_deg,360)
        np.testing.assert_array_equal(result.defect_maps['test']>0,result.observed_mask>0)
        self.assertAlmostEqual(result.defect_pct_of_observed,100)
        self.assertTrue(result.observed_mask[:,0].any() and result.observed_mask[:,-1].any())

    def test_second_measured_revolution_contributes_defects_without_duplicate_area(self):
        views=render(np.arange(0,721,20))
        for i,view in enumerate(views):
            view.defect_masks={'late':view.object_mask.copy() if i>=18 else np.zeros_like(view.object_mask)}
        s=settings(adaptive_keyframes=False,select_rotating_views=False,defect_observations_complete=True)
        with patch.object(a,'estimate_rotation',return_value=(rotation_x(20),.1)):
            result=a.build_surface_map(views,s)
        self.assertLess(result.observed_surface_pct,88)
        self.assertGreater(result.defect_pct_of_observed,99)
        self.assertEqual(result.observed_longitude_deg,360)

    def test_dense_small_step_profile_recovers_a_full_revolution(self):
        s=settings(keyframe_candidate_spacing=1,keyframe_minimum_rotation_deg=3,maximum_keyframe_index_gap=8,
                   exclude_specular_texture=True)
        for oblate in (False,True):
            with self.subTest(oblate=oblate):
                result=a.build_surface_map(render(np.linspace(0,360,65),oblate),s)
                self.assertAlmostEqual(result.rotation_coverage_deg,360,delta=8)
                self.assertGreaterEqual(result.observed_surface_pct,80)
                self.assertGreaterEqual(result.observed_longitude_deg,350)

    def test_wider_dense_retry_is_two_axis_and_keeps_independent_checks(self):
        views=render([0,20]); s=settings(); model=a.fit_spheroid(views,s); details={}
        with patch.object(a,'_search_rotation',side_effect=[a.MappingError('coarse residual unavailable'),
                    (rotation_x(20),.2),(rotation_x(20),.2),(rotation_x(-20),.2)]) as search:
            R,_=a.estimate_rotation(*views,model,0,s,details)
        self.assertAlmostEqual(np.rad2deg(cv2.Rodrigues(R)[0][0,0]),20)
        self.assertTrue(details['native_retry_accepted'])
        self.assertEqual(details['native_retry_inplane_angle_limit_deg'],0)
        self.assertTrue(all(call.kwargs.get('inplane_angle_deg')==0 for call in search.call_args_list[1:]))


if __name__=='__main__':
    unittest.main()
