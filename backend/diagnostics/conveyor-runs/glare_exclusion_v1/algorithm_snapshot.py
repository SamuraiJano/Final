"""Naartjie multiview spheroid mapping and area based grading.

Research basis: Albiol et al., Sensors 2021, 21, 2232 (spheroid fit and
3D rotation); Albiol et al., Sensors 2022, 22, 5452 (single surface map).
This is an independent OpenCV implementation of those methods, adapted to
tracked naartjie crops and their optional defect masks. It is not the
original authors' software, and its speed and accuracy require validation
on the actual conveyor.

Core input: ordered BGR crops of ONE tracked fruit with optional fruit and
defect masks. NaartjiePipeline below provides the optional model connection:
D-FINE detection + TrackTrack, crop, GrabCut, D-FINE SEG defect segmentation, then
build_surface_map. Existing trackers can use add_tracked_detection instead.
Sorting actuator control is outside this video analysis app.

Requires: numpy, opencv-python (or opencv-python-headless).
CLI: python algorithm.py views.json --out output_dir
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np


class MappingError(RuntimeError):
    """The images do not support a reliable surface reconstruction."""


@dataclass
class FruitView:
    image: np.ndarray
    object_mask: np.ndarray | None = None
    defect_masks: Mapping[str, np.ndarray] = field(default_factory=dict)
    frame_index: int = 0
    fruit_bbox: tuple[int, int, int, int] | None = None  # detector box inside crop


@dataclass
class Settings:
    spheroid_type: str = "oblate"  # also accepts "sphere" or "auto"
    spherical_tolerance: float = 0.06
    rotation_axis: str = "y"  # image axis, "x" or "y"; set from roller orientation
    rotation_direction: int = 1  # +1 or -1 around axis, right-hand rule
    max_pair_angle_deg: float = 55.0
    transverse_angle_deg: float = 10.0
    search_step_deg: float = 1.0  # paper uses 1 deg; 2 is a practical initial value
    image_downsample: int = 4
    highpass_sigma: float = 1.25
    point_percentile: float = 97.0
    min_pair_points: int = 12
    min_pair_angle_deg: float = 1.0
    max_pair_error: float = 0.58  # normalized high-pass error; validate on real fruit
    min_texture: float = 0.006  # green channel intensity 0-1
    matching_cost: str = 'mad'  # paper Eq. 17; normalized cost retained for ablation
    bidirectional_matching: bool = False  # engineering extension; evaluate separately
    select_rotating_views: bool = False
    minimum_view_rotation_deg: float = 3.0
    maximum_view_index_gap: int = 8
    texture_metric: str = 'selected_rms'
    exclude_specular_texture: bool = False  # bright low-saturation glare is not surface texture
    enforce_uniform_pair_rotation: bool = False
    max_latitude_deg: float = 60.0
    map_angle_step_deg: float | None = None
    grabcut_iterations: int = 3
    minimum_surface_coverage: float = 0.65
    minimum_rotation_coverage_deg: float = 0.0
    maximum_pair_gap_deg: float | None = None
    pole_pose_tolerance_deg: float = 5.0
    pole_pose_method: str = 'silhouette_trend'
    minimum_mask_box_fraction: float = 0.4
    minimum_silhouette_solidity: float = 0.95
    class_1_max_defect_pct: float = 10.0  # upper boundary is exclusive
    class_2_max_defect_pct: float = 20.0
    defect_observations_complete: bool = False  # true only if segmentation ran on every view


@dataclass
class Ellipse:
    center: np.ndarray  # full resolution image pixel coordinates
    major: float
    minor: float
    v_major: np.ndarray  # 2D unit eigenvector
    v_minor: np.ndarray


@dataclass
class Spheroid:
    A: float  # equal (equatorial) semi-axis for oblate, in original pixels
    B: float  # pole semi-axis, in original pixels
    ellipses: list[Ellipse]
    matrices: list[np.ndarray]  # x^T M_i x = 1, camera centered pixels
    reference_axes: np.ndarray  # fruit-to-camera orthonormal basis at reference
    reference_index: int
    pole_axes: list[np.ndarray]


@dataclass
class MapResult:
    bgr_map: np.ndarray
    observed_mask: np.ndarray
    defect_maps: dict[str, np.ndarray]
    longitude_deg: np.ndarray
    latitude_deg: np.ndarray
    pair_rotations_deg: list[float]  # signed dominant rotation component
    pair_rotation_vectors_deg: list[list[float]]
    pair_errors: list[float]
    observed_surface_pct: float
    defect_pct_of_observed: float | None
    defect_pct_of_full_surface: float | None
    grade: str | None
    status: str
    model_type: str
    estimated_radii_px: tuple[float, float, float]
    rotation_coverage_deg: float
    map_longitude_span_deg: float = 0.0
    view_frames: list[int] = field(default_factory=list)
    discarded_view_frames: list[int] = field(default_factory=list)
    selection_diagnostics: list[dict] = field(default_factory=list)


def _binary(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if mask.shape != shape:
        raise ValueError(f"Mask {mask.shape} does not match image {shape}")
    return (mask > 0).astype(np.uint8)


def _largest_component(mask: np.ndarray) -> np.ndarray:
    n, labels, sizes, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n < 2:
        raise MappingError("Foreground mask has no fruit")
    result = (labels == 1 + np.argmax(sizes[1:, cv2.CC_STAT_AREA])).astype(np.uint8)
    if int(result.sum()) < 100:
        raise MappingError("Fruit foreground has fewer than 100 pixels")
    return result


def _grabcut(image: np.ndarray, iterations: int,
             bbox: tuple[int, int, int, int] | None = None) -> np.ndarray:
    h, w = image.shape[:2]
    # GrabCut scales poorly with crop area. Estimate the boundary at a smaller
    # resolution, then restore the binary mask for mapping and defect clipping.
    scale = max(96 / max(h, w), 28 / min(h, w))
    if scale < 1:
        small = cv2.resize(image, (round(w * scale), round(h * scale)),
                           interpolation=cv2.INTER_AREA)
        small_box = tuple(round(value * scale) for value in bbox) if bbox else None
        mask = _grabcut(small, iterations, small_box)
        return cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    margin = max(2, min(h, w) // 20)
    if min(h, w) < 28 or margin * 2 >= min(h, w):
        raise MappingError("Crop is too small for GrabCut")
    labels = np.zeros((h, w), np.uint8)
    bg = np.zeros((1, 65), np.float64)
    fg = np.zeros((1, 65), np.float64)
    if bbox is None:
        rectangle = (margin, margin, w - 2 * margin, h - 2 * margin)
    else:
        x1, y1, x2, y2 = bbox
        x1, y1 = max(1, x1 - 2), max(1, y1 - 2)
        x2, y2 = min(w - 1, x2 + 2), min(h - 1, y2 + 2)
        if x2 - x1 < 5 or y2 - y1 < 5:
            raise MappingError('Detector box is too small for GrabCut')
        rectangle = (x1, y1, x2 - x1, y2 - y1)
    cv2.grabCut(image, labels, rectangle,
                bg, fg, iterations, cv2.GC_INIT_WITH_RECT)
    return _largest_component(np.isin(labels, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8))


def _prepare(views: Sequence[FruitView], s: Settings) -> list[FruitView]:
    if len(views) < 2:
        raise MappingError("At least two views of the same fruit are required")
    result = []
    for v in views:
        if v.image.ndim != 3 or v.image.shape[2] != 3 or v.image.dtype != np.uint8:
            raise ValueError("Fruit images must be uint8 H x W x 3 BGR arrays")
        shape = v.image.shape[:2]
        mask = (_largest_component(_binary(v.object_mask, shape))
                if v.object_mask is not None else
                _grabcut(v.image, s.grabcut_iterations, v.fruit_bbox))
        defects = {name: _binary(m, shape) & mask for name, m in v.defect_masks.items()}
        result.append(FruitView(v.image, mask, defects, v.frame_index, v.fruit_bbox))
    names = set(result[0].defect_masks)
    if any(set(v.defect_masks) != names for v in result[1:]):
        raise MappingError("All views must supply identical defect classes, or none")
    return result


def _ellipse(mask: np.ndarray) -> Ellipse:
    # 2021 paper Section 3.1.1: eigenvalues of the masked-pixel covariance.
    y, x = np.nonzero(mask)
    if len(x) < 100:
        raise MappingError("Too few silhouette pixels")
    xy = np.column_stack((x, y)).astype(np.float64)
    center = xy.mean(axis=0)
    deviation = xy - center
    cov = deviation.T @ deviation / len(xy)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    if eigenvalues[0] <= 0:
        raise MappingError("Degenerate fruit silhouette")
    a, b = 2 * np.sqrt(eigenvalues[1]), 2 * np.sqrt(eigenvalues[0])
    if b < 8:
        raise MappingError("Fruit is too small to fit a spheroid")
    v1, v2 = eigenvectors[:, 1], eigenvectors[:, 0]
    return Ellipse(center, float(a), float(b), v1, v2)


def _validate_capture_mask(mask: np.ndarray, bbox: tuple[int, int, int, int],
                           settings: Settings) -> None:
    """Reject collapsed and visibly concave silhouettes before fitting geometry."""
    x1, y1, x2, y2 = bbox
    fraction = np.count_nonzero(mask) / max(1, (x2-x1)*(y2-y1))
    if fraction < settings.minimum_mask_box_fraction:
        raise MappingError('Fruit mask covers too little of its detection box')
    _ellipse(mask)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour = max(contours, key=cv2.contourArea)
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    solidity = cv2.contourArea(contour) / max(hull_area, 1)
    if solidity < settings.minimum_silhouette_solidity:
        raise MappingError('Fruit silhouette is occluded or too irregular for a spheroid')


def _oblate_poles(ellipses: Sequence[Ellipse], A: float, B: float,
                  s: Settings) -> list[np.ndarray]:
    """2021 section 3.1.3: disambiguate depth from minor-axis variation.

    The fitted silhouettes are measurements of imperfect fruit, not exact
    projections of a rigid ellipsoid. Their poses must not be forced to satisfy
    an exact rigid transition before texture matching has estimated motion.
    """
    if s.pole_pose_method == 'constrained':
        return _constrained_oblate_poles(ellipses, A, B, s)
    if s.pole_pose_method != 'silhouette_trend':
        raise ValueError('pole_pose_method must be silhouette_trend or constrained')
    axis = 0 if s.rotation_axis == 'x' else 1
    other = 1-axis
    minor = np.array([e.minor for e in ellipses])
    # One-sided second-order slopes at endpoints avoid choosing the wrong
    # depth sign when a turning point lies inside the final view interval.
    derivative = np.gradient(minor, edge_order=2 if len(minor) >= 3 else 1)
    span = max(A*A-B*B, 1e-9)
    result = []
    for i, e in enumerate(ellipses):
        projected = np.sqrt(np.clip((A*A-e.minor**2)/span, 0., 1.))
        depth = np.sqrt(np.clip((e.minor**2-B*B)/span, 0., 1.))
        vector = e.v_minor.copy()
        if vector[other] < 0:
            vector *= -1
        xy = vector*projected
        # d(p_z^2)/dt = +2*w*p_y*p_z for x rotation, -2*w*p_x*p_z for y.
        sign = np.sign(derivative[i])*s.rotation_direction*(1 if axis == 0 else -1)
        if sign == 0:
            candidates = [np.r_[xy, depth], np.r_[xy, -depth]]
            pole = (max(candidates, key=lambda p: abs(float(p @ result[-1])))
                    if result else candidates[0])
        else:
            pole = np.r_[xy, sign*depth]
        pole /= np.linalg.norm(pole)
        if result and pole @ result[-1] < 0:
            pole *= -1
        result.append(pole)
    return result


def _constrained_oblate_poles(ellipses: Sequence[Ellipse], A: float, B: float,
                             s: Settings) -> list[np.ndarray]:
    """Resolve the silhouette's front/back ambiguity across ordered views.

    Each ellipse fixes the pole's image-plane projection but not the sign of
    its depth. Choose the sequence consistent with rotation about the known
    roller axis, rather than using the minor-axis size trend (which reverses
    at a turning point and is constant for an axis-aligned pole).
    """
    axis_index = 0 if s.rotation_axis == "x" else 1
    span = max(A*A - B*B, 1e-9)
    candidates = []
    for e in ellipses:
        projected = np.sqrt(np.clip((A*A - e.minor**2) / span, 0.0, 1.0))
        depth = np.sqrt(np.clip((e.minor**2 - B*B) / span, 0.0, 1.0))
        vminor = e.v_minor.copy()
        if vminor[axis_index] < 0:
            vminor *= -1
        xy = vminor * projected
        pair = np.array([[xy[0], xy[1], depth],
                         [xy[0], xy[1], -depth],
                         [-xy[0], -xy[1], depth],
                         [-xy[0], -xy[1], -depth]], dtype=np.float64)
        pair /= np.linalg.norm(pair, axis=1)[:, None]
        candidates.append(pair)

    # A pair of signs is the DP state so changes in angular step can be
    # penalized. Identical poles remain valid: a fruit may turn about its
    # symmetry axis without changing its silhouette.
    if not 0 <= s.pole_pose_tolerance_deg < 45:
        raise ValueError('pole_pose_tolerance_deg must be in [0, 45)')
    # Eigenvector signs are arbitrary. Keep both image-plane signs as well
    # as both depth signs; fixing a sign from a near-zero axis component
    # otherwise creates a false 180-degree pole flip.
    count = 4
    edge = np.full((len(candidates)-1, count, count), np.inf)
    residuals = np.full_like(edge, np.inf)
    # Use the same two-component rotation domain as texture matching. The
    # former phase-only check incorrectly prohibited all transverse rotation.
    main = np.deg2rad(np.arange(0, s.max_pair_angle_deg + .001, s.search_step_deg))
    transverse = np.deg2rad(np.arange(-s.transverse_angle_deg,
                                      s.transverse_angle_deg + .001, s.search_step_deg))
    angles = np.array([(u, v) for u in main for v in transverse])
    vectors = np.zeros((len(angles), 3))
    vectors[:, axis_index] = s.rotation_direction * angles[:, 0]
    vectors[:, 1-axis_index] = angles[:, 1]
    feasible_rotations = np.array([cv2.Rodrigues(vector)[0] for vector in vectors])
    for i in range(len(candidates)-1):
        for previous in range(count):
            for current in range(count):
                before, after = candidates[i][previous], candidates[i+1][current]
                # Phase becomes undefined when the pole lies on the roller
                # axis. Measure the actual 3D pole mismatch instead: tiny
                # silhouette jitter must not become a spurious 360-degree turn.
                predicted = feasible_rotations @ before
                errors = np.arccos(np.clip(predicted @ after, -1, 1))
                best_index = int(np.argmin(errors**2 + 1e-8*np.sum(angles**2, axis=1)))
                best = (float(errors[best_index]), float(angles[best_index, 0]))
                residuals[i, previous, current] = best[0]
                if best[0] <= np.deg2rad(s.pole_pose_tolerance_deg) + 1e-6:
                    edge[i, previous, current] = best[1]
        if not np.isfinite(edge[i]).any():
            mismatch = float(np.rad2deg(np.min(residuals[i])))
            raise MappingError(f'Oblate pose mismatch at pair {i}: {mismatch:.1f} deg; '
                               'check silhouette quality, view spacing and rotation configuration')
    costs = np.full((count, count), np.inf)
    for previous in range(count):
        for current in range(count):
            if np.isfinite(edge[0, previous, current]):
                costs[previous, current] = (residuals[0, previous, current]**2 +
                                            edge[0, previous, current]**2 * .001)
    back = []
    for i in range(1, len(edge)):
        next_costs = np.full((count, count), np.inf)
        choice = np.full((count, count), -1, dtype=int)
        for previous in range(count):
            for current in range(count):
                angle = edge[i, previous, current]
                if not np.isfinite(angle):
                    continue
                for older in range(count):
                    earlier = edge[i-1, older, previous]
                    if not np.isfinite(earlier):
                        continue
                    cost = (costs[older, previous] + residuals[i, previous, current]**2 +
                            .1*(angle-earlier)**2 +
                            .001*angle**2)
                    if cost < next_costs[previous, current]:
                        next_costs[previous, current] = cost
                        choice[previous, current] = older
        costs = next_costs
        back.append(choice)
        if not np.isfinite(costs).any():
            raise MappingError(f'No consistent oblate pose sequence through pair {i}; '
                               'check silhouette quality, view spacing and rotation configuration')
    if not np.isfinite(costs).any():
        raise MappingError("Oblate pole poses do not follow the configured rotation")
    previous, current = np.unravel_index(np.argmin(costs), costs.shape)
    signs = [0] * len(candidates)
    signs[-2:] = [int(previous), int(current)]
    for i in range(len(back)-1, -1, -1):
        signs[i] = int(back[i][signs[i+1], signs[i+2]])
    return [candidates[i][signs[i]] for i in range(len(candidates))]


def fit_spheroid(views: Sequence[FruitView], s: Settings) -> Spheroid:
    """Fit shared radii and per-view pose from all silhouettes (2021 Sec. 3.1)."""
    if len(views) < 2:
        raise MappingError("At least two views are required to fit a spheroid")
    if s.spheroid_type not in ("oblate", "sphere", "auto"):
        raise ValueError("spheroid_type must be 'oblate', 'sphere', or 'auto'")
    if not 0 <= s.spherical_tolerance < 1:
        raise ValueError("spherical_tolerance must be in [0, 1)")
    if s.rotation_axis not in ("x", "y") or s.rotation_direction not in (-1, 1):
        raise ValueError("Set rotation_axis x/y and direction +1/-1 from the conveyor")
    ellipses = [_ellipse(v.object_mask) for v in views]
    major = np.array([e.major for e in ellipses])
    minor = np.array([e.minor for e in ellipses])
    near_sphere = (float(major.mean()) - float(minor.min())) / float(major.mean()) < s.spherical_tolerance
    if s.spheroid_type == "sphere" or (s.spheroid_type == "auto" and near_sphere):
        radius = float(np.mean((major + minor) / 2))  # paper Equation (4)
        matrix = np.eye(3, dtype=np.float64) / radius**2
        basis = (np.eye(3) if s.rotation_axis == 'y' else
                 np.array([[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]]))
        return Spheroid(radius, radius, ellipses,
                        [matrix.copy() for _ in views], basis, 0,
                        [basis[:, 1].copy() for _ in views])
    A, B = float(major.mean()), float(minor.min())  # paper Equation (5)
    if B > A + 1 or B <= 0:
        raise MappingError("The projected ellipses do not support an oblate model")
    if (A - B) / A < 0.035:
        raise MappingError("Oblate pole pose is ambiguous; choose spheroid_type='sphere'")
    reference = int(np.argmin(minor))
    poles = _oblate_poles(ellipses, A, B, s)
    matrices = []
    for pole in poles:
        # M = P^T diag(1/B²,1/A²,1/A²) P; rotation about pole is immaterial.
        M = np.eye(3) / A**2 + (1 / B**2 - 1 / A**2) * np.outer(pole, pole)
        matrices.append(M)
    pole = poles[reference]
    e = ellipses[reference]
    x_axis = np.r_[e.v_major, 0.0]
    y_axis = pole
    x_axis -= x_axis.dot(y_axis) * y_axis
    x_axis /= np.linalg.norm(x_axis)
    z_axis = np.cross(x_axis, y_axis)
    if z_axis[2] < 0:
        x_axis *= -1
        z_axis *= -1
    return Spheroid(A, B, ellipses, matrices,
                    np.column_stack((x_axis, y_axis, z_axis)), reference, poles)


def _height(M: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Larger quadratic root of [x,y,z]^T M [x,y,z] = 1 (2021 App. A)."""
    b = 2 * (M[0, 2] * x + M[1, 2] * y)
    c = M[0, 0] * x*x + 2 * M[0, 1] * x*y + M[1, 1] * y*y - 1
    disc = b*b - 4 * M[2, 2] * c
    z = (-b + np.sqrt(np.maximum(disc, 0))) / (2 * M[2, 2])
    return np.where(disc >= 0, z, np.nan)


