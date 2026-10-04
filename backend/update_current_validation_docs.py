"""Write the documented source50 checkpoint; retain the earlier dated log."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

README_SECTION = """## Validation evidence: current checkpoint, 3 October 2026

The adopted algorithm is frozen as source `50bdd78e` (full SHA256 in its
[source record](backend/diagnostics/algorithm-revision/aligned_pixel_switch_trace_source/metadata.json)).
Its controlled motion tests and isolated model integration pass, but the full
515-frame original-video API test failed at **330/515 frames** with a NumPy memory
allocation error. **Complete conveyor operation was not verified by midnight.**
The [failed-run evidence](backend/diagnostics/api-runs/full_pixel_switch_trace_failure_capture_20261003/README.md)
preserves the request, HTTP 500 response, error state, tracebacks, exact execution
sources and partial outputs. A healthy API response does not mean that analysis
completed. Runtime recovery needs a separately recorded replay.

Testing is paused at the user's request until model training finishes. The owned
API and dashboard services were stopped at 01:05:09 SAST to free RAM/GPU; the
user's training was left running. [Pause evidence](backend/diagnostics/algorithm-revision/service_20261002/pixel_switch_trace_services/paused_for_training_20261003.json)
records the stopped processes. Sources, report images and failures remain saved.

The algorithm retains the papers' spheroid geometry, lifted surface points,
two-axis rotation search and surface fusion. For rechecked adjacent turns it
uses a local log-pattern comparison when predicted texture displacement is at
least one pixel; smaller displacements use smoothed native green values. This
choice handles the tested camera lighting while retaining small-motion detail.
The current recorded-video bounds are 20 degrees rolling and 20 degrees sideways;
live/author rolling search is 55 degrees. Coverage and class thresholds remain
65% observed surface, 350 degrees observed longitude, and 10%/20% defect limits.
The [plain-language walkthrough](backend/ALGORITHM_EXPLAINED.md) explains the
pipeline and these engineering adaptations.

The exact adopted source passes all twelve
[camera-lighting controls](backend/diagnostics/algorithm-revision/camera_shading_pixel_switch_trace20_20261002/report.json),
the [short-motion and brightness-offset controls](backend/diagnostics/algorithm-revision/short_pixel_switch_trace20_20261002/report.json),
four [strict large-sideways pairs at the 20-degree bound](backend/diagnostics/algorithm-revision/large_transverse_pixel_switch_trace20_20261002/report.json),
two [fresh-texture turns](backend/diagnostics/algorithm-revision/fresh_texture_pixel_switch_trace20_20261002/report.json),
two [complete vertical-axis turns](backend/diagnostics/algorithm-revision/full_turn_y_pixel_switch_trace20_20261002/report.json),
and [numerical equivalence checks](backend/diagnostics/algorithm-revision/pixel_switch_trace_equivalence_20261002/report.json).
All 714 noisy stationary pairs remain unavailable and produce no map or grade;
this is the expected observability result, not measured zero motion error.
Inputs, criteria, failed predecessors and actual misleading maps are preserved.
These repeatedly inspected synthetic scenes are development tests.

On [all 36 public author sequences and 497 labels](backend/diagnostics/authors-benchmark/runs/pixel_switch_trace_author_profile_20261002/report.json),
the adopted source produces 36 maps and returns 457 point predictions, with
5.225-pixel conditional RMS error; 372 of all 497 labels are within five pixels.
The earlier operational reference returned 458 at 5.103 pixels, with 367 within
five pixels. There is no overall author-accuracy improvement claim. The
[same-label comparison](backend/diagnostics/algorithm-revision/pixel_switch_author_comparison_20261002/SAME_LABEL_COMPARISON.md)
retains gains, regressions and unavailable predictions. The
[retained-map subset](backend/diagnostics/authors-benchmark/bridge_runs/retained_pixel_switch_trace_author_20261002/report.json)
returns 348/497 at 5.360 pixels, with 286/497 within five pixels and no
nonadjacent bridges. A 39.56-pixel worst returned error remains documented.
Map availability alone does not establish correct pose.

