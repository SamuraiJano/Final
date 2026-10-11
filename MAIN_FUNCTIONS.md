# Main Functions of the Inspection Pipeline

The application has two main parts: the Python algorithm performs the inspection, and React provides the controls and displays its results. This document groups the main runtime functions, with more detail on the algorithm.

The overall pipeline is:

**Video/camera → fruit detection → tracking and identity checks → usable fruit views → shape fitting → rotation estimation → view selection → defect segmentation → surface mapping → area measurement → grading → dashboard.**

## Algorithm Functions

Most of the reconstruction logic lives in [algorithm.py](backend/algorithm.py).

### 1. `analyze_video()` — Manage the Complete Recorded-Video Pipeline

Located in [main.py](backend/main.py), this is the main processing loop.

It opens the video, reads every frame, passes frames to `process_frame()`, reports progress, and finalizes fruit after they disappear beyond the tracking buffer. At the end of the video, it finalizes the remaining fruit.

It also checks whether image content has changed before capturing another mapping view. Tracking still runs on every frame; repeated images do not consume the capture budget.

**`_make_pipeline()`** constructs the detector, segmenter and `NaartjiePipeline`, and supplies the application's rotation, coverage and grading settings.

### 2. `DfineDetector.track()` — Find Fruit and Obtain Tracker IDs

Located in [dfine_segmenter.py](backend/dfine_segmenter.py).

It converts the frame into the detector's input format, runs D-FINE inference, and extracts bounding boxes, confidence scores and class labels. It then passes those detections to TrackTrack.

Its main supporting functions are:

| Function | Role |
|---|---|
| `make_fruit_tracker()` | Configures TrackTrack, including publishing an ID on the first accepted detection. |
| `suppress_duplicate_detections()` | Removes strongly overlapping detections of the same class, keeping the strongest prediction. |
| `associate_fruit_detections()` | Connects detections across frames and handles partially visible fruit entering or leaving the image. |

`associate_fruit_detections()` temporarily estimates larger bounding-box extents for clipped fruit to help association. It returns the actual detected boxes for capture.

**Why this matters:** every surface reconstruction needs an ordered collection of views belonging to one fruit.

### 3. `ConveyorIdentityManager.update()` — Check Continuity Before Grouping Views

Located in [conveyor_identity.py](backend/conveyor_identity.py).

This function sits between TrackTrack and the stored fruit views. It assigns the application's fruit IDs using the tracker observations plus motion and ordering evidence.

It predicts where existing fruit should appear, calculates association costs, and uses `linear_sum_assignment()` to obtain a one-to-one assignment. It then checks size changes, backward movement, competing associations and changes in local fruit order.

Important helpers are:

| Function | Role |
|---|---|
| `_time()` | Uses timestamps, with a frame-rate fallback, to calculate elapsed time. |
| `_velocity()` | Estimates fruit movement from recent accepted observations. |
| `_local()` | Determines whether two fruit are close enough for an ordering constraint. |
| `_order_pairs()` | Selects neighboring fruit whose order should persist. |
| `_order_conflict()` | Detects an unexpected reversal of that order. |

Clear motion continuity can reconnect a changed raw tracker ID. Ambiguous observations are separated and marked uncertain.

**Why this matters:** mixing views from different fruit would corrupt shape, rotation, defect measurements and grading.

`FruitIdentityGuard.update()` in [fruit_identity.py](backend/fruit_identity.py) remains the alternative implementation when conveyor identity validation is disabled.

### 4. `NaartjiePipeline.process_frame()` — Connect Detection, Identity and Capture

This is the main per-frame coordinator inside `algorithm.py`.

It calls the detector, keeps the configured fruit class, runs identity validation, records each accepted observation, and attempts to capture usable views.

Two functions carry out the capture work:

- **`record_tracked_detection()`** records the fruit's bounding box and frame number, plus entry and last-seen images. It runs before the mapping checks, so partially visible fruit still have tracking records.
- **`add_tracked_detection()`** creates a padded crop, extracts its fruit mask, validates the silhouette, and stores a `FruitView`. It also enforces capture spacing and the maximum number of views.

**Why this matters:** being tracked successfully and being suitable for reconstruction are separate decisions.

### 5. `_grabcut()` and `_validate_capture_mask()` — Isolate Usable Fruit Silhouettes

`_grabcut()` uses OpenCV GrabCut to separate the fruit from the background. For larger crops, it estimates the mask at a smaller resolution and restores it to the original size.

Supporting functions:

