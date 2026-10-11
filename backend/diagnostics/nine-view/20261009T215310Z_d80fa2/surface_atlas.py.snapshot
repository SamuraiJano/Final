"""Vectorised strip fusion shared by recorded and incremental inspection.

Only measured neighboring views supply samples. Endpoints remain temporary
layers until the next measured view arrives, preventing stale endpoint defects
from being permanently added to the union. Revisits share physical cells.
"""
import cv2
import numpy as np
import algorithm as a


class SurfaceAtlas:
    def __init__(self, model, settings, first_longitude, direction, radii):
        self.model, self.settings = model, settings
        self.radii = np.asarray(radii, dtype=float)
        self.direction = float(direction)
        if self.direction not in (-1., 1.):
            raise a.MappingError('No consistent angular progress')
        step = np.deg2rad(settings.map_angle_step_deg) if settings.map_angle_step_deg else 1 / model.A
        if not 0 < step < np.deg2rad(10):
            raise ValueError('Map angular step must be between 0 and 10 degrees')
        self.width, self.height = int(np.ceil(2 * np.pi / step)), int(np.ceil(np.pi / step))
        self.latitude = (np.arange(self.height) + .5) * np.pi / self.height - np.pi / 2
        self.q = (np.arange(self.width) + .5) * 2 * np.pi / self.width - np.pi / 4
        self.longitude = first_longitude + direction * self.q
        rx, ry, rz = self.radii
        cosine = np.cos(self.latitude)[:, None]
        self.fruit = np.stack(np.broadcast_arrays(
            rx * cosine * np.cos(self.longitude)[None],
            ry * np.sin(self.latitude)[:, None],
            rz * cosine * np.sin(self.longitude)[None]), axis=-1)
        self.jacobian = a._ellipsoid_jacobian(self.latitude, self.longitude, self.radii)
        self.visible_latitude = np.abs(self.latitude) < np.deg2rad(settings.max_latitude_deg)
        self.accum = np.zeros((self.height, self.width, 3), np.float32)
        self.weights = np.zeros((self.height, self.width), np.float32)
        self.defects = None
        self.last = None
        self.progress = 0.

    def _columns(self, start, stop):
        # q < 0 occurs only for the initial endpoint. Later turns use q + 2pi*n.
        for turn in range(max(0, int(np.floor((start + np.pi / 4) / (2 * np.pi)))),
                          max(1, int(np.ceil((stop + np.pi / 4) / (2 * np.pi))) + 1)):
            measured = self.q + turn * 2 * np.pi
            columns = np.flatnonzero((measured >= start) & (measured < stop))
            if len(columns):
                yield columns, measured[columns]

    def _sample(self, view, axes, center, columns):
        points = self.fruit[:, columns] @ axes.T
        matrix = axes @ np.diag(1 / self.radii ** 2) @ axes.T
        normals_z = points @ matrix[:, 2]
        x = (points[..., 0] + center[0]).astype(np.float32)
        y = (points[..., 1] + center[1]).astype(np.float32)
        h, w = view.object_mask.shape
        ix, iy = np.rint(x).astype(int), np.rint(y).astype(int)
        valid = ((normals_z > 0) & (x >= 0) & (y >= 0) & (x <= w - 1) & (y <= h - 1) &
                 self.visible_latitude[:, None])
        valid &= view.object_mask[np.clip(iy, 0, h - 1), np.clip(ix, 0, w - 1)] > 0
        color = cv2.remap(view.image, x, y, cv2.INTER_LINEAR)
        defects = {name: cv2.remap(mask, x, y, cv2.INTER_NEAREST) > 0
                   for name, mask in view.defect_masks.items()}
        return color, valid, defects

    def _apply(self, views, axes, centers, columns, factors, accum, weights, defects):
        for view, pose, center, factor in zip(views, axes, centers, factors):
            if set(view.defect_masks) != set(defects):
                raise a.MappingError('Selected views must supply identical defect classes')
            color, valid, masks = self._sample(view, pose, center, columns)
            weight = np.where(valid, factor[None, :], 0).astype(np.float32)
            accum[:, columns] += color * weight[..., None]
            weights[:, columns] += weight
            for name in defects:
                defects[name][:, columns] |= (masks[name] & (weight > 0)).astype(np.uint8)

    def append(self, view, axes, center, progress):
        if self.defects is None:
            self.defects = {name: np.zeros((self.height, self.width), np.uint8)
                            for name in sorted(view.defect_masks)}
            for columns, measured in self._columns(-np.pi / 4, 0.):
                self._apply([view], [axes], [center], columns, [np.ones(len(columns))],
                            self.accum, self.weights, self.defects)
        else:
            previous, previous_axes, previous_center = self.last
            if progress <= self.progress:
                raise a.MappingError('Surface longitude must progress monotonically')
            for columns, measured in self._columns(self.progress, progress):
                fraction = (measured - self.progress) / (progress - self.progress)
                self._apply([previous, view], [previous_axes, axes], [previous_center, center],
                            columns, [1 - fraction, fraction], self.accum, self.weights, self.defects)
        self.last = (view, axes, center)
        self.progress = float(progress)

    def result(self, rotations, errors, frames, diagnostics=(), captured_frames=()):
        accum, weights = self.accum.copy(), self.weights.copy()
        defects = {name: mask.copy() for name, mask in (self.defects or {}).items()}
        if self.last is not None:
            view, axes, center = self.last
            for columns, _ in self._columns(self.progress, self.progress + np.pi / 4 + 1e-10):
                self._apply([view], [axes], [center], columns, [np.ones(len(columns))],
                            accum, weights, defects)
        observed = weights > 1e-7
        bgr = np.zeros_like(accum, dtype=np.uint8)
        bgr[observed] = np.clip(accum[observed] / weights[observed, None], 0, 255).astype(np.uint8)
        total = float(self.jacobian.sum())
        area = float((observed * self.jacobian).sum())
        union = np.zeros_like(observed)
        for mask in defects.values():
            union |= mask > 0
        defect_area = float((union * observed * self.jacobian).sum())
        coverage = 100 * area / total if total else 0.
        # Successful segmentation must provide class keys, including all-clear masks.
        has_evidence = bool(defects)
        defect_pct = 100 * defect_area / area if has_evidence and area else None
        defect_full = 100 * defect_area / total if has_evidence and total else None
        vectors = [np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel() for rotation in rotations]
        component = 0 if self.settings.rotation_axis == 'x' else 1
        magnitudes = [abs(vector[component]) for vector in vectors]
        travel = float(sum(magnitudes))
        maximum = float(max(magnitudes, default=0))
        longitude = float(np.count_nonzero(observed.any(axis=0)) * 360 / self.width)
        grade, status = a._grade_map(defect_pct, coverage / 100, longitude, travel, maximum, self.settings)
        complete = (coverage / 100 >= self.settings.minimum_surface_coverage and
                    longitude >= self.settings.minimum_longitude_coverage_deg and
                    travel >= self.settings.minimum_rotation_coverage_deg and
                    (self.settings.maximum_pair_gap_deg is None or maximum <= self.settings.maximum_pair_gap_deg))
        return a.MapResult(bgr, observed.astype(np.uint8), defects,
            np.rad2deg(self.longitude), np.rad2deg(self.latitude),
            [float(vector[component]) for vector in vectors], [vector.tolist() for vector in vectors],
            list(errors), coverage, defect_pct, defect_full, grade, status,
            'sphere' if self.model.A == self.model.B else 'oblate',
            (self.model.A, self.model.B, self.model.A), travel, float(np.rad2deg(self.progress)),
            list(frames), [frame for frame in captured_frames if frame not in set(frames)],
            list(diagnostics), longitude, status == 'graded_partial', bool(complete))


def fuse_surface(views, model, rotations, errors, settings, diagnostics=(), captured_frames=()):
    axes, radii, longitude, direction, progress = a._map_trajectory(model, rotations, settings)
    atlas = SurfaceAtlas(model, settings, longitude[0], direction, radii)
    for view, pose, ellipse, position in zip(views, axes, model.ellipses, progress):
        atlas.append(view, pose, ellipse.center, position)
    result = atlas.result(rotations, errors, [v.frame_index for v in views], diagnostics, captured_frames)
    # Standalone callers retain the existing explicit all-clear contract.
    if not result.defect_maps and settings.defect_observations_complete and result.observed_surface_pct:
        result.defect_pct_of_observed = result.defect_pct_of_full_surface = 0.
        maximum = max((abs(v) for v in result.pair_rotations_deg), default=0.)
        result.grade, result.status = a._grade_map(0., result.observed_surface_pct / 100,
            result.observed_longitude_deg, result.rotation_coverage_deg, maximum, settings)
        result.grade_provisional = result.status == 'graded_partial'
    return result