The [actual GPU model integration](backend/diagnostics/algorithm-revision/real_segmenter_pixel_switch_trace20_20261002/report.json)
uses 215 frozen detector/tracker crops and fruit masks. It performs 42 actual
segmentation calls, returning 80 instances. Fruit 98 reaches 360 degrees observed
longitude and 85.074% observed surface; predicted defects cover 4.544% of observed
surface and the configured arithmetic assigns Class 1. Three other examples
remain partial. This isolated replay repeats no detector inference and has no
human pose, defect or grade truth. All 43 Python tests, frontend build and lint
pass in the [software record](backend/diagnostics/software-checks/pixel_switch_trace20_final_20261002/summary.json);
two preceding failed check attempts are retained separately.

The dashboard defaults to the latest saved report. **All saved runs** includes
earlier development results. The screenshot's 711 Review records match the
138 + 171 + 402 records in the earliest saved reports; association with that
screenshot is an inference because it shows no report IDs. The
[history and display audit](backend/diagnostics/ui-checks/dashboard_scope_20261002/README.md)
separates actual saved reports from artificial UI fixtures. Existing-history
screenshots taken before the new run finished are not evidence of grading by
the adopted algorithm.

Earlier source `951b55` passed some controls but failed later horizontal turns.
Its native20 setting and subsequent plane/pattern candidates also had documented
motion, author-availability or stationary failures. Those historical profiles
are not the current validated control configuration. See the
[continued-testing report](backend/diagnostics/algorithm-revision/development_followup_20261002/DEVELOPMENT_TEST_REPORT.md),
[failure-image gallery](backend/diagnostics/algorithm-revision/development_followup_20261002/index.html)
and [development log](backend/diagnostics/authors-benchmark/DEVELOPMENT_LOG.md).
The earlier `full_observable_20261002` video completed with 474 records, 7 graded
and 467 Review, using a matcher later found to fail known-turn controls.
`full_hybrid_wobble_20261002` remained incomplete after a service interruption
of unconfirmed cause. Neither supplies a completed full-video result for source50.

The authors' repositories supplied images and annotations; no reusable
reconstruction implementation was found in the inspected repositories. This is
an independent implementation tested against published labels and controlled
geometry. Author-label error, model execution, coverage arithmetic and complete
video execution are different measurements. Reliable field grading and real-time
throughput remain unverified. Original evidence packs and failed trials remain
intact; the final current-source pack awaits the separately documented runtime
recovery outcome.

"""

LATEST = """## Latest checkpoint, 3 October 2026, 01:05 SAST

The production matcher is source `50bdd78eafcc5581d0368353c9996c2f95823c69f734dac6f778dc82f22c815d`.
Its declared exact-input motion controls, numerical checks, isolated real-model
integration and 43-test/build/lint suite pass. **The full original-video API
attempt failed with a memory allocation error at the last published progress
330/515; complete conveyor operation was not verified by the midnight target.**
The API remained alive with health 200 and analysis state error. The error is a
runtime failure, separate from controlled motion accuracy. No completed aggregate
report exists; 256 saved partial track JSON files cannot establish full execution.
The failed request, raw response, tracebacks, state, snapshots, file times and
partial-job SHA256 inventory are preserved in
`../api-runs/full_pixel_switch_trace_failure_capture_20261003`.
Exact server failure time is unavailable; capture and last-write times are explicit
proxies. Earlier entries below record historical checkpoints, not current status.
The latest deadline was midnight at the end of 2 October (3 October 00:00 SAST).
At the user's explicit request, testing is paused until model training finishes.
The owned API/dashboard processes stopped at 01:05:09 SAST; user training remains
untouched. No algorithm changes were made during the memory audit. The stopped
processes are recorded in `../algorithm-revision/service_20261002/pixel_switch_trace_services/paused_for_training_20261003.json`.