| Function | Role |
|---|---|
| `_largest_component()` | Keeps the largest connected foreground region and rejects empty or very small foregrounds. |
| `_binary()` | Converts a supplied mask into a binary mask and checks its dimensions. |
| `_validate_capture_mask()` | Rejects collapsed masks, insufficient foreground and strongly irregular or concave silhouettes. |
| `_prepare()` | Validates the complete view collection, prepares fruit masks, and clips defect masks to the fruit. |

**The fruit silhouette mask describes the whole fruit. Defect masks describe damaged regions within it.** GrabCut supplies the former.

### 6. `_ellipse()` and `fit_spheroid()` — Estimate the Fruit's Geometry

`_ellipse()` calculates the center and covariance of the foreground pixels. Its eigenvalues and eigenvectors provide the ellipse's major and minor semi-axes and their directions.

`fit_spheroid()` combines those measurements across views to construct a shared three-dimensional shape:

- A **sphere** when configured explicitly, or when `auto` identifies a sufficiently round fruit.
- An **oblate spheroid**, representing a flattened sphere, otherwise.

For the oblate model, the equatorial radius comes from the mean major semi-axis, and the pole radius comes from the smallest minor semi-axis.

**`_oblate_poles()`** estimates the symmetry-axis orientation in each view from the ellipse geometry and its variation through the sequence. **`_constrained_oblate_poles()`** supplies an optional alternative pose calculation.

**`_height()`** then solves the fitted surface equation to obtain the visible depth coordinate for an image location:

`image point (x, y) → surface point (x, y, z)`

**Why this matters:** the rotation estimator needs points on a three-dimensional fruit surface, and the mapper needs that surface to calculate area.

### 7. `_preprocess()` and `_relevant()` — Identify Measurable Texture

`_preprocess()` extracts the green channel, resizes it according to the matching settings, and produces a high-pass image by subtracting a blurred version. This emphasizes local texture.

`_relevant()` selects strong texture points within the central fruit region, checks that enough measurable texture exists, and uses `_height()` to lift those points onto the fitted surface.

**Why this matters:** rotation is estimated by following surface appearance between views. Weak texture, silhouettes and reflections can make that measurement unavailable or misleading.

### 8. `_search_rotation()` and `estimate_rotation()` — Measure Movement Between Views

These are central to the reconstruction.

**`_search_rotation()`** tries candidate rotations around the configured rolling axis, with a bounded sideways component. For each candidate, it:

1. Rotates the source's three-dimensional texture points.
2. Projects them into the target image.
3. Checks visibility and the target fruit mask.
4. Compares the source and target appearance.
5. Chooses the lowest-cost candidate and refines the estimate.

The comparison functions are:

| Function | Role |
|---|---|
| `_cost()` | Evaluates one candidate rotation. |
| `_cost_many()` | Evaluates multiple candidates in a batch using the same objective. |
| `_surface_patches()` | Builds small neighborhoods on the fitted fruit surface. |
| `_patch_response()` | Samples those neighborhoods, removes local brightness trends, and normalizes contrast. |
| `_descriptor_cost_many()` | Compares the resulting nine-sample neighborhood patterns. |

**`estimate_rotation()`** controls the matching strategy. It first attempts the coarse measurement, then rechecks qualifying small movements at the original image resolution.

In the current app configuration, the native comparison uses:

- Smoothed green values when predicted rolling displacement is below one pixel.
- Surface-aligned local log patterns when displacement reaches at least one pixel.

For a failed coarse match in the dense recorded-video configuration, it can also attempt a bounded three-component native rotation. That retry requires independently measured forward and backward rotations to agree.

**Output:** a rotation matrix and matching residual. Unacceptable measurements raise `MappingError`.

### 9. `_select_rotating_views()` and `_map_trajectory()` — Choose a Usable Sequence

`_select_rotating_views()` measures adjacent captured views and splits the sequence when a transition is missing, unreliable or too small to observe. It also splits sequences whose mapped longitude progression falls outside the permitted bounds.

It chooses the valid connected sequence with the largest measured longitude span.

Its supporting functions are:

| Function | Role |
|---|---|
| `_subset_spheroid()` | Keeps the geometry and poses associated with a selected set of views. |
| `_map_frame()` | Chooses the fruit coordinate frame and matching radius arrangement for mapping. |
| `_map_trajectory()` | Accumulates measured rotations and calculates each view's longitude in common fruit coordinates. |

The orientation propagation is:

`next orientation = measured rotation × previous orientation`

**Why this matters:** the views must progress consistently around the same surface before they can be combined.

### 10. `DfineSegmenter.predict()` and `_segment_defects()` — Identify Defect Regions

`DfineSegmenter.predict()` runs the trained segmentation model and returns instance masks, labels and confidence scores.

`NaartjiePipeline._segment_defects()` masks out the background before inference, converts predictions into binary masks, groups instances by defect category, and clips them to the fruit silhouette.