def _preprocess(v: FruitView, down: int, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    # 2021 Section 3.3.1: green channel, 4x area shrink, signed high-pass.
    green = v.image[:, :, 1].astype(np.float32) / 255.0
    h, w = green.shape
    size = (max(1, w // down), max(1, h // down))
    small = cv2.resize(green, size, interpolation=cv2.INTER_AREA)
    mask = cv2.resize(v.object_mask, size, interpolation=cv2.INTER_NEAREST)
    high = small - cv2.GaussianBlur(small, (0, 0), sigma)
    return high.astype(np.float32), mask


def _relevant(v: FruitView, model: Spheroid, index: int, s: Settings
              ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high, mask = _preprocess(v, s.image_downsample, s.highpass_sigma)
    h, w = high.shape
    yy, xx = np.mgrid[:h, :w]
    e = model.ellipses[index]
    # Pixel centers of the downsampled image expressed at original resolution.
    sx = (xx + .5) * (v.image.shape[1] / w) - .5
    sy = (yy + .5) * (v.image.shape[0] / h) - .5
    delta = np.stack((sx - e.center[0], sy - e.center[1]), axis=-1)
    along_major = delta @ e.v_major
    along_minor = delta @ e.v_minor
    # The ellipse interior excludes unstable silhouette and occluding edge.
    interior = ((along_major / e.major)**2 + (along_minor / e.minor)**2 < .66**2) & (mask > 0)
    if s.exclude_specular_texture:
        small_color = cv2.resize(v.image, (w,h), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small_color, cv2.COLOR_BGR2HSV)
        glare = ((hsv[:,:,1] < 102) & (hsv[:,:,2] > 90)).astype(np.uint8)
        glare = cv2.dilate(glare, np.ones((3,3),np.uint8))
        interior &= glare == 0
    if int(interior.sum()) < s.min_pair_points:
        raise MappingError("Too little central fruit area to select texture")
    absolute = np.abs(high[interior])
    if s.texture_metric == 'absolute_std' and float(np.std(absolute)) < s.min_texture:
        raise MappingError("Fruit has insufficient measurable surface texture")
    threshold = np.percentile(absolute, s.point_percentile)
    selected = interior & (np.abs(high) >= threshold)
    rows, cols = np.nonzero(selected)
    if len(rows) < s.min_pair_points:
        central_rows, central_cols = np.nonzero(interior)
        strongest = np.argsort(np.abs(high[central_rows, central_cols]))[-s.min_pair_points:]
        rows, cols = central_rows[strongest], central_cols[strongest]
    if len(rows) > 160:
        order = np.argsort(np.abs(high[rows, cols]))[-160:]
        rows, cols = rows[order], cols[order]
    if s.texture_metric not in ('selected_rms', 'absolute_std'):
        raise ValueError('texture_metric must be selected_rms or absolute_std')
    if (s.texture_metric == 'selected_rms' and
            float(np.sqrt(np.mean(high[rows, cols]**2))) < s.min_texture):
        raise MappingError('Fruit has insufficient measurable surface texture')
    src_x, src_y = delta[rows, cols, 0], delta[rows, cols, 1]
    z = _height(model.matrices[index], src_x, src_y)
    # The larger quadratic root is the visible surface, including portions
    # with negative z when an oblate spheroid is tilted.
    good = np.isfinite(z)
    if int(good.sum()) < s.min_pair_points:
        raise MappingError("Insufficient valid lifted 3D texture points")
    points = np.column_stack((src_x[good], src_y[good], z[good]))
    return points, high[rows[good], cols[good]], np.array([h, w])


def _cost(vector: np.ndarray, points: np.ndarray, source_values: np.ndarray,
          target_high: np.ndarray, target_mask: np.ndarray,
          target_view: FruitView, center: np.ndarray, min_points: int,
          target_matrix: np.ndarray, normalize: bool = True
          ) -> float:
    R, _ = cv2.Rodrigues(vector.astype(np.float64).reshape(3, 1))
    rotated = points @ R.T
    h, w = target_high.shape
    px = (rotated[:, 0] + center[0] + .5) * w / target_view.image.shape[1] - .5
    py = (rotated[:, 1] + center[1] + .5) * h / target_view.image.shape[0] - .5
    ix, iy = np.rint(px).astype(int), np.rint(py).astype(int)
    facing_camera = rotated @ target_matrix[:, 2] > 0
    valid = (facing_camera & (ix >= 0) & (iy >= 0) & (ix < w) & (iy < h))
    valid &= target_mask[np.clip(iy, 0, h - 1), np.clip(ix, 0, w - 1)] > 0
    if int(valid.sum()) < min_points:
        return float('inf')
    values = cv2.remap(target_high, px[valid].astype(np.float32).reshape(1, -1),
                       py[valid].astype(np.float32).reshape(1, -1),
                       cv2.INTER_LINEAR)[0]
    difference = float(np.mean(np.abs(source_values[valid] - values)))
    if not normalize:
        return difference  # Paper Eq. 17, used to select the rotation.
    # Report a normalized residual for the existing confidence gate. It must
    # not alter the minimizer of the paper's unnormalized objective.
    scale = max(float(np.mean(np.abs(source_values[valid])) +
                      np.mean(np.abs(values))), .005)
    return difference / scale


def estimate_rotation(source: FruitView, target: FruitView, model: Spheroid,
                      index: int, s: Settings) -> tuple[np.ndarray, float]:
    """Grid search over two 3D rotation-vector components (2021 Sec. 3.2)."""
    points, values, _ = _relevant(source, model, index, s)
    if s.matching_cost not in ('mad', 'normalized'):
        raise ValueError('matching_cost must be mad or normalized')
    target_high, target_mask = _preprocess(target, s.image_downsample, s.highpass_sigma)
    reverse = None
    if s.bidirectional_matching:
        reverse_points, reverse_values, _ = _relevant(target, model, index+1, s)
        source_high, source_mask = _preprocess(source, s.image_downsample, s.highpass_sigma)
        reverse = (reverse_points, reverse_values, source_high, source_mask)
    step = s.search_step_deg
    main = np.arange(0, s.max_pair_angle_deg + .001, step)
    side = np.arange(-s.transverse_angle_deg, s.transverse_angle_deg + .001, step)
    axis = 0 if s.rotation_axis == 'x' else 1
    other = 1 - axis
    best = (float('inf'), None)
    def vector_cost(vec: np.ndarray, normalize: bool) -> float:
        forward = _cost(vec, points, values, target_high, target_mask,
                        target, model.ellipses[index+1].center, s.min_pair_points,
                        model.matrices[index+1], normalize=normalize)
        if reverse is None:
            return forward
        backward = _cost(-vec, *reverse, source, model.ellipses[index].center,
                         s.min_pair_points, model.matrices[index], normalize=normalize)
        return (forward+backward)/2

    def score(u: float, v: float) -> float:
        vec = np.zeros(3, np.float64)
        vec[axis] = s.rotation_direction * np.deg2rad(u)
        vec[other] = np.deg2rad(v)
        return vector_cost(vec, normalize=s.matching_cost == 'normalized')
    for u in main:
        for v in side:
            error = score(float(u), float(v))
            if error < best[0]:
                best = (error, (float(u), float(v)))
    if best[1] is None:
        raise MappingError(f'No valid projected correspondences for pair {index}')
    best_error, (u0, v0) = best
    # 2021 Sec. 3.2: half-step 5x5 grid and quadratic subpixel refinement.
    step2 = step / 2
    grid_u, grid_v = u0, v0
    for du in range(-2, 3):
        u = grid_u + du * step2
        if not 0 <= u <= s.max_pair_angle_deg:
            continue
        for dv in range(-2, 3):
            v = grid_v + dv * step2
            if abs(v) > s.transverse_angle_deg:
                continue
            error = score(u, v)
            if error < best_error:
                best_error, u0, v0 = error, u, v
    e00 = score(u0, v0)
    ep, em, fp, fm = (score(u0 + step2, v0), score(u0 - step2, v0),
                      score(u0, v0 + step2), score(u0, v0 - step2))
    epp, epm, emp, emm = (score(u0 + step2, v0 + step2),
                          score(u0 + step2, v0 - step2),
                          score(u0 - step2, v0 + step2),
                          score(u0 - step2, v0 - step2))
    if np.all(np.isfinite([e00, ep, em, fp, fm, epp, epm, emp, emm])):
        grad = np.array([(ep - em) / (2*step2), (fp - fm) / (2*step2)])
        hess = np.array([[(ep - 2*e00 + em) / step2**2,
                          (epp - epm - emp + emm) / (4*step2**2)],
                         [(epp - epm - emp + emm) / (4*step2**2),
                          (fp - 2*e00 + fm) / step2**2]])
        if np.min(np.linalg.eigvalsh(hess)) > 0:
            offset = -np.linalg.solve(hess, grad)
            if (np.max(np.abs(offset)) <= step2 and
                    0 <= u0 + offset[0] <= s.max_pair_angle_deg and
                    abs(v0 + offset[1]) <= s.transverse_angle_deg):
                refined = score(u0 + offset[0], v0 + offset[1])
                if refined < best_error:
                    best_error, u0, v0 = refined, u0 + offset[0], v0 + offset[1]
    vec = np.zeros(3, np.float64)
    vec[axis] = s.rotation_direction * np.deg2rad(u0)
    vec[other] = np.deg2rad(v0)
    residual = vector_cost(vec, normalize=True)
    if (not np.isfinite(residual) or residual > s.max_pair_error or
            u0 < s.min_pair_angle_deg or u0 >= s.max_pair_angle_deg):
        raise MappingError(f'Unreliable pair {index}: rotation {u0:.1f} deg, error {residual:.3f}')
    return cv2.Rodrigues(vec)[0], float(residual)


def _sample_view(view: FruitView, points: np.ndarray,
                 names: Sequence[str], matrix: np.ndarray,
                 center: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    h, w = view.image.shape[:2]
    x = points[:, 0].astype(np.float32).reshape(-1, 1)
    y = points[:, 1].astype(np.float32).reshape(-1, 1)
    ix, iy = np.rint(x).astype(int), np.rint(y).astype(int)
    centered = points.copy()
    centered[:, :2] -= center
    valid = (centered @ matrix[:, 2] > 0).reshape(-1, 1) & (ix >= 0) & (iy >= 0) & (ix < w) & (iy < h)
    valid &= view.object_mask[np.clip(iy, 0, h-1), np.clip(ix, 0, w-1)] > 0
    color = cv2.remap(view.image, x, y, cv2.INTER_LINEAR)
    masks = {name: (cv2.remap(view.defect_masks[name], x, y,
                             cv2.INTER_NEAREST) > 0) & valid for name in names}
    return color, valid[:, 0], {name: mask[:, 0] for name, mask in masks.items()}


def _grade(defect_pct: float | None, coverage: float,
           s: Settings) -> tuple[str | None, str]:
    if coverage < s.minimum_surface_coverage:
        return None, 'insufficient_surface_coverage'
    if defect_pct is None:
        return None, 'missing_defect_masks'
    t1, t2 = s.class_1_max_defect_pct, s.class_2_max_defect_pct
    if t1 is None or t2 is None:
        return None, 'grade_thresholds_not_configured'
    if not (0 <= t1 <= t2 <= 100):
        raise ValueError('Grade thresholds must satisfy 0 <= T1 <= T2 <= 100')
    return ('Class 1' if defect_pct < t1 else
            'Class 2' if defect_pct <= t2 else 'Class 3'), 'graded'


def _map_frame(model: Spheroid, settings: Settings) -> tuple[np.ndarray, np.ndarray]:
    """Choose fruit y near the roller axis (2022 section 2.1).

    The short symmetry axis of an oblate fruit need not be its rolling axis.
    Reordering frame axes requires reordering the corresponding radii too.
    """
    basis = model.reference_axes.copy()
    radii = np.array([model.A, model.B, model.A], dtype=float)
    axis = 0 if settings.rotation_axis == 'x' else 1
    if abs(basis[axis, 0]) > abs(basis[axis, 1]):
        basis = np.column_stack((-basis[:, 1], basis[:, 0], basis[:, 2]))
        radii = radii[[1, 0, 2]]
    return basis, radii


def _subset_spheroid(model: Spheroid, indices: Sequence[int]) -> Spheroid:
    """Keep poses measured from the full sequence when selecting useful views."""
    ellipses = [model.ellipses[i] for i in indices]
    poles = [model.pole_axes[i] for i in indices]
    reference = int(np.argmin([e.minor for e in ellipses]))
    basis = model.reference_axes.copy()
    if model.A != model.B:
        y_axis = poles[reference]
        x_axis = np.r_[ellipses[reference].v_major, 0.]
        x_axis -= x_axis.dot(y_axis)*y_axis
        x_axis /= np.linalg.norm(x_axis)
        z_axis = np.cross(x_axis, y_axis)
        if z_axis[2] < 0:
            x_axis *= -1
            z_axis *= -1
        basis = np.column_stack((x_axis, y_axis, z_axis))
    return Spheroid(model.A, model.B, ellipses, [model.matrices[i] for i in indices],
                    basis, reference, poles)


def _select_rotating_views(views: Sequence[FruitView], model: Spheroid, s: Settings):
    """Select measured transitions; never interpolate an unverified rotation.

    A failed or stationary target can be skipped only if a later target matches
    the last retained view. Long gaps start a separate segment. Return the
    segment with the greatest measured rotation; grading still needs coverage.
    This capture adaptation is separate from the paper's pairwise estimator.
    """
    if not (0 < s.minimum_view_rotation_deg < s.max_pair_angle_deg and
            s.maximum_view_index_gap >= 1):
        raise ValueError('Invalid rotating-view selection settings')
    pair_settings = replace(s, min_pair_angle_deg=0.)
    axis = 0 if s.rotation_axis == 'x' else 1
    segments, diagnostics = [], []
    indices, rotations, errors = [0], [], []
    for target in range(1, len(views)):
        if target-indices[-1] > s.maximum_view_index_gap:
            if rotations:
                segments.append((indices, rotations, errors))
            indices, rotations, errors = [target-1], [], []
        anchor = indices[-1]
        pair_model = _subset_spheroid(model, [anchor, target])
        record = {'source_frame': views[anchor].frame_index,
                  'target_frame': views[target].frame_index}
        try:
            R, error = estimate_rotation(views[anchor], views[target], pair_model, 0, pair_settings)
            angle = abs(float(np.rad2deg(cv2.Rodrigues(R)[0][axis, 0])))
            record.update(rotation_deg=angle, error=error)
            if angle < s.minimum_view_rotation_deg:
                record.update(status='skipped', reason='insufficient_angular_change')
            else:
                indices.append(target); rotations.append(R); errors.append(error)
                record['status'] = 'accepted'
        except MappingError as error:
            record.update(status='skipped', reason=str(error))
        diagnostics.append(record)
    if rotations:
        segments.append((indices, rotations, errors))
    if not segments:
        raise MappingError('No reliable rotating sequence; inspect motion, reflections and fruit masks')
    indices, rotations, errors = max(segments, key=lambda segment: sum(
        abs(float(cv2.Rodrigues(R)[0][axis, 0])) for R in segment[1]))
    return ([views[i] for i in indices], _subset_spheroid(model, indices),
            rotations, errors, diagnostics)


def build_surface_map(views: Sequence[FruitView],
                      settings: Settings | None = None) -> MapResult:
    """Estimate geometry/rotations, unwrap views, and grade observed area."""
    s = settings or Settings()
    if not (0 < s.max_latitude_deg < 90 and 0 <= s.minimum_surface_coverage <= 1 and
            0 <= s.minimum_rotation_coverage_deg <= 360 and
            (s.maximum_pair_gap_deg is None or 0 < s.maximum_pair_gap_deg <= 180)):
        raise ValueError('Invalid latitude or minimum coverage')
    prepared = _prepare(views, s)
    model = fit_spheroid(prepared, s)
    captured_frames = [v.frame_index for v in prepared]
    rotations, errors, diagnostics = [], [], []
    if s.select_rotating_views:
        prepared, model, rotations, errors, diagnostics = _select_rotating_views(prepared, model, s)
    else:
        for i in range(len(prepared) - 1):
            R, error = estimate_rotation(prepared[i], prepared[i+1], model, i, s)
            rotations.append(R)
            errors.append(error)
    component = 0 if s.rotation_axis == 'x' else 1
    magnitudes = np.array([abs(np.rad2deg(cv2.Rodrigues(R)[0][component,0]))
                           for R in rotations])
    typical = float(np.median(magnitudes))
    if s.enforce_uniform_pair_rotation and np.any(np.abs(magnitudes - typical) > max(12.0, .45*typical)):
        raise MappingError('A pair rotation disagrees sharply with the other views; inspect tracking, pose and texture')
    # Propagate the same fruit-fixed basis through all views (2022 Eq. 1-2).
    poses = [np.eye(3)]
    for R in rotations:
        poses.append(R @ poses[-1])
    map_basis, radii = _map_frame(model, s)
    rx, ry, rz = radii
    axes_ref = poses[model.reference_index].T @ map_basis
    axes = [pose @ axes_ref for pose in poses]
    centers = []
    for Q in axes:
        ray = Q.T @ np.array([0.0, 0.0, 1.0])
        centers.append(np.arctan2(ray[2] / rz, ray[0] / rx))
    unwrapped = np.unwrap(centers)
    differences = np.diff(unwrapped)
    direction = float(np.sign(np.median(differences)))
    if direction == 0:
        raise MappingError('No consistent angular progress')
    progress = direction * (unwrapped - unwrapped[0])
    if np.any(np.diff(progress) < np.deg2rad(.25)) or np.any(np.diff(progress) > np.deg2rad(s.max_pair_angle_deg + 12)):
        raise MappingError('Fruit-fixed longitude centers are not consistently ordered')
    step = (np.deg2rad(s.map_angle_step_deg) if s.map_angle_step_deg else 1 / model.A)
    if not 0 < step < np.deg2rad(10):
        raise ValueError('Map angular step must be between 0 and 10 degrees')
    width = int(np.ceil(2*np.pi/step))
    height = int(np.ceil(np.pi/step))
    latitude = (np.arange(height)+.5) * np.pi/height - np.pi/2
    longitude = unwrapped[0] + direction * ((np.arange(width)+.5)*2*np.pi/width - np.pi/4)
    qgrid = (np.arange(width)+.5)*2*np.pi/width - np.pi/4
    names = sorted(prepared[0].defect_masks)
    bgr = np.zeros((height,width,3), np.uint8)
    observed = np.zeros((height,width), bool)
    defect_maps = {name: np.zeros((height,width), np.uint8) for name in names}
    visible_lat = np.abs(latitude) < np.deg2rad(s.max_latitude_deg)
    for col, q in enumerate(qgrid):
        if q < -np.pi/4 or q > progress[-1] + np.pi/4:
            continue
        if q < 0:
            indices, weights = [0], [1.0]
        elif q > progress[-1]:
            indices, weights = [len(prepared)-1], [1.0]
        else:
            k = min(max(int(np.searchsorted(progress, q, side='right'))-1, 0), len(prepared)-2)
            fraction = (q-progress[k])/(progress[k+1]-progress[k])
            indices, weights = [k,k+1], [1-fraction, fraction]
        lam = latitude
        phi = longitude[col]
        fruit = np.column_stack((rx*np.cos(lam)*np.cos(phi),
                                 ry*np.sin(lam),
                                 rz*np.cos(lam)*np.sin(phi)))
        accum = np.zeros((height,3), np.float32)
        weight_sum = np.zeros(height, np.float32)
        for index, weight in zip(indices, weights):
            projected = fruit @ axes[index].T
            projected[:, 0:2] += model.ellipses[index].center
            matrix = axes[index] @ np.diag(1/radii**2) @ axes[index].T
            color, valid, defects = _sample_view(prepared[index], projected, names,
                                                matrix, model.ellipses[index].center)
            valid &= visible_lat
            factor = np.where(valid, weight, 0).astype(np.float32)
            accum += color[:,0,:] * factor[:,None]
            weight_sum += factor
            for name in names:
                defect_maps[name][:,col] |= (defects[name] & valid).astype(np.uint8)
        occupied = weight_sum > 1e-7
        bgr[occupied,col] = np.clip(accum[occupied]/weight_sum[occupied,None],0,255).astype(np.uint8)
        observed[:,col] = occupied
    # General ellipsoid Jacobian: the short radius may lie on map x or y.
    cosine = np.cos(latitude)[:, None]
    sine = np.sin(latitude)[:, None]
    jacobian = cosine * np.sqrt(
        (ry*rz*cosine*np.cos(longitude)[None, :])**2 +
        (rx*rz*sine)**2 + (rx*ry*cosine*np.sin(longitude)[None, :])**2)
    total = float(jacobian.sum())
    observed_area = float((observed*jacobian).sum())
    union = np.zeros_like(observed)
    for mask in defect_maps.values():
        union |= mask > 0
    defect_area = float((union*observed*jacobian).sum())
    coverage = 100*observed_area/total if total else 0
    has_defect_evidence = bool(names) or s.defect_observations_complete
    defect_visible = 100*defect_area/observed_area if has_defect_evidence and observed_area else None
    defect_full = 100*defect_area/total if has_defect_evidence and total else None
    grade, status = _grade(defect_visible, coverage/100, s)
    rotation_coverage = float(magnitudes.sum())
    if (rotation_coverage < s.minimum_rotation_coverage_deg or
            (s.maximum_pair_gap_deg is not None and
             float(magnitudes.max()) > s.maximum_pair_gap_deg)):
        grade, status = None, 'insufficient_rotation_coverage'
    vectors = [cv2.Rodrigues(R)[0].ravel() for R in rotations]
    return MapResult(bgr, observed.astype(np.uint8), defect_maps,
                     np.rad2deg(longitude), np.rad2deg(latitude),
                     [float(np.rad2deg(v[component])) for v in vectors],
                     [np.rad2deg(v).tolist() for v in vectors],
                     errors, coverage, defect_visible, defect_full, grade, status,
                     "sphere" if model.A == model.B else "oblate",
                     (model.A, model.B, model.A),
                     rotation_coverage, float(np.rad2deg(progress[-1])),
                     [v.frame_index for v in prepared],
                     [frame for frame in captured_frames if frame not in {v.frame_index for v in prepared}],
                     diagnostics)


def _as_numpy(value: object) -> np.ndarray:
    """Accept a CPU/GPU tensor or array without requiring torch at import time."""
    if hasattr(value, 'detach'):
        value = value.detach()
    if hasattr(value, 'cpu'):
        value = value.cpu()
    if hasattr(value, 'numpy'):
        value = value.numpy()
    return np.asarray(value)


def _model_names(model: object) -> dict[int, str]:
    names = getattr(model, 'names', None)
    if isinstance(names, dict):
        result = {int(key): str(name) for key, name in names.items()}
    elif isinstance(names, (tuple, list)):
        result = {index: str(name) for index, name in enumerate(names)}
    else:
        raise ValueError('A model must expose class names in .names')
    if not result or len(set(result.values())) != len(result):
        raise ValueError('Model class names must be nonempty and unique')
    return result


class NaartjiePipeline:
    """Optional model adapter around the paper-based build_surface_map function.

    `process_frame` runs D-FINE detection with TrackTrack IDs. If another
    tracker already owns fruit IDs, call `add_tracked_detection`
    instead and keep its existing IDs. Call `finish_track` only after the
    fruit leaves the capture zone, not after an isolated missed detection.
    """

    def __init__(self, segmentation_model: object, detector_model: object | None = None,
                 settings: Settings | None = None, detection_conf: float = .25,
                 segmentation_conf: float = .25, capture_stride_frames: int = 1,
                 crop_padding: float = .12, fruit_class_name: str | None = None,
                 max_views_per_track: int = 120):
        self.detector = detector_model
        self.segmenter = segmentation_model
        self.settings = settings or Settings()
        self.defect_names = _model_names(self.segmenter)
        self.fruit_names = _model_names(self.detector) if self.detector is not None else {}
        if self.detector is not None and fruit_class_name is None:
            if len(self.fruit_names) != 1:
                raise ValueError('Set fruit_class_name for a multi-class detector')
            fruit_class_name = next(iter(self.fruit_names.values()))
        self.fruit_class_name = fruit_class_name.casefold() if fruit_class_name else None
        if self.detector is not None and self.fruit_class_name not in {
            name.casefold() for name in self.fruit_names.values()
        }:
            raise ValueError(f'Detector has no {fruit_class_name!r} class')
        if (not 0 <= detection_conf <= 1 or not 0 <= segmentation_conf <= 1 or
                capture_stride_frames < 1 or max_views_per_track < 2 or
                not 0 < crop_padding < 1):
            raise ValueError('Invalid model confidence, capture stride or crop padding')
        self.detection_conf = detection_conf
        self.segmentation_conf = segmentation_conf
        self.capture_stride_frames = capture_stride_frames
        self.crop_padding = crop_padding
        self.max_views_per_track = max_views_per_track
        self.views_by_id: dict[int, list[FruitView]] = {}
        self.last_capture_frame: dict[int, int] = {}
        self.last_seen_frame: dict[int, int] = {}
        self.rejected_views_by_id: dict[int, dict[str, int]] = {}

    def _segment_defects(self, crop: np.ndarray,
                         fruit_mask: np.ndarray) -> dict[str, np.ndarray]:
        """Run the defect instance-segmentation model on a background-free crop."""
        masked_crop = cv2.bitwise_and(crop, crop, mask=fruit_mask)
        result = self.segmenter.predict(masked_crop, conf=self.segmentation_conf,
                                        retina_masks=True, verbose=False)[0]
        class_masks = {name: np.zeros(fruit_mask.shape, np.uint8)
                       for name in self.defect_names.values()}
        if result.masks is None:
            return class_masks
        if result.boxes is None:
            raise MappingError('Segmentation returned masks without class boxes')
        masks = _as_numpy(result.masks.data)
        classes = _as_numpy(result.boxes.cls).astype(int).ravel()
        if len(masks) != len(classes):
            raise MappingError('Defect mask and class counts do not match')
        for category, raw_mask in zip(classes, masks):
            if int(category) not in self.defect_names:
                raise MappingError(f'Unknown defect model class index {category}')
            mask = (raw_mask > .5).astype(np.uint8)
            if mask.shape != fruit_mask.shape:
                mask = cv2.resize(mask, (fruit_mask.shape[1], fruit_mask.shape[0]),
                                  interpolation=cv2.INTER_NEAREST)
            name = self.defect_names[int(category)]
            class_masks[name] |= mask & fruit_mask
        return class_masks

    def add_tracked_detection(self, frame: np.ndarray, track_id: int,
                              bbox_xyxy: Sequence[float], frame_index: int) -> bool:
        """Detector/TrackTrack output -> crop -> GrabCut -> defect masks -> FruitView.

        Returns False if the configured capture stride skips this frame.
        `bbox_xyxy` contains full-frame coordinates and `track_id` comes from
        an external tracker if one is used.
        """
        if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            raise ValueError('frame must be uint8 H x W x 3 BGR')
        track_id, frame_index = int(track_id), int(frame_index)
        last = self.last_capture_frame.get(track_id)
        if last is not None:
            if frame_index <= last:
                raise ValueError('Captured frame indices for a track must increase')
            if frame_index - last < self.capture_stride_frames:
                return False
        if len(self.views_by_id.get(track_id, [])) >= self.max_views_per_track:
            return False
        x1, y1, x2, y2 = map(float, bbox_xyxy)
        height, width = frame.shape[:2]
        if not (x2 > x1 and y2 > y1):
            raise ValueError('Detector bounding box has no positive area')
        if x1 <= 2 or y1 <= 2 or x2 >= width-2 or y2 >= height-2:
            raise MappingError('Fruit is cut off by the video frame')
        pad_x, pad_y = (x2-x1)*self.crop_padding, (y2-y1)*self.crop_padding
        left, top = max(0, int(np.floor(x1-pad_x))), max(0, int(np.floor(y1-pad_y)))
        right, bottom = min(width, int(np.ceil(x2+pad_x))), min(height, int(np.ceil(y2+pad_y)))
        crop = frame[top:bottom, left:right].copy()
        if crop.size == 0:
            raise MappingError('Fruit crop lies outside the image')
        local_box = (max(0, int(np.floor(x1))-left), max(0, int(np.floor(y1))-top),
                     min(right-left, int(np.ceil(x2))-left),
                     min(bottom-top, int(np.ceil(y2))-top))
        fruit_mask = _grabcut(crop, self.settings.grabcut_iterations, local_box)
        _validate_capture_mask(fruit_mask, local_box, self.settings)
        defects = self._segment_defects(crop, fruit_mask)
        current = self.views_by_id.setdefault(track_id, [])
        current.append(FruitView(crop, fruit_mask, defects, frame_index, local_box))
        self.last_capture_frame[track_id] = frame_index
        return True

    def process_frame(self, frame: np.ndarray, frame_index: int,
                      capture_views: bool = True) -> list[int]:
        """D-FINE fruit detection + TrackTrack on consecutive video frames.

        Use one pipeline instance per video stream. This method does not
        finalize tracks automatically: an ID can disappear for one frame.
        """
        if self.detector is None:
            raise ValueError('No detector supplied; use add_tracked_detection')
        result = self.detector.track(frame, persist=True, tracker='tracktrack.yaml',
                                     conf=self.detection_conf, verbose=False)[0]
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return []
        xyxy = _as_numpy(boxes.xyxy)
        classes = _as_numpy(boxes.cls).astype(int).ravel()
        track_ids = _as_numpy(boxes.id).astype(int).ravel()
        if len(xyxy) != len(classes) or len(xyxy) != len(track_ids):
            raise MappingError('Detector boxes and TrackTrack IDs are misaligned')
        captured = []
        for bounds, category, track_id in zip(xyxy, classes, track_ids):
            if self.fruit_names.get(int(category), '').casefold() != self.fruit_class_name:
                continue
            self.last_seen_frame[int(track_id)] = frame_index
            if not capture_views:
                continue
            try:
                if self.add_tracked_detection(frame, int(track_id), bounds, frame_index):
                    captured.append(int(track_id))
            except MappingError as error:
                # A single unusable crop should not discard earlier views.
                counts = self.rejected_views_by_id.setdefault(int(track_id), {})
                counts[str(error)] = counts.get(str(error), 0) + 1
                continue
        return captured

    def drop_track(self, track_id: int) -> None:
        """Release a finished or unusable track."""
        self.views_by_id.pop(int(track_id), None)
        self.last_capture_frame.pop(int(track_id), None)
        self.last_seen_frame.pop(int(track_id), None)
        self.rejected_views_by_id.pop(int(track_id), None)

    def finish_track(self, track_id: int) -> MapResult:
        """Map and grade one completed ID; remove its views only on success."""
        track_id = int(track_id)
        if track_id not in self.views_by_id:
            raise KeyError(f'No captured views for track {track_id}')
        result = build_surface_map(self.views_by_id[track_id], self.settings)
        self.drop_track(track_id)
        return result


def _read_manifest(path: Path) -> tuple[list[FruitView], Settings]:
    data = json.loads(path.read_text(encoding='utf-8'))
    base = path.parent
    s = Settings(**data.get('settings', {}))
    views = []
    for item in data['views']:
        def load(name: str, mode: int) -> np.ndarray:
            image = cv2.imread(str(base/name), mode)
            if image is None:
                raise FileNotFoundError(base/name)
            return image
        image = load(item['image'], cv2.IMREAD_COLOR)
        mask = load(item['object_mask'],cv2.IMREAD_GRAYSCALE) if item.get('object_mask') else None
        defects = {name: load(filename, cv2.IMREAD_GRAYSCALE)
                   for name, filename in item.get('defect_masks',{}).items()}
        views.append(FruitView(image, mask, defects, item.get('frame_index',0)))
    return views, s


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    views, settings = _read_manifest(args.manifest)
    result = build_surface_map(views, settings)
    args.out.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(args.out/'surface_map.png'),result.bgr_map)
    cv2.imwrite(str(args.out/'observed.png'),result.observed_mask*255)
    for name, mask in result.defect_maps.items():
        safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)
        cv2.imwrite(str(args.out/f'defect_{safe}.png'),mask*255)
    report = dict(status=result.status, grade=result.grade,
                  model_type=result.model_type,
                  estimated_radii_px=result.estimated_radii_px,
                  rotation_coverage_deg=result.rotation_coverage_deg,
                  pair_rotations_deg=result.pair_rotations_deg,
                  pair_rotation_vectors_deg=result.pair_rotation_vectors_deg,
                  pair_errors=result.pair_errors,
                  observed_surface_pct=result.observed_surface_pct,
                  defect_pct_of_observed=result.defect_pct_of_observed,
                  defect_pct_of_full_surface=result.defect_pct_of_full_surface,
                  defect_classes=list(result.defect_maps))
    (args.out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