"""

APPEND = """
## Adopted pixel-displacement matcher and failed full replay, 2-3 October 2026

The final tested motion source is
`50bdd78eafcc5581d0368353c9996c2f95823c69f734dac6f778dc82f22c815d`,
frozen in `../algorithm-revision/aligned_pixel_switch_trace_source` and adopted
in production with main.py source
`2a51490a827c7429114ec51d0e8b627f30a9be069dd7d5769af283780ae50d49`.
It retains fitted spheroids, lifted high-pass surface points, a coarse two-axis
MAD search, connected adjacent-view selection and map fusion. Rechecking chooses
smoothed green MAD for a predicted rolling pixel chord below one pixel and the
aligned local log-pattern objective otherwise. The criterion uses the fitted
radius and the recorded coarse angle; no hidden fruit-speed prior is supplied.
Recorded-video rolling search is 20 degrees; live/author rolling search remains
55 degrees. Native recheck and transverse bounds are 20 degrees, maximum pair gap
55 degrees. Surface/longitude thresholds remain 65%/350 degrees and defect class
limits remain 10%/20%. These changes are engineering adaptations, not author code.

Several later candidates still failed the unchanged twelve lighting scenes.
Source 6f2c's detrended pattern and unblurred c5c7/log-blurred 1cfb variants retain
curved-lighting failures. Unblurred log-detrended source25d1 returned false motion
on stationary inputs, with 117/0/119/27 returned pairs across the four scenes.
Its moving-scene successes do not cancel this stationary failure. The pixel-switch
predecessor d570 was tested separately; none of its tests is relabelled as source50.
Final source50 reruns use the same frozen inputs and thresholds. Original source
snapshots, reports and rendered map pixels remain under their uniquely named runs.

Source50 completes all twelve camera-fixed lighting scenes at 20:41:04 SAST:
four full turns, four short noncommuting chains and four 120-frame stationary
sequences. All declared criteria pass. A separate short-motion suite passes both
moving sequences, both stationary sequences and both exposure-offset controls.
All 476 + 238 stationary pairs remain unavailable with no map or grade; their
reference-scaffold zero maxima are not measured zero-error predictions. All four
known +/-13-degree sideways pairs pass the strict 1-degree/1-pixel criteria at
the selected transverse bound20. Bound10 alternatives in the same report are
comparison history and are not assigned to the adopted profile. Fresh texture C's
two lighting full turns and both ideal complete vertical-axis turns pass. Numerical
equivalence passes. All results identify the exact source50 hash and recorded
dataset parameters. These reused scenes are development controls, not held-out
field evaluation.

The source50 author benchmark covers all 36 sequences and all 497 published
correspondences. It creates 36 maps, returns 457 labels at conditional RMS
5.224578716 pixels, with 372/497 within five pixels. The earlier operational
reference returns 458 at 5.102881442 pixels, 367/497 within five pixels. On their
450 common predictions RMS changes 4.912064264 to 4.887740347: 124 improve,
99 worsen, 227 are unchanged; seven predictions become available, eight are lost
and 32 are unavailable in both. Overall improvement is not claimed. The retained
surface-map subset returns 348/497 at 5.359672789 pixels, 286/497 within five,
with no nonadjacent bridges. The worst returned actual label remains mandarin
obj0004 line61, frames6 to5, at 39.559957711 pixels. Exact original annotated
frames and prediction overlays are preserved.

On four fixed conveyor examples, source50 geometry reaches 360-degree observed
longitude and 85.073593% surface on track98; three others remain partial. Missing
defect observations prevent grading in the geometry-only run. The isolated GPU
integration uses all 215 frozen crops/masks and the unchanged real weights,
performing 42 segmenter calls and returning 80 instances (104.8 ms mean call time,
0.492 mean confidence). Its track98 predicts 4.544026% defects on observed surface
and produces Class1 arithmetic. The other three tracks remain partial. No new
detector/tracker execution occurs in that isolated test. Human pose/mask/grade
truth is absent, so execution, coverage and grade output are not grading accuracy.

