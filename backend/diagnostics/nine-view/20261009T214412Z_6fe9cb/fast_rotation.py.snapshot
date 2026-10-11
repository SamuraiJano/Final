"""Measured skin rotation from sparse optical flow and bounded texture refinement.

Conveyor displacement and roller speed never supply rotation. Failed feature
measurements raise MappingError; the caller decides whether to spend a recovery
search. All coordinates remain in original crop pixels.
"""
from dataclasses import replace
import cv2
import numpy as np
from scipy.optimize import least_squares

import algorithm as a


def _track_fit(source, target, model, index, settings, maximum_features=80, initial_rotation=None):
    first, second = model.ellipses[index:index + 2]
    h = max(source.image.shape[0], target.image.shape[0])
    w = max(source.image.shape[1], target.image.shape[1])
    images = []
    for view in (source, target):
        canvas = np.zeros((h, w), np.uint8)
        canvas[:view.image.shape[0], :view.image.shape[1]] = view.image[:, :, 1]
        images.append(canvas)
    margin = np.deg2rad(np.hypot(settings.max_pair_angle_deg,
                              settings.transverse_angle_deg) + 2)
    interior = cv2.erode((source.object_mask > 0).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    hsv = cv2.cvtColor(source.image, cv2.COLOR_BGR2HSV)
    if settings.exclude_specular_texture:
        glare = cv2.dilate(((hsv[..., 1] < 102) & (hsv[..., 2] > 90)).astype(np.uint8),
                          np.ones((3, 3), np.uint8))
        interior &= glare == 0
    mask = np.zeros((h, w), np.uint8)
    mask[:interior.shape[0], :interior.shape[1]] = interior.astype(np.uint8) * 255
    points = cv2.goodFeaturesToTrack(images[0], maximum_features * 3, .015, 4,
                                    mask=mask, blockSize=5)
    minimum = max(12, settings.min_pair_points)
    if points is None or len(points) < minimum:
        raise a.MappingError('Too few reliable peel features')
    relative = points[:, 0].astype(float) - first.center
    lifted = np.column_stack((relative, a._height(model.matrices[index], relative[:, 0], relative[:, 1])))
    normals = lifted @ model.matrices[index]
    visible = (np.isfinite(lifted).all(axis=1) &
               (normals[:, 2] > np.sin(margin) * np.linalg.norm(normals, axis=1)))
    points = points[visible][:maximum_features]
    if len(points) < minimum:
        raise a.MappingError('Too few peel features in the surface visibility cone')
    initial = points + (second.center - first.center).astype(np.float32)[None, None, :]
    if initial_rotation is not None:
        relative = points[:, 0].astype(float) - first.center
        lifted = np.column_stack((relative, a._height(model.matrices[index], relative[:, 0], relative[:, 1])))
        initial = ((lifted @ initial_rotation.T)[:, :2] + second.center).astype(np.float32)[:, None]
    options = dict(winSize=(15, 15), maxLevel=3,
                   criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, .01))
    if initial_rotation is not None:
        # A measured chain already places each feature near its native target.
        # Re-running the coarse pyramid can alias repetitive peel texture.
        options.update(winSize=(9, 9), maxLevel=0)
    tracked, ok, error = cv2.calcOpticalFlowPyrLK(images[0], images[1], points,
                                initial.copy(), flags=cv2.OPTFLOW_USE_INITIAL_FLOW, **options)
    if tracked is None:
        raise a.MappingError('Peel optical flow unavailable')
    backward, back_ok, _ = cv2.calcOpticalFlowPyrLK(images[1], images[0], tracked,
                                 points.copy(), flags=cv2.OPTFLOW_USE_INITIAL_FLOW, **options)
    if backward is None:
        raise a.MappingError('Reverse peel optical flow unavailable')
    source_xy, target_xy = points[:, 0].astype(float), tracked[:, 0].astype(float)
    fb = np.linalg.norm(backward[:, 0] - points[:, 0], axis=1)
    th, tw = target.object_mask.shape
    ix, iy = np.rint(target_xy).astype(int).T
    good = ((ok.ravel() > 0) & (back_ok.ravel() > 0) & (fb <= 1.) &
            np.isfinite(target_xy).all(axis=1) & (error.ravel() < 25.) &
            (ix >= 0) & (iy >= 0) & (ix < tw) & (iy < th))
    good &= target.object_mask[np.clip(iy, 0, th - 1), np.clip(ix, 0, tw - 1)] > 0
    source_xy, target_xy = source_xy[good], target_xy[good]
    if len(source_xy) < minimum:
        raise a.MappingError('Too few bidirectionally tracked peel features')
    relative = source_xy - first.center
    lift = a._height(model.matrices[index], relative[:, 0], relative[:, 1])
    points3 = np.column_stack((relative, lift))
    axis = 0 if settings.rotation_axis == 'x' else 1
    other = 1 - axis

    def vector(parameters):
        result = np.zeros(3)
        result[axis] = settings.rotation_direction * parameters[0]
        result[other] = parameters[1]
        return result

    def residual(parameters):
        rotation = cv2.Rodrigues(vector(parameters))[0]
        projected = (points3 @ rotation.T)[:, :2] + second.center
        return (projected - target_xy).ravel()

    def analytical_jacobian(parameters):
        _, derivatives = cv2.Rodrigues(vector(parameters))
        return np.column_stack((
            ((points3 @ derivatives[axis].reshape(3, 3).T)[:, :2] * settings.rotation_direction).ravel(),
            (points3 @ derivatives[other].reshape(3, 3).T)[:, :2].ravel()))

    upper = np.deg2rad([settings.max_pair_angle_deg, settings.transverse_angle_deg])
    if upper[1] <= 0:
        raise a.MappingError('Feature fit requires a positive transverse bound')
    # A linearised projection supplies a measured initial guess, not a speed prior.
    basis = np.zeros((2, 3))
    basis[0, axis], basis[1, other] = settings.rotation_direction, 1.
    jacobian = np.stack([np.cross(v, points3)[:, :2].ravel() for v in basis], axis=1)
    displacement = (target_xy - second.center - points3[:, :2]).ravel()
    seed = np.linalg.lstsq(jacobian, displacement, rcond=None)[0]
    seed = np.clip(seed, [1e-8, -upper[1] + 1e-8], upper - 1e-8)
    fit = least_squares(residual, seed, jac=analytical_jacobian, bounds=([0., -upper[1]], upper),
                        loss='soft_l1', f_scale=.75, max_nfev=18,
                        ftol=1e-5, xtol=1e-5, gtol=1e-5)
    distances = np.linalg.norm(residual(fit.x).reshape(-1, 2), axis=1)
    inliers = distances <= 1.5
    if inliers.sum() < minimum or inliers.mean() < .65:
        raise a.MappingError('Peel features do not support a rigid rotation')
    spread = np.linalg.eigvalsh(np.cov(source_xy[inliers].T))
    if spread[0] < max(4., (.04 * model.A) ** 2):
        raise a.MappingError('Peel features have insufficient spatial support')
    singular = np.linalg.svd(fit.jac, compute_uv=False)
    if singular[-1] < 1e-6 or singular[0] / singular[-1] > 100:
        raise a.MappingError('Peel rotation is poorly constrained')
    rms = float(np.sqrt(np.mean(distances[inliers] ** 2)))
    if rms > 1.:
        raise a.MappingError('Peel reprojection residual exceeds one pixel')
    return cv2.Rodrigues(vector(fit.x))[0], dict(
        features=len(points), feature_inliers=int(inliers.sum()), feature_reprojection_px=rms,
        feature_fb_median_px=float(np.median(fb[good])))


