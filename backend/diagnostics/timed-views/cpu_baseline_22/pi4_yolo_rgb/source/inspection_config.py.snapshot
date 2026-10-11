"""Versioned inspection choices; callers retain immutable entry snapshots."""
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
import json
import math
import threading


@dataclass(frozen=True)
class NineViewSettings:
    region: tuple | None = None
    acquisition: str = 'progress_bins'
    required_views: int = 9
    snapshot_interval_seconds: float = .4
    first_snapshot_delay_seconds: float = 0.
    snapshot_lateness_seconds: float = .15
    timing_calibration_id: str = 'not_calibrated'
    minimum_stream_change: float = 1.5
    conveyor_stop_grace_seconds: float = .35
    direction: str = 'top_to_bottom'
    minimum_crop_pixels: int = 24
    minimum_blur_variance: float = 10.
    maximum_glare_fraction: float = .25
    maximum_occlusion_fraction: float = .20
    minimum_mask_box_fraction: float = .40
    minimum_instance_confidence: float = .50
    minimum_defect_pixels: int = 3
    class_1_max_defect_pct: float = 10.
    class_2_max_defect_pct: float = 20.
    calibration_status: str = 'experimental'
    calibration_id: str = 'transferred_surface_10_20_unvalidated'
    decision_deadline_seconds: float = 5.
    maximum_dwell_seconds: float = 12.
    track_loss_seconds: float = 1.
    expected_dwell_seconds: float | None = None
    expected_fruit_rate: float | None = None
    contact_sheet: bool = True
    evidence_level: str = 'full'

    def __post_init__(self):
        if self.acquisition not in ('progress_bins', 'timed'):
            raise ValueError('Acquisition must be progress_bins or timed')
        if type(self.required_views) is not int or not 4 <= self.required_views <= 9:
            raise ValueError('required_views must be an integer from 4 to 9')
        if not math.isfinite(self.snapshot_interval_seconds) or self.snapshot_interval_seconds <= 0:
            raise ValueError('Snapshot interval must be finite and positive')
        for name in ('first_snapshot_delay_seconds', 'snapshot_lateness_seconds'):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        if self.snapshot_lateness_seconds >= self.snapshot_interval_seconds:
            raise ValueError('Snapshot lateness must be less than the interval')
        if not isinstance(self.timing_calibration_id, str) or not self.timing_calibration_id.strip():
            raise ValueError('Timing calibration identifier is required')
        for name in ('minimum_stream_change', 'conveyor_stop_grace_seconds'):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        if self.direction not in ('top_to_bottom', 'bottom_to_top', 'left_to_right', 'right_to_left'):
            raise ValueError('Invalid inspection direction')
        if self.region is not None:
            if len(self.region) != 4 or not all(math.isfinite(v) for v in self.region):
                raise ValueError('Inspection region needs four finite normalized coordinates')
            l, t, r, b = self.region
            if not 0 <= l < r <= 1 or not 0 <= t < b <= 1:
                raise ValueError('Inspection region must lie within the camera image')
            object.__setattr__(self, 'region', tuple(self.region))
        for name in ('minimum_crop_pixels', 'minimum_defect_pixels'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f'{name} must be a positive integer')
        for name in ('maximum_glare_fraction', 'maximum_occlusion_fraction',
                     'minimum_mask_box_fraction', 'minimum_instance_confidence'):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f'{name} must be within [0,1]')
        if not math.isfinite(self.minimum_blur_variance) or self.minimum_blur_variance < 0:
            raise ValueError('Blur variance must be nonnegative')
        if not 0 <= self.class_1_max_defect_pct < self.class_2_max_defect_pct <= 100:
            raise ValueError('Defect thresholds must increase within [0,100]')
        for name in ('decision_deadline_seconds', 'maximum_dwell_seconds', 'track_loss_seconds',
                     'expected_dwell_seconds', 'expected_fruit_rate'):
            value = getattr(self, name)
            if value is None and name not in ('expected_dwell_seconds', 'expected_fruit_rate'):
                raise ValueError(f'{name} is required')
            if value is not None and (isinstance(value, bool) or not math.isfinite(value) or value <= 0):
                raise ValueError(f'{name} must be a finite positive duration/rate')
        if self.calibration_status not in ('experimental', 'validated') or not isinstance(self.calibration_id, str) or not self.calibration_id.strip():
            raise ValueError('A calibration status and record identifier are required')
        if self.calibration_status == 'validated' and self.calibration_id == 'transferred_surface_10_20_unvalidated':
            raise ValueError('Transferred thresholds cannot be marked validated')
        if type(self.contact_sheet) is not bool:
            raise ValueError('contact_sheet must be boolean')
        if self.evidence_level not in ('full', 'contact_sheet'):
            raise ValueError('evidence_level must be full or contact_sheet')


@dataclass(frozen=True)
class InspectionSettings:
    version: int = 1
    algorithm: str = 'surface_mapping'
    nine_view: NineViewSettings = field(default_factory=NineViewSettings)

    def __post_init__(self):
        if self.algorithm not in ('surface_mapping', 'nine_view'):
            raise ValueError('Algorithm must be surface_mapping or nine_view')
        if type(self.version) is not int or self.version < 1:
            raise ValueError('Configuration version must be positive')


class InspectionConfiguration:
    def __init__(self, path: Path | None = None):
        self.path, self.lock = path, threading.RLock()
        self.current = InspectionSettings()
        if path is not None and path.is_file():
            data = json.loads(path.read_text(encoding='utf-8'))
            self.current = InspectionSettings(version=data.get('version', 1),
                algorithm=data.get('algorithm', 'surface_mapping'), nine_view=NineViewSettings(**data.get('nine_view', {})))

    def snapshot(self, tracking=None):
        with self.lock:
            result = self.current
        # Reuse the operator's existing region only at fruit entry.
        if tracking is not None and result.nine_view.region is None and tracking.region is not None:
            result = replace(result, nine_view=replace(result.nine_view, region=tracking.region,
                                                     direction=tracking.direction))
        return result

    def update(self, patch):
        if not isinstance(patch, dict) or set(patch) - {'algorithm', 'nine_view', 'expected_version'}:
            raise ValueError('Invalid inspection configuration fields')
        with self.lock:
            if patch.get('expected_version', self.current.version) != self.current.version:
                raise ValueError('Inspection configuration changed; refresh and retry')
            nine = {**asdict(self.current.nine_view), **patch.get('nine_view', {})}
            new = InspectionSettings(self.current.version + 1, patch.get('algorithm', self.current.algorithm),
                                     NineViewSettings(**nine))
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps(asdict(new), indent=2, allow_nan=False), encoding='utf-8')
                temporary.replace(self.path)
            self.current = new
            return new
