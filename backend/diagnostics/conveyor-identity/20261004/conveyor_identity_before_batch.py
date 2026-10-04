"""Validate TrackTrack observations before storing views under a stable fruit ID.

Only image coordinates and elapsed seconds are used. Motion is supporting
evidence, not physical-identity ground truth. Ambiguous links are split rather
than allowing uncertain observations to contaminate an established fruit.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import csv
import json
import math
import os
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class ConveyorIdentitySettings:
    conveyor_identity_validation: bool = True
    conveyor_direction: str = "top_to_bottom"
    enable_motion_validation: bool = True
    enable_order_validation: bool = True
    debug_identity_overlay: bool = False
    debug_identity_csv: bool = False
    reference_speed_px_s: float = 395.83
    fallback_fps: float = 29.9307
    history_observations: int = 8
    lost_track_buffer_frames: int = 30
    prediction_gate_diameters: float = .35
    gap_uncertainty_diameters: float = .04
    ambiguity_margin_diameters: float = .12
    raw_id_support: float = .03
    maximum_size_ratio: float = 1.5
    backward_tolerance_diameters: float = .2
    local_horizontal_overlap: float = .35
    local_centre_separation_widths: float = .6
    order_separation_heights: float = .15
    order_penalty: float = .2
    scene_minimum_observations: int = 3
    scene_history_samples: int = 128

    def __post_init__(self):
        if self.conveyor_direction not in {"top_to_bottom", "bottom_to_top"}:
            raise ValueError("Unsupported conveyor_direction")
        for name in ("conveyor_identity_validation", "enable_motion_validation", "enable_order_validation",
                     "debug_identity_overlay", "debug_identity_csv"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
        for name in ("history_observations", "lost_track_buffer_frames", "scene_minimum_observations", "scene_history_samples"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.history_observations < 3 or self.scene_minimum_observations < 3:
            raise ValueError("Motion estimation requires at least three history/scene observations")
        for name in ("reference_speed_px_s", "fallback_fps", "prediction_gate_diameters", "maximum_size_ratio"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.maximum_size_ratio < 1:
            raise ValueError("maximum_size_ratio must be >=1")
        for name in ("gap_uncertainty_diameters", "ambiguity_margin_diameters", "raw_id_support",
                     "backward_tolerance_diameters", "local_horizontal_overlap",
                     "local_centre_separation_widths", "order_separation_heights", "order_penalty"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and within [0,1]")

    @classmethod
    def from_environment(cls):
        """One optional JSON configuration, with explicit debug environment overrides."""
        path = os.getenv("FRUIT_IDENTITY_CONFIG", "").strip()
        values = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
        if not isinstance(values, dict):
            raise ValueError("FRUIT_IDENTITY_CONFIG must contain a JSON object")
        for key, env in (("conveyor_identity_validation", "FRUIT_CONVEYOR_IDENTITY_VALIDATION"),
                         ("debug_identity_overlay", "FRUIT_DEBUG_IDENTITY_OVERLAY"),
                         ("debug_identity_csv", "FRUIT_DEBUG_IDENTITY_CSV")):
            if env in os.environ:
                value = os.environ[env].strip().lower()
                if value not in {"true", "false", "1", "0"}:
                    raise ValueError(f"{env} must be true/false or 1/0")
                values[key] = value in {"true", "1"}
        return cls(**values)


@dataclass
class FruitState:
    fruit_id: int
    current_tracker_id: int
    history: deque = field(default_factory=deque)  # (seconds, centre, actual box, clipped)
    recent_velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))
    last_accepted_centre: np.ndarray = field(default_factory=lambda: np.zeros(2))
    last_seen_timestamp: float = 0.
    last_seen_frame: int = 0
    status: str = "active"
    observations: int = 0


class ConveyorIdentityManager:
    CSV_FIELDS = ("frame_number", "timestamp", "tracker_id", "fruit_id", "cx", "cy",
                  "predicted_cx", "predicted_cy", "prediction_error", "vx", "vy",
                  "identity_corrected", "correction_reason")

    def __init__(self, settings=None, lost_track_buffer_frames=None):
        self.settings = settings or ConveyorIdentitySettings.from_environment()
        self.lost_track_buffer_frames = (self.settings.lost_track_buffer_frames
                                        if lost_track_buffer_frames is None else int(lost_track_buffer_frames))
        if self.lost_track_buffer_frames < 1:
            raise ValueError("Lost-track buffer must be positive")
        self.states: dict[int, FruitState] = {}
        self.metadata: dict[int, dict] = {}
        self.next_id = 1
        self.last_frame = None
        self.last_timestamp = None
        self.fps = self.settings.fallback_fps
        sign = 1 if self.settings.conveyor_direction == "top_to_bottom" else -1
        self.scene_velocity = np.array([0., sign * self.settings.reference_speed_px_s])
        self.scene_samples = deque(maxlen=self.settings.scene_history_samples)
        self.last_decisions = []
        self._csv_stream = self._csv_writer = self._video_writer = None
        self._debug_directory = None

    def configuration(self):
        return {"version": 4, "component": "ConveyorIdentityManager", **asdict(self.settings),
                "effective_lost_track_buffer_frames": self.lost_track_buffer_frames}

    def set_frame_rate(self, fps):
        if math.isfinite(float(fps)) and float(fps) > 0:
            self.fps = float(fps)

    def configure_debug(self, directory):
        self.close_debug()
        self._debug_directory = Path(directory)
        if self.settings.debug_identity_csv or self.settings.debug_identity_overlay:
            self._debug_directory.mkdir(parents=True, exist_ok=True)
        if self.settings.debug_identity_csv:
            self._csv_stream = (self._debug_directory / "identity_debug.csv").open("w", newline="", encoding="utf-8")
            self._csv_writer = csv.DictWriter(self._csv_stream, fieldnames=self.CSV_FIELDS)
            self._csv_writer.writeheader()

    def close_debug(self):
        if self._csv_stream is not None:
            self._csv_stream.close()
        if self._video_writer is not None:
            self._video_writer.release()
        self._csv_stream = self._csv_writer = self._video_writer = None

    def drop(self, fruit_id):
        self.states.pop(int(fruit_id), None)
        self.metadata.pop(int(fruit_id), None)
        # next_id is never rewound, including after finalizing a fruit.

    @staticmethod
    def _edge(box, shape):
        height, width = shape[:2]
        return box[0] <= 2 or box[1] <= 2 or box[2] >= width-2 or box[3] >= height-2

    def _time(self, frame, timestamp):
        supplied = timestamp is not None and math.isfinite(float(timestamp)) and float(timestamp) >= 0
        if supplied and (self.last_timestamp is None or float(timestamp) > self.last_timestamp):
            return float(timestamp), "timestamp"
        if self.last_timestamp is None:
            return frame / self.fps, "frame_rate_fallback"
        return self.last_timestamp + (frame-self.last_frame)/self.fps, "frame_rate_fallback"

    def _velocity(self, state):
        points = [item for item in state.history if not item[3]]
        if len(points) < 2:
            return self.scene_velocity.copy()
        times = np.array([item[0] for item in points])
        centres = np.array([item[1] for item in points])
        velocity = np.median(np.diff(centres, axis=0) / np.diff(times)[:, None], axis=0)
        # Tiny negative box jitter must not create a backwards conveyor model.
        sign = 1 if self.settings.conveyor_direction == "top_to_bottom" else -1
        velocity[1] = sign * max(0., sign * velocity[1])
        return velocity

    def _local(self, a, b):
        wa, wb = a[2]-a[0], b[2]-b[0]
        overlap = max(0., min(a[2], b[2])-max(a[0], b[0])) / min(wa, wb)
        separation = abs((a[0]+a[2]-b[0]-b[2])/2) / ((wa+wb)/2)
        return (overlap >= self.settings.local_horizontal_overlap or
                separation <= self.settings.local_centre_separation_widths)

    def _order_conflict(self, a, b, proposed_a, proposed_b, predicted_a, predicted_b):
        old_a, old_b = a.history[-1][2], b.history[-1][2]
        if not self._local(old_a, old_b) or not self._local(proposed_a, proposed_b):
            return False
        height = ((old_a[3]-old_a[1]) + (old_b[3]-old_b[1]))/2
        tolerance = self.settings.order_separation_heights * height
        old_delta = a.last_accepted_centre[1]-b.last_accepted_centre[1]
        new_delta = (proposed_a[1]+proposed_a[3]-proposed_b[1]-proposed_b[3])/2
        predicted_delta = predicted_a[1]-predicted_b[1]
        return (abs(old_delta) > tolerance and abs(new_delta) > tolerance and
                old_delta * new_delta < 0 and old_delta * predicted_delta > 0)

    def update(self, boxes, raw_ids, frame, shape, timestamp=None):
        boxes = np.asarray(boxes, dtype=float).reshape(-1, 4)
        supplied_ids = np.asarray(raw_ids).ravel()
        if (len(boxes) != len(supplied_ids) or not np.isfinite(supplied_ids).all() or
                np.any(supplied_ids <= 0) or np.any(supplied_ids != np.floor(supplied_ids))):
            raise ValueError("Identity input requires positive integer tracker IDs aligned with boxes")
        raw_ids = supplied_ids.astype(int)
        if len(set(raw_ids.tolist())) != len(raw_ids):
            raise ValueError("Identity input requires unique tracker IDs per frame")
        if not np.isfinite(boxes).all() or np.any(boxes[:, 2:] <= boxes[:, :2]):
            raise ValueError("Identity boxes must be finite with positive area")
        if isinstance(frame, bool) or not isinstance(frame, (int, np.integer)) or frame < 0:
            raise ValueError("Frame must be a nonnegative integer")
        if self.last_frame is not None and frame <= self.last_frame:
            raise ValueError("Identity frames must increase")
        now, clock_source = self._time(frame, timestamp)
        prior = [state for state in self.states.values()
                 if frame-state.last_seen_frame <= self.lost_track_buffer_frames]
        self.states = {state.fruit_id: state for state in prior}
        for state in prior:
            state.status = "lost"
        centres = (boxes[:, :2]+boxes[:, 2:])/2
        predictions, velocities = [], []
        costs = np.full((len(prior), len(boxes)), np.inf)
        errors = np.full_like(costs, np.inf)
        for i, state in enumerate(prior):
            velocity = self._velocity(state)
            predicted = state.last_accepted_centre + velocity * (now-state.last_seen_timestamp)
            predictions.append(predicted)
            velocities.append(velocity)
            old = state.history[-1][2]
            size = old[2:]-old[:2]
            for j, box in enumerate(boxes):
                edge = state.history[-1][3] or self._edge(box, shape)
                new_size = box[2:]-box[:2]
                scale = max(float(np.max(size if edge else np.sqrt(size.prod()))),
                            float(np.max(new_size if edge else np.sqrt(new_size.prod()))), 1.)
                error = float(np.linalg.norm(centres[j]-predicted))
                normalised = error / scale
                errors[i, j] = error
                if self.settings.enable_motion_validation:
                    gate = self.settings.prediction_gate_diameters + self.settings.gap_uncertainty_diameters * (frame-state.last_seen_frame-1)
                    if normalised > gate:
                        continue
                    if not edge and np.max(np.maximum(size/new_size, new_size/size)) > self.settings.maximum_size_ratio:
                        continue
                    sign = 1 if self.settings.conveyor_direction == "top_to_bottom" else -1
                    if sign*(centres[j, 1]-state.last_accepted_centre[1]) < -self.settings.backward_tolerance_diameters*scale:
                        continue
                costs[i, j] = normalised - self.settings.raw_id_support * (state.current_tracker_id == raw_ids[j])

        # Pairwise order is a validation of the global assignment, not a global
        # sorting of detections. Lateral separation removes the constraint.
        assignments = {}
        if costs.size:
            unmatched = len(prior)+1.
            matrix = np.concatenate((np.where(np.isfinite(costs), costs, unmatched*2),
                                     np.full((len(prior), len(prior)), unmatched)), axis=1)
            ii, jj = linear_sum_assignment(matrix)
            assignments = {int(i): int(j) for i, j in zip(ii, jj)
                           if j < len(boxes) and np.isfinite(costs[i, j])}
        order_evidence = set()
        order_rejected = set()
        if self.settings.enable_order_validation:
            # What would blindly following raw IDs have done to local order?
            raw_indices = {int(value): j for j, value in enumerate(raw_ids)}
            for i in list(assignments):
                for k in list(assignments):
                    if k <= i:
                        continue
                    j, l = assignments[i], assignments[k]
                    a, b = prior[i], prior[k]
                    r, s = raw_indices.get(a.current_tracker_id), raw_indices.get(b.current_tracker_id)
                    if r is not None and s is not None and self._order_conflict(a, b, boxes[r], boxes[s], predictions[i], predictions[k]):
                        order_evidence.update((i, k))
                    if self._order_conflict(a, b, boxes[j], boxes[l], predictions[i], predictions[k]):
                        # Swap only when both links satisfy the motion gates and
                        # the secondary penalty does not outweigh trajectory fit.
                        alternative = costs[i, l] + costs[k, j]
                        if (np.isfinite(alternative) and alternative <= costs[i, j]+costs[k, l]+self.settings.order_penalty and
                                not self._order_conflict(a, b, boxes[l], boxes[j], predictions[i], predictions[k])):
                            assignments[i], assignments[k] = l, j
                            order_evidence.update((i, k))
                        else:
                            order_rejected.update((i, k))
            # Recheck after pair changes; never admit an unresolved order flip.
            items = list(assignments.items())
            for position, (i, j) in enumerate(items):
                for k, l in items[position+1:]:
                    if self._order_conflict(prior[i], prior[k], boxes[j], boxes[l], predictions[i], predictions[k]):
                        order_rejected.update((i, k))

        accepted, ambiguous = {}, set(order_rejected)
        for i, j in assignments.items():
            if i in order_rejected:
                continue
            # Raw continuity is supporting evidence for a plausible association.
            # Changed raw IDs must beat competing trajectories in both directions.
            alternatives = np.delete(costs[i], j)
            competitors = np.delete(costs[:, j], i)
            margin = self.settings.ambiguity_margin_diameters
            clear = ((not np.isfinite(alternatives).any() or np.min(alternatives) - costs[i, j] >= margin) and
                     (not np.isfinite(competitors).any() or np.min(competitors) - costs[i, j] >= margin))
            same_raw = prior[i].current_tracker_id == raw_ids[j]
            raw_plausible = (same_raw and
                             (not np.isfinite(alternatives).any() or costs[i, j] <= np.min(alternatives)+self.settings.raw_id_support) and
                             (not np.isfinite(competitors).any() or costs[i, j] <= np.min(competitors)+self.settings.raw_id_support))
            if clear or raw_plausible:
                accepted[j] = i
            else:
                ambiguous.add(i)

        decisions = []
        protected = {prior[i].fruit_id for i in accepted.values()}
        retire = set()
        for j, (box, raw_id) in enumerate(zip(boxes, raw_ids)):
            i = accepted.get(j)
            previous = prior[i] if i is not None else None
            corrected = previous is not None and previous.current_tracker_id != int(raw_id)
            reason = ("trajectory_order_correction" if corrected and i in order_evidence else
                      "trajectory_correction" if corrected else
                      "recovered_after_gap" if previous is not None and frame-previous.last_seen_frame > 1 else "continued")
            if previous is None:
                related = {state.fruit_id for k, state in enumerate(prior)
                           if (state.current_tracker_id == raw_id or np.isfinite(costs[k, j]))
                           and state.fruit_id not in protected}
                reason = ("ambiguous_association" if np.isfinite(costs[:, j]).any() else
                          "motion_or_size_discontinuity" if related else "new_track")
                for identity in related:
                    self.metadata[identity]["identity_status"] = "uncertain"
                    self.metadata[identity]["identity_events"].append({"frame": int(frame), "reason": reason})
                retire.update(related)
                fruit_id = self.next_id
                self.next_id += 1
                state = FruitState(fruit_id, int(raw_id), history=deque(maxlen=self.settings.history_observations))
                self.states[fruit_id] = state
                self.metadata[fruit_id] = {"fruit_id": fruit_id, "identity_status": "motion_consistent" if reason == "new_track" else "uncertain",
                                           "source_tracker_ids": [], "identity_events": [], "identity_guard": self.configuration()}
                predicted, velocity, error = None, self.scene_velocity.copy(), None
            else:
                state = previous
                fruit_id = state.fruit_id
                predicted, velocity, error = predictions[i], velocities[i], float(errors[i, j])
            state.current_tracker_id = int(raw_id)
            state.last_accepted_centre = centres[j].copy()
            state.last_seen_timestamp, state.last_seen_frame, state.status = now, int(frame), "active"
            state.observations += 1
            state.history.append((now, centres[j].copy(), box.copy(), self._edge(box, shape)))
            state.recent_velocity = self._velocity(state)
            meta = self.metadata[fruit_id]
            if int(raw_id) not in meta["source_tracker_ids"]:
                meta["source_tracker_ids"].append(int(raw_id))
            decision = {"frame": int(frame), "timestamp": now, "timestamp_source": clock_source,
                        "raw_track_id": int(raw_id), "tracker_id": int(raw_id), "fruit_id": fruit_id,
                        "capture_id": fruit_id, "reason": reason, "identity_corrected": bool(corrected),
                        "cx": float(centres[j, 0]), "cy": float(centres[j, 1]),
                        "predicted_cx": None if predicted is None else float(predicted[0]),
                        "predicted_cy": None if predicted is None else float(predicted[1]),
                        "prediction_error": error, "vx": float(velocity[0]), "vy": float(velocity[1])}
            if reason != "continued":
                meta["identity_events"].append(decision.copy())
            decisions.append(decision)
            if (previous is not None and state.observations >= self.settings.scene_minimum_observations and
                    sum(not point[3] for point in state.history) >= self.settings.scene_minimum_observations and
                    not state.history[-1][3] and meta["identity_status"] != "uncertain" and
                    state.recent_velocity[1] * self.scene_velocity[1] > 0):
                self.scene_samples.append(state.recent_velocity.copy())
            if corrected and (self.settings.debug_identity_overlay or self.settings.debug_identity_csv):
                print(f"IDENTITY CORRECTION: tracker_id {raw_id} reassigned to fruit_id {fruit_id}; reason: {reason}")
            if self._csv_writer is not None:
                row = {key: decision.get(key) for key in self.CSV_FIELDS}
                row.update(frame_number=int(frame), correction_reason=reason)
                self._csv_writer.writerow(row)
        for identity in retire:
            self.states.pop(identity, None)
        if self.scene_samples:
            self.scene_velocity = np.median(np.asarray(self.scene_samples), axis=0)
        if self._csv_stream is not None:
            self._csv_stream.flush()
        self.last_frame, self.last_timestamp, self.last_decisions = int(frame), now, decisions
        return decisions

    def draw_debug(self, frame):
        """Return an overlay copy; never paint on mapper/detector source pixels."""
        image = frame.copy()
        for decision in self.last_decisions:
            state = self.states[decision["fruit_id"]]
            box = np.rint(state.history[-1][2]).astype(int)
            colour = (0, 180, 255) if decision["identity_corrected"] else (70, 235, 100)
            cv2.rectangle(image, tuple(box[:2]), tuple(box[2:]), colour, 2)
            points = np.rint([item[1] for item in state.history]).astype(np.int32)
            cv2.polylines(image, [points], False, colour, 2)
            predicted = state.last_accepted_centre + state.recent_velocity / self.fps
            cv2.drawMarker(image, tuple(np.rint(predicted).astype(int)), (255, 200, 80), cv2.MARKER_CROSS, 16, 2)
            label = f'T:{decision["tracker_id"]} F:{decision["fruit_id"]}'
            if decision["identity_corrected"]:
                label += " CORRECTED"
            cv2.putText(image, label, (max(0, box[0]), max(24, box[1]-6)), cv2.FONT_HERSHEY_SIMPLEX, .6, colour, 2)
        cv2.putText(image, f"Frame {self.last_frame} | t={self.last_timestamp:.4f}s", (12, image.shape[0]-16), cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 2)
        return image

    def write_debug(self, frame):
        if not self.settings.debug_identity_overlay or self._debug_directory is None:
            return
        if self._video_writer is None:
            self._video_writer = cv2.VideoWriter(str(self._debug_directory / "identity_debug.mp4"),
                                                 cv2.VideoWriter_fourcc(*"mp4v"), self.fps,
                                                 (frame.shape[1], frame.shape[0]))
            if not self._video_writer.isOpened():
                raise RuntimeError("Cannot create identity debug overlay video")
        self._video_writer.write(self.draw_debug(frame))
