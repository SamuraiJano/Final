"""Raw-ID diagnostics for the standalone tracker experiment, without identity correction."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import hypot, isfinite
from statistics import mean, median

import numpy as np


@dataclass(frozen=True)
class DiagnosticSettings:
    """Application-defined diagnostics; these are not official Ultralytics thresholds."""

    short_lifetime_seconds: tuple[float, ...] = (.25, .5, 1.)
    substantial_lifetime_seconds: float = 1.
    substantial_consistency_percent: float = 90.
    fragmentation_window_seconds: float = .5
    fragmentation_distance_box_diagonals: float = .5

    def __post_init__(self):
        seconds = (*self.short_lifetime_seconds, self.substantial_lifetime_seconds,
                   self.fragmentation_window_seconds, self.fragmentation_distance_box_diagonals)
        if not all(isfinite(x) and x > 0 for x in seconds):
            raise ValueError('Diagnostic time and distance thresholds must be finite and positive')
        if not 0 <= self.substantial_consistency_percent <= 100:
            raise ValueError('Consistency threshold must be between 0 and 100')


TRACK_FIELDS = ('tracker_name', 'mode', 'track_id', 'first_frame', 'last_frame',
                'first_timestamp', 'last_timestamp', 'observed_frames',
                'possible_frames_between_first_and_last', 'lifetime_seconds',
                'processed_video_frames_percent', 'consistency_percent',
                'mean_box_width', 'mean_box_height')
EVENT_FIELDS = ('tracker_name', 'mode', 'event', 'frame', 'timestamp', 'track_id',
                'previous_track_id', 'gap_seconds', 'distance_pixels',
                'distance_limit_pixels', 'predicted_x', 'predicted_y')
OBSERVATION_FIELDS = ('frame', 'timestamp', 'track_id', 'x1', 'y1', 'x2', 'y2', 'confidence', 'class_id')
FRAME_FIELDS = ('frame', 'timestamp', 'active_ids', 'processing_seconds')


class RawTrackStatistics:
    def __init__(self, tracker_name: str, mode: str, settings: DiagnosticSettings | None = None):
        self.name, self.mode = tracker_name, mode
        self.settings = settings or DiagnosticSettings()
        self.states: dict[int, dict] = {}
        self.events: list[dict] = []
        self.frames: list[dict] = []
        self.previous_ids: set[int] = set()
        self.last_timestamp = -1.

    def _event(self, kind, frame, timestamp, track_id, **details):
        self.events.append(dict(tracker_name=self.name, mode=self.mode, event=kind,
                                frame=frame, timestamp=timestamp, track_id=track_id, **details))

    def observe(self, frame: int, timestamp: float, raw_tracks, processing_seconds: float):
        """Ultralytics axis-aligned update rows: x1,y1,x2,y2,raw_id,score,class,index."""
        rows = np.asarray(raw_tracks, dtype=np.float32)
        if rows.size == 0:
            rows = np.empty((0, 8), dtype=np.float32)
        if rows.ndim != 2 or rows.shape[1] != 8 or not np.isfinite(rows).all():
            raise ValueError('Tracker must return finite axis-aligned rows with eight columns')
        if frame != len(self.frames) or not isfinite(timestamp) or timestamp < self.last_timestamp:
            raise ValueError('Frames must be consecutive from zero with monotonic video timestamps')
        if not isfinite(processing_seconds) or processing_seconds <= 0:
            raise ValueError('Processing duration must be finite and positive')
        ids = [int(row[4]) for row in rows]
        if len(set(ids)) != len(ids) or any(i <= 0 or i != row[4] for i, row in zip(ids, rows)):
            raise ValueError('Duplicate or invalid raw IDs returned in one frame')
        if any(row[2] <= row[0] or row[3] <= row[1] for row in rows):
            raise ValueError('Tracker returned a box with nonpositive dimensions')
        current = set(ids)
        new = [row for row in rows if int(row[4]) not in self.states]
        self._fragmentations(new, current, frame, timestamp)
        for disappeared in sorted(self.previous_ids - current):
            self._event('id_disappeared', frame, timestamp, disappeared)
        for row in rows:
            track_id = int(row[4])
            box = [float(x) for x in row[:4]]
            center = [(box[0]+box[2])/2, (box[1]+box[3])/2]
            if track_id not in self.states:
                self._event('id_first_observed', frame, timestamp, track_id)
                self.states[track_id] = dict(first_frame=frame, first_timestamp=timestamp,
                                            count=0, widths=0., heights=0., history=[])
            elif track_id not in self.previous_ids:
                self._event('id_reappeared', frame, timestamp, track_id)
            state = self.states[track_id]
            state.update(last_frame=frame, last_timestamp=timestamp, box=box, class_id=int(row[6]))
            state['count'] += 1
            state['widths'] += box[2]-box[0]
            state['heights'] += box[3]-box[1]
            state['history'] = (state['history'] + [(timestamp, center)])[-2:]
        self.frames.append(dict(frame=frame, timestamp=timestamp, active_ids=len(ids),
                                processing_seconds=processing_seconds))
        self.previous_ids = current
        self.last_timestamp = timestamp

    def _fragmentations(self, new, current, frame, timestamp):
        candidates = []
        for row in new:
            new_id = int(row[4])
            width, height = float(row[2]-row[0]), float(row[3]-row[1])
            center = [(float(row[0])+float(row[2]))/2, (float(row[1])+float(row[3]))/2]
            for old_id, state in self.states.items():
                gap = timestamp-state['last_timestamp']
                if (old_id in current or gap <= 0 or
                        gap > self.settings.fragmentation_window_seconds+1e-9 or
                        int(row[6]) != state['class_id']):
                    continue
                old_box = state['box']
                old_width, old_height = old_box[2]-old_box[0], old_box[3]-old_box[1]
                if not (.5 <= width/old_width <= 2 and .5 <= height/old_height <= 2):
                    continue
                history = state['history']
                predicted = list(history[-1][1])
                if len(history) == 2 and history[-1][0] > history[0][0]:
                    dt = history[-1][0]-history[0][0]
                    predicted = [v+(v-u)*gap/dt for u, v in zip(history[0][1], history[-1][1])]
                distance = hypot(center[0]-predicted[0], center[1]-predicted[1])
                limit = self.settings.fragmentation_distance_box_diagonals * max(
                    hypot(width, height), hypot(old_width, old_height))
                if distance <= limit:
                    candidates.append((distance/limit, old_id, new_id, gap, distance, limit, predicted))
        # One nearest candidate pair per old/new ID in this frame. IDs themselves stay untouched.
        used_old, used_new = set(), set()
        for _, old_id, new_id, gap, distance, limit, predicted in sorted(candidates):
            if old_id in used_old or new_id in used_new:
                continue
            used_old.add(old_id)
            used_new.add(new_id)
            self._event('Suspected ID Fragmentation', frame, timestamp, new_id,
                        previous_track_id=old_id, gap_seconds=gap, distance_pixels=distance,
                        distance_limit_pixels=limit, predicted_x=predicted[0], predicted_y=predicted[1])

    def finish(self) -> tuple[dict, list[dict]]:
        count = len(self.frames)
        tracks = []
        for track_id, state in sorted(self.states.items()):
            possible = state['last_frame']-state['first_frame']+1
            tracks.append(dict(tracker_name=self.name, mode=self.mode, track_id=track_id,
                               first_frame=state['first_frame'], last_frame=state['last_frame'],
                               first_timestamp=state['first_timestamp'], last_timestamp=state['last_timestamp'],
                               observed_frames=state['count'], possible_frames_between_first_and_last=possible,
                               lifetime_seconds=state['last_timestamp']-state['first_timestamp'],
                               processed_video_frames_percent=100*state['count']/count,
                               consistency_percent=100*state['count']/possible,
                               mean_box_width=state['widths']/state['count'],
                               mean_box_height=state['heights']/state['count']))
        lifetime = [t['lifetime_seconds'] for t in tracks]
        consistency = [t['consistency_percent'] for t in tracks]
        seconds = sum(f['processing_seconds'] for f in self.frames)
        active = [f['active_ids'] for f in self.frames]
        short = [dict(threshold_seconds=x, count=sum(t < x for t in lifetime),
                      percent=100*sum(t < x for t in lifetime)/len(tracks) if tracks else None)
                 for x in self.settings.short_lifetime_seconds]
        bins = (0., .25, .5, 1., 2., 5., float('inf'))
        distribution = [dict(label=f'{lo:g}–{hi:g} s' if isfinite(hi) else f'≥{lo:g} s',
                             count=sum(lo <= t < hi for t in lifetime))
                        for lo, hi in zip(bins, bins[1:])]
        summary = dict(tracker_name=self.name, mode=self.mode, processed_frames=count,
                       timing_scope='detector_plus_tracker' if self.mode == 'full' else 'tracker_only',
                       total_processing_seconds=seconds, processing_fps=count/seconds if seconds else None,
                       average_time_ms=1000*seconds/count if count else None,
                       unique_raw_ids=len(tracks), maximum_active_ids=max(active, default=0),
                       mean_active_ids=mean(active) if active else 0,
                       final_active_ids=active[-1] if active else 0,
                       mean_lifetime_seconds=mean(lifetime) if lifetime else None,
                       median_lifetime_seconds=median(lifetime) if lifetime else None,
                       minimum_lifetime_seconds=min(lifetime, default=None),
                       maximum_lifetime_seconds=max(lifetime, default=None),
                       mean_consistency_percent=mean(consistency) if consistency else None,
                       median_consistency_percent=median(consistency) if consistency else None,
                       substantial_persistence_ids=sum(t['lifetime_seconds'] >= self.settings.substantial_lifetime_seconds
                           and t['consistency_percent'] >= self.settings.substantial_consistency_percent for t in tracks),
                       suspected_id_fragmentations=sum(e['event'] == 'Suspected ID Fragmentation' for e in self.events),
                       short_lived_ids=short, lifetime_distribution=distribution,
                       diagnostic_settings=asdict(self.settings))
        summary['substantial_persistence_percent'] = (
            100*summary['substantial_persistence_ids']/len(tracks) if tracks else None)
        for diagnostic in short:
            key = f"short_lived_under_{diagnostic['threshold_seconds']:g}s"
            summary[key+'_count'] = diagnostic['count']
            summary[key+'_percent'] = diagnostic['percent']
        return summary, tracks
