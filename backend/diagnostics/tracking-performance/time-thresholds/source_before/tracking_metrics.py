"""Passive, run-scoped conveyor checkpoint measurements from raw TrackTrack IDs.

No detection, association, identity repair or grading occurs here. A configured
rectangle is required for spatial metrics; timing and observations are retained
even before calibration. Journal replay uses observations, never model inference.
"""
from __future__ import annotations

import csv
import json
import math
import threading
from bisect import bisect_right, insort
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


DIRECTIONS = ('top_to_bottom', 'bottom_to_top', 'left_to_right', 'right_to_left')
EXPORTS = ('tracking_summary.csv', 'region_continuity.csv',
           'checkpoint_crossings.csv', 'tracking_events.csv')


@dataclass(frozen=True)
class TrackingConfig:
    # Normalised camera coordinates; None means the physical region is unset.
    region: tuple[float, float, float, float] | None = None
    direction: str = 'top_to_bottom'
    checkpoint_interval_percent: int = 1
    lost_buffer_frames: int = 30
    entry_band_percent: float = 5.0
    fragment_gap_frames: int = 10
    max_interpolation_seconds: float = 0.5

    def __post_init__(self):
        if self.direction not in DIRECTIONS:
            raise ValueError('Invalid conveyor direction')
        step = self.checkpoint_interval_percent
        if isinstance(step, bool) or not isinstance(step, int) or step < 1 or step > 100 or 100 % step:
            raise ValueError('Checkpoint interval must be a positive integer divisor of 100')
        for value in (self.lost_buffer_frames, self.fragment_gap_frames):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000:
                raise ValueError('Frame buffers must be integers from 1 to 1000')
        if not math.isfinite(self.entry_band_percent) or not 0 < self.entry_band_percent < 50:
            raise ValueError('Entry band must be between 0 and 50 percent')
        if not math.isfinite(self.max_interpolation_seconds) or self.max_interpolation_seconds <= 0:
            raise ValueError('Interpolation time limit must be positive')
        if self.region is not None:
            if len(self.region) != 4 or not all(math.isfinite(v) for v in self.region):
                raise ValueError('Region needs four finite normalised coordinates')
            left, top, right, bottom = self.region
            if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
                raise ValueError('Region must be a nonempty rectangle within the camera image')
            object.__setattr__(self, 'region', tuple(self.region))


def config_from_dict(data: dict) -> TrackingConfig:
    try:
        return TrackingConfig(**data)
    except (TypeError, OverflowError) as error:
        raise ValueError('Invalid tracking configuration') from error