The configured categories are skin wrinkling, dark marking, wind scarring, light brown discolouration and open skin.

**In the current application, segmentation is deferred until the usable rotating sequence has been selected.** The model therefore runs on the selected views used for reconstruction.

### 11. `build_surface_map()` and `_sample_view()` — Construct the Unified Map

`build_surface_map()` is the main reconstruction function. It coordinates preparation, shape fitting, rotation estimation, view selection, defect prediction, fusion and grading.

It creates a latitude–longitude grid on the fitted fruit surface. For each grid location, it projects the surface point into nearby selected views.

**`_sample_view()`** retrieves the image color and defect labels while checking that the point faces the camera, lies inside the image, and belongs to the fruit mask.

The mapper blends valid colors and combines defect masks. Unobserved regions remain marked unknown.

It then weights map locations by the spheroid's surface-area formula. Flat map pixels represent different physical areas at different latitudes.

The main measurements are:

`Observed coverage = observed surface area / full modeled surface area × 100`

`Defect percentage = observed defect area / observed surface area × 100`

Overlapping defect categories form a union for the total defect calculation, so the same surface location is counted once.

### 12. `_grade()`, `_grade_map()` and `finish_track()` — Produce the Final Decision

`_grade()` validates the observed area and defect percentage, then applies the configured boundaries:

| Predicted defect percentage of observed surface | Grade |
|---|---|
| Below 10% | Class 1 |
| 10% through 20% | Class 2 |
| Above 20% | Class 3 |

`_grade_map()` additionally checks longitude coverage, rotation coverage and excessive pair gaps.

The current application uses **80% observed surface and 350° observed longitude** as coverage requirements. Usable maps below those requirements can receive a provisional partial grade.

`NaartjiePipeline.finish_track()` calls the reconstruction for one completed fruit, withholds its grade if identity is uncertain, and releases its stored views after success.

The output is a `MapResult` containing the textured map, observed mask, defect maps, rotations, residuals, coverage, grade and status.

## React Application Functions

The interface is primarily in [App.jsx](src/App.jsx). These functions manage interaction, requests and presentation.

| Function/component | Responsibility |
|---|---|
| `App()` | Holds dashboard, upload, camera, progress, filtering and selected-fruit state; renders the main interface. |
| `getJson()` | Fetches JSON and checks HTTP success. |
| `refreshDashboard()` | Loads saved inspection results from `/api/dashboard`. |
| `chooseFile()` | Stores the selected video and creates its local preview URL. |
| `analyze()` | Uploads the video, assigns a request ID, handles completion/errors, and refreshes the results. |
| `stopAnalysis()` | Requests cancellation of the active analysis using its request ID. |
| `changeLive()` | Starts or stops live inspection. |
| `refreshBackend()` | Requests a managed backend restart and reloads status information. |
| `refreshStatus()` | Polls backend health, camera connection, live inspection and backend-control status. |
| `refreshProgress()` | Polls analysis state and frame progress. |
| `FruitDetail()` | Displays an individual inspection, map views, masks, coverage, tracking evidence and report download. |
| `MetricCard()` | Displays summary figures. |
| `ModelRow()` | Displays model latency, prediction counts and confidence. |
| `gradeText()` / `gradeClass()` | Format the supplied grade, partial status and review styling. |
| `formatNumber()`, `formatPercent()`, `formatTime()` | Format values for display. |
| `Icon()` | Renders interface icons. |

The `useEffect()` calls schedule polling and clean up timers, keyboard listeners and preview URLs. Search, grade filtering, run selection and pagination are calculated inside `App()`.

### Backend Functions Supporting React

React also depends on these application-side Python functions in [main.py](backend/main.py):

| Function | Responsibility |
|---|---|
| `analyze_upload()` | Accepts the video upload, invokes `analyze_video()`, and saves the completed report. |
| `_finish_track()` / `_write_track_result()` | Save each fruit's maps, masks, tracking information and result metadata. |
| `_write_report()` | Writes the report through a temporary file before replacing the saved report. |
| `dashboard()` | Loads saved reports and returns dashboard records and totals. |
| `analysis_status()` / `stop_analysis()` | Expose progress and cancellation controls. |
| `CameraFeed.start()`, `_capture()`, `stream()` | Acquire camera frames and supply the preview stream. |
| `LiveInspector.start()`, `_run()`, `stop()` | Run the same inspection pipeline on the camera feed. |

Finally, `render_defect_overlay()` in [map_visualization.py](backend/map_visualization.py) creates the colored defect display shown by React. The measured coverage and grade come from the reconstruction and area calculations; the overlay provides their visual presentation.