Software `pixel_switch_trace20_final_20261002` passes all 43 Python tests, build
and lint. Earlier `pixel_switch_trace20_20261002` fails seven mocks because they
supplied model=None where the new criterion needs the fitted radius. The fixture
repair supplies a fitted model without relaxing assertions. The subsequent
`pixel_switch_trace20_fixed_checks_20261002` lint failure came from preserved
minified UI artifacts being scanned; generated evidence directories are now
ignored. Both failed attempts remain intact rather than being called passes.

The full original 515-frame input, SHA256
`dc25964bf6052972cad761b0246f79906e768c6737bf4228ba44711d7272429c`, was
submitted to POST /api/analyze-video at 20:51:37.951279 SAST, run ID
`a43e26c70871450d8b72a5c291074b0c`, label `full_pixel_switch_trace_20261002`.
Its source50 job `78b4a03ccaa549de96ecd88c5efb5806` fails while finalizing a track
in `_patch_response`, with NumPy unable to allocate 1.26 MiB for shape
(115,160,9), float64. HTTP500 and the validator HTTPError traceback are retained.
The validator did not write summary.json because raise_for_status occurred after
saving the raw response and outside its transport-exception capture. A separate
failure freeze observes health200 and matching analysis state error at 330/515
around 01:02 SAST on3October. The API does not record exact failure time. Original
file last-write and capture times are labelled proxies. The full-video verification
deadline was not met. The error concerns runtime memory, not the motion scoring
criteria. No completed report exists; all256 partial result JSON files, job/service
source snapshots and the complete partial file inventory are preserved. Runtime
changes and any later replay require separate provenance and a new run label.

Dashboard scope evidence independently verifies latest-run display, history totals
and grade filtering. Mocked screenshots in `../ui-checks/dashboard_scope_20261002`
are captioned artificial UI controls only. Real running-service screenshots in
`../algorithm-revision/service_20261002/pixel_switch_trace_services` show earlier
saved history while the new analysis was running; they do not show current-source
grading. The screenshot's711Review count matches138+171+402 older records as an
explicit inference because the screenshot carries no report IDs. Saved development
reports are retained rather than deleted to change displayed totals.

The fresh `evidence_pixel_switch_trace_20261002` package is configured but not
sealed at this checkpoint. It must retain this failed full replay and separately
name any runtime recovery and subsequent outcome. Earlier sealed evidence remains
unchanged. Final report-grade figures must distinguish actual author annotations,
controlled synthetic images, actual model predictions, tracking donors and UI
fixtures, and retain both successful and failed cases.

At the user's explicit request, further testing and evidence generation are paused
pending model-training completion. The owned API wrapper/worker (45580/31488) and
Node/Vite (5740/39568) stopped at 01:05:09 SAST on3October to free RAM/GPU. User
training was untouched. The pause metadata is
`../algorithm-revision/service_20261002/pixel_switch_trace_services/paused_for_training_20261003.json`.
No production source changed during the memory audit; source50/main2a remain
frozen. Resume requires training completion, restarted services and a new uniquely
labelled full-video replay. Report images and all failed data remain preserved.
"""


def main():
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    start = text.index("## Validation evidence")
    end = text.index("Run the existing algorithm checks with:", start)
    path.write_text(text[:start] + README_SECTION + text[end:], encoding="utf-8")
    path = ROOT / "backend/diagnostics/authors-benchmark/DEVELOPMENT_LOG.md"
    text = path.read_text(encoding="utf-8")
    marker = "## 1 October 2026, 19:40"
    start = text.index(marker)
    if "## Latest checkpoint, 3 October 2026" not in text:
        text = text[:start] + LATEST + text[start:]
    if "## Adopted pixel-displacement matcher and failed full replay" not in text:
        text += APPEND
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