def _atomic_json(path: Path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


class TrackingMetrics:
    def __init__(self, config: TrackingConfig | None = None, output: Path | None = None,
                 job_id: str | None = None):
        self.config = config or TrackingConfig()
        self.job_id = job_id
        self.output = output
        self.lock = threading.RLock()
        self.tracks: dict[int, dict] = {}
        self.crossings = {p: {} for p in range(0, 101, self.config.checkpoint_interval_percent)}
        self.events: list[dict] = []
        self.frames = 0
        self.processing_seconds = 0.0
        self.timed_frames = 0
        self.last_frame = -1
        self.state = 'collecting'
        self.forward_motion = 0
        self.reverse_motion = 0
        self.last_boxes = []
        self.last_shape = None
        self._cache = None
        self._journal = None
        if output is not None:
            output.mkdir(parents=True, exist_ok=True)
            _atomic_json(output / 'tracking_config.json', asdict(self.config))
            self._journal = (output / 'tracking_observations.jsonl').open('w', encoding='utf-8')

    def _position(self, center, shape):
        if self.config.region is None:
            return None, False
        h, w = shape[:2]
        x, y = center[0] / w, center[1] / h
        left, top, right, bottom = self.config.region
        vertical = self.config.direction in DIRECTIONS[:2]
        position = (y-top)/(bottom-top) if vertical else (x-left)/(right-left)
        if self.config.direction in ('bottom_to_top', 'right_to_left'):
            position = 1-position
        lateral = left <= x <= right if vertical else top <= y <= bottom
        # Avoid losing an exact integer checkpoint to normalised float noise.
        return round(100 * position, 10), lateral

    def _event(self, kind, ids, frame, position, description, **extra):
        self.events.append(dict(frame=frame, position_percent=position, event_type=kind,
                                IDs=list(ids), description=description, **extra))

    def observe(self, frame_index, timestamp, shape, ids, boxes, processing_seconds=None):
        """Consume the already filtered fruit boxes, before the identity guard.

        Crossings use only consecutive processed observations with the same raw
        ID. Missing frames cannot be silently bridged into complete coverage.
        """
        with self.lock:
            frame_index = int(frame_index)
            if frame_index <= self.last_frame:
                raise ValueError('Observation frames must increase within one run')
            if len(ids) != len(boxes) or len(set(int(i) for i in ids)) != len(ids):
                raise ValueError('Raw IDs and boxes must be aligned and unique')
            ids = [int(i) for i in ids]
            boxes = [[float(v) for v in box] for box in boxes]
            if any(len(b) != 4 or not all(math.isfinite(v) for v in b) for b in boxes):
                raise ValueError('Invalid tracking box')
            timestamp = float(timestamp) if timestamp is not None and math.isfinite(timestamp) else None
            if processing_seconds is not None:
                processing_seconds = float(processing_seconds)
                if not math.isfinite(processing_seconds) or processing_seconds < 0:
                    raise ValueError('Invalid measured processing time')
                self.processing_seconds += processing_seconds
                self.timed_frames += 1
            if self._journal:
                self._journal.write(json.dumps(dict(frame=frame_index, timestamp=timestamp,
                    shape=list(shape[:2]), ids=ids, boxes=boxes, processing_seconds=processing_seconds),
                    allow_nan=False) + '\n')
                self._journal.flush()
            self._cache = None
            self.last_boxes = list(zip(ids, boxes))
            self.last_shape = shape[:2]
            present = set(ids)
            for track_id, box in zip(ids, boxes):
                center = ((box[0]+box[2])/2, (box[1]+box[3])/2)
                position, lateral = self._position(center, shape)
                inside = position is not None and lateral and 0 <= position <= 100
                track = self.tracks.get(track_id)
                previous = None if track is None else track['last']
                if track is None:
                    track = self.tracks[track_id] = dict(id=track_id, first_frame=frame_index,
                        frames_tracked=0, checkpoints={}, entered=False, lost=False,
                        terminal=False, fragmented_to=None, velocity=(0.0, 0.0))
                    band = self.config.entry_band_percent
                    # IDs already visible when recording starts are left censored.
                    if self.frames > 0 and inside and band < position < 100-band:
                        self._event('mid_region_new_id', [track_id], frame_index, position,
                                    'Raw ID first appeared well inside the configured region.')
                    if self.frames > 0 and inside:
                        self._fragment_candidate(track_id, center, box, frame_index, position, present)
                track['frames_tracked'] += 1
                current = dict(frame=frame_index, timestamp=timestamp, center=center,
                               position=position, lateral=lateral, inside=inside, box=box)
                if previous and position is not None:
                    gap = frame_index-previous['frame']
                    track['velocity'] = tuple((center[k]-previous['center'][k])/gap for k in (0, 1))
                    delta = position-previous['position']
                    if lateral and previous['lateral'] and abs(delta) > 0.1:
                        self.forward_motion += int(delta > 0)
                        self.reverse_motion += int(delta < 0)
                    time_ok = (timestamp is None or previous['timestamp'] is None or
                               0 <= timestamp-previous['timestamp'] <= self.config.max_interpolation_seconds)
                    if gap == 1 and time_ok and delta > 0:
                        for checkpoint in self.crossings:
                            # Inclusive initial endpoint, each ID is recorded only once.
                            if checkpoint in track['checkpoints'] or not previous['position'] <= checkpoint <= position:
                                continue
                            fraction = (checkpoint-previous['position'])/delta
                            crossing_center = tuple(previous['center'][k]+fraction*(center[k]-previous['center'][k])
                                                    for k in (0, 1))
                            _, in_lane = self._position(crossing_center, shape)
                            if not in_lane:
                                continue
                            crossing_time = (previous['timestamp'] + fraction*(timestamp-previous['timestamp'])
                                if timestamp is not None and previous['timestamp'] is not None else None)
                            crossing = dict(checkpoint_percent=checkpoint, track_id=track_id,
                                crossing_frame=previous['frame']+fraction,
                                crossing_time=crossing_time, crossing_position=list(crossing_center))
                            self.crossings[checkpoint][track_id] = crossing
                            track['checkpoints'][checkpoint] = crossing
                            if checkpoint == 0:
                                track['entered'] = True
                track['last'] = current
                # A measured exit, lateral departure or confirmed disappearance
                # closes pending regional comparisons. Stopping alone never does.
                if previous and previous['inside'] and not inside:
                    track['terminal'] = True
                if inside:
                    track['terminal'] = False
                if track['lost']:
                    track['lost'] = False
                    self.events = [e for e in self.events if not (e['event_type'] == 'lost_track' and e['IDs'] == [track_id])]
            for track_id, track in self.tracks.items():
                if track_id in present or not track.get('last'):
                    continue
                last = track['last']
                if frame_index-last['frame'] > self.config.lost_buffer_frames:
                    track['terminal'] = True
                    if track['entered'] and last['inside'] and 100 not in track['checkpoints'] and not track['lost']:
                        track['lost'] = True
                        self._event('lost_track', [track_id], frame_index, last['position'],
                            f'Raw ID absent for more than {self.config.lost_buffer_frames} processed frames before exit.',
                            last_seen_frame=last['frame'])
            self.frames += 1
            self.last_frame = frame_index

    def _fragment_candidate(self, new_id, center, box, frame, position, present):
        candidates = []
        for old_id, old in self.tracks.items():
            last = old.get('last')
            if old_id == new_id or old_id in present or not last or not last['inside'] or old['fragmented_to'] is not None:
                continue
            gap = frame-last['frame']
            if not 0 < gap <= self.config.fragment_gap_frames:
                continue
            predicted = tuple(last['center'][k]+gap*old['velocity'][k] for k in (0, 1))
            scale = max(1, box[2]-box[0], box[3]-box[1],
                        last['box'][2]-last['box'][0], last['box'][3]-last['box'][1])
            distance = math.dist(center, predicted)/scale
            if distance <= 0.75:
                candidates.append((distance, old_id))
        candidates.sort()
        # Ambiguous nearby fruit cannot establish a correspondence.
        if candidates and (len(candidates) == 1 or candidates[1][0]-candidates[0][0] > 0.25):
            old_id = candidates[0][1]
            self.tracks[old_id]['fragmented_to'] = new_id
            self._event('id_fragmentation', [old_id, new_id], frame, position,
                        'Suspected fragmentation: a missing raw ID was replaced near its predicted centre.',
                        old_id=old_id, new_id=new_id)

    def snapshot(self):
        with self.lock:
            if self._cache is not None:
                return self._cache
            regions, derived = [], []
            points = list(self.crossings)
            for start, end in zip(points, points[1:]):
                a, b = self.crossings[start], self.crossings[end]
                common = set(a) & set(b)
                lost, new = sorted(set(a)-set(b)), sorted(set(b)-set(a))
                pending = [i for i in lost if not self.tracks[i]['terminal'] and
                           self.tracks[i]['last']['position'] < end]
                valid = self.config.region is not None and bool(a) and not pending
                continuity = 100*len(common)/len(a) if valid else None
                inversions = 0
                def ties(values):
                    return sum(n*(n-1)//2 for n in Counter(values).values())
                first_times = {i: round(a[i]['crossing_frame'], 9) for i in common}
                last_times = {i: round(b[i]['crossing_frame'], 9) for i in common}
                comparable = (len(common)*(len(common)-1)//2 - ties(first_times.values()) -
                              ties(last_times.values()) + ties((first_times[i], last_times[i]) for i in common))
                order = sorted(common, key=lambda i: (a[i]['crossing_frame'], i))
                # Enumerate actual inversions, not all O(n²) pairs on every poll.
                prior, group = [], []
                group_time = None
                for second in order:
                    if first_times[second] != group_time:
                        for item in group:
                            insort(prior, item)
                        group, group_time = [], first_times[second]
                    offset = bisect_right(prior, (last_times[second], math.inf))
                    for _, first in prior[offset:]:
                        inversions += 1
                        derived.append(dict(frame=max(b[first]['crossing_frame'], b[second]['crossing_frame']),
                            position_percent=end, event_type='possible_id_swap', IDs=[first, second],
                            description=f'Crossing order reversed between {start}% and {end}%.'))
                    group.append((last_times[second], second))
                if valid and lost:
                    derived.append(dict(frame=max(self.tracks[i]['last']['frame'] for i in lost),
                        position_percent=end, event_type='regional_continuity_drop', IDs=lost,
                        description=f'{start}% → {end}%: {len(common)} of {len(a)} raw IDs continued.'))
                regions.append(dict(region_start_percent=start, region_end_percent=end,
                    start_id_count=len(a), end_id_count=len(b), same_id_count=len(common),
                    continuity_percent=continuity,
                    order_consistency_percent=100*(1-inversions/comparable) if comparable else None,
                    possible_swap_count=inversions, lost_ids=lost, new_ids=new,
                    pending_ids=pending, evaluated=valid,
                    region_pass=(len(common) == len(a) and inversions == 0) if valid else None))
            events = sorted(self.events+derived, key=lambda e: (e['frame'], e['event_type'], e['IDs']))
            problems = {i: set() for i in self.tracks}
            for event in events:
                for track_id in event['IDs']:
                    problems[track_id].add(event['event_type'])
            rows = []
            for track_id, track in self.tracks.items():
                checkpoints = sorted(track['checkpoints'])
                coverage = sum(end-start for start, end in zip(points, points[1:])
                               if start in track['checkpoints'] and end in track['checkpoints'])
                complete = track['entered'] and len(checkpoints) == len(points)
                status = ('complete' if complete else 'lost' if track['lost'] else
                          'ended_incomplete' if track['terminal'] else 'unfinished')
                rows.append(dict(track_id=track_id, first_frame=track['first_frame'],
                    last_frame=track['last']['frame'], first_checkpoint=checkpoints[0] if checkpoints else None,
                    last_checkpoint=checkpoints[-1] if checkpoints else None,
                    region_coverage_percent=coverage if self.config.region else None,
                    frames_tracked=track['frames_tracked'], completed=complete, valid_entry=track['entered'],
                    status=status, problems=sorted(problems[track_id])))
            evaluated = [r for r in regions if r['evaluated']]
            worst = min(evaluated, key=lambda r: r['continuity_percent']) if evaluated else None
            entering = sum(t['valid_entry'] for t in rows)
            completed = sum(t['completed'] for t in rows)
            counts = {kind: sum(e['event_type'] == kind for e in events) for kind in
                      ('id_fragmentation', 'lost_track', 'mid_region_new_id', 'possible_id_swap')}
            coordinates = self.config.region or (None, None, None, None)
            summary = dict(run_id=self.job_id, tracker='TrackTrack', protocol_version=1,
                conveyor_direction=self.config.direction,
                region_left=coordinates[0], region_top=coordinates[1],
                region_right=coordinates[2], region_bottom=coordinates[3],
                checkpoint_interval_percent=self.config.checkpoint_interval_percent,
                lost_buffer_frames=self.config.lost_buffer_frames,
                total_unique_track_ids=len(rows), valid_entering_tracks=entering,
                completed_tracks=completed, id_continuity_percent=100*completed/entering if entering else None,
                mean_regional_continuity_percent=sum(r['continuity_percent'] for r in evaluated)/len(evaluated) if evaluated else None,
                minimum_regional_continuity_percent=worst['continuity_percent'] if worst else None,
                worst_region_start_percent=worst['region_start_percent'] if worst else None,
                worst_region_end_percent=worst['region_end_percent'] if worst else None,
                regional_pass_rate_percent=100*sum(r['region_pass'] for r in evaluated)/len(evaluated) if evaluated else None,
                valid_evaluated_regions=len(evaluated), id_fragmentations=counts['id_fragmentation'],
                lost_tracks=counts['lost_track'], mid_region_new_ids=counts['mid_region_new_id'],
                order_inversions=counts['possible_id_swap'],
                unfinished_entering_tracks=sum(t['valid_entry'] and t['status'] == 'unfinished' for t in rows),
                left_censored_or_late_ids=sum(not t['valid_entry'] for t in rows),
                frames_processed=self.frames, timed_frames=self.timed_frames,
                processing_seconds=self.processing_seconds,
                processing_fps=self.timed_frames/self.processing_seconds if self.processing_seconds > 0 else None,
                average_processing_time_ms=1000*self.processing_seconds/self.timed_frames if self.timed_frames else None,
                direction_warning=self.reverse_motion > self.forward_motion and self.reverse_motion >= 5,
                region_configured=self.config.region is not None)
            self._cache = dict(job_id=self.job_id, state=self.state, config=asdict(self.config),
                               summary=summary, regions=regions, events=events,
                               tracks=sorted(rows, key=lambda t: t['track_id']))
            return self._cache

    def finish(self, state='complete'):
        with self.lock:
            self.state = state
            self._cache = None
            if self._journal:
                self._journal.close()
                self._journal = None
            # Do not manufacture missing observations or age tracks at EOF.
            return self.save() if self.output else self.snapshot()

    def save(self):
        with self.lock:
            data = self.snapshot()
            if self.output is None:
                return data
            _atomic_json(self.output/'tracking_metrics.json', data)
            self._csv('tracking_summary.csv', list(data['summary']), [data['summary']])
            region_fields = ['region_start_percent', 'region_end_percent', 'start_id_count',
                'end_id_count', 'same_id_count', 'continuity_percent', 'order_consistency_percent',
                'possible_swap_count', 'lost_ids', 'new_ids', 'region_pass', 'evaluated', 'pending_ids']
            self._csv('region_continuity.csv', region_fields, data['regions'])
            self._csv('checkpoint_crossings.csv', ['checkpoint_percent', 'track_id',
                'crossing_frame', 'crossing_time', 'crossing_position'],
                [crossing for records in self.crossings.values() for crossing in records.values()])
            self._csv('tracking_events.csv', ['frame', 'position_percent', 'event_type', 'IDs', 'description'], data['events'])
            return data

    def _csv(self, name, fields, rows):
        temporary = self.output/(name+'.tmp')
        with temporary.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fields, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items() if k in fields})
        temporary.replace(self.output/name)


def replay_journal(path: Path, config: TrackingConfig, job_id=None, output=None):
    metrics = TrackingMetrics(config, job_id=job_id)
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            record = json.loads(line)
            metrics.observe(record['frame'], record['timestamp'], record['shape'],
                            record['ids'], record['boxes'], record.get('processing_seconds'))
    metrics.output = output
    if output:
        _atomic_json(output/'tracking_config.json', asdict(config))
    metrics.finish()
    return metrics