def estimate_feature_rotation(source, target, model, index, settings, details=None, initial_rotation=None):
    """Independent directional fits, local native texture check and inverse gate."""
    forward, evidence = _track_fit(source, target, model, index, settings, initial_rotation=initial_rotation)
    reverse_model = a._subset_spheroid(model, [index + 1, index])
    backward, reverse_evidence = _track_fit(target, source, reverse_model, 0,
                            replace(settings, rotation_direction=-settings.rotation_direction),
                            initial_rotation=forward.T)

    def angle(matrix):
        return float(np.rad2deg(np.linalg.norm(cv2.Rodrigues(matrix)[0])))

    inverse = angle(backward @ forward)
    if inverse > settings.keyframe_inverse_tolerance_deg:
        raise a.MappingError(f'Feature inverse rotations disagree: {inverse:.2f} degrees')
    native = replace(settings, image_downsample=1, matching_cost='aligned_mad',
                     bidirectional_matching=True, min_pair_angle_deg=.25)
    initial = np.rad2deg(cv2.Rodrigues(forward)[0]).ravel()
    rotation, error = a._search_rotation(source, target, model, index, native,
                                        initial_rotation_deg=initial, local_radius_deg=2.)
    forward_difference = angle(rotation @ forward.T)
    backward_difference = angle(rotation @ backward)
    if max(forward_difference, backward_difference) > settings.keyframe_inverse_tolerance_deg:
        raise a.MappingError('Local texture refinement disagrees with measured peel motion')
    axis = 0 if settings.rotation_axis == 'x' else 1
    degrees = np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel()
    if abs(degrees[axis]) < max(.25, settings.min_pair_angle_deg):
        raise a.MappingError('Measured peel rotation is below the observable minimum')
    if details is not None:
        details.update(evidence, feature_rotation_verified=True, rotation_estimator='features',
            image_downsample=1, matching_cost_used='aligned_mad',
            inverse_disagreement_deg=inverse, forward_disagreement_deg=forward_difference,
            backward_disagreement_deg=backward_difference,
            independent_backward_reprojection_px=reverse_evidence['feature_reprojection_px'],
            local_search_radius_deg=2.)
    return rotation, error
