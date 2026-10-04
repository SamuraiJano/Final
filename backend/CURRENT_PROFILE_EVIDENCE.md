# Building evidence for the final selected profile

`build_current_profile_evidence.py` requires an explicit configuration after the
source and parameters are settled. It does not run inference and it never
overwrites an existing evidence directory. The example JSON deliberately has
unfilled values and cannot declare an algorithm validated.

Copy `current_profile_evidence.example.json` to a new configuration. Set a fresh
output label, the exact frozen algorithm source and its SHA256, the four matcher
parameters, and each completed report path. Primary reports must execute that
source. Set `primary: false` only for clearly described comparison history.

Report roles are `shading`, `motion`, `full_turn`, `fresh_texture`, `author`,
`retained_author`, `author_comparison`, `large_transverse`, `fixed`, `model`,
`software`, `area` and `api`. Primary report settings inherit
`profile_settings`. An explicit `settings_expected` can record a different
dataset profile, such as the author rolling direction or a wider author search;
explain that difference in the report's `scope`. Author entries specify their
actual sequence and label counts, so a mandarin-only test cannot silently become
an all-fruit benchmark. Incomplete lighting suites cannot be sealed.
For a report comparing transverse bounds 10 and 20, set `bounds: [20]` when
scoring the selected twenty-degree profile. Both original bounds remain in its
copied report; the ten-degree alternative is not assigned to the chosen profile.

The script preserves source/report hashes, original reports and images, frozen
scripts, masks and NPZ inputs. Identical NPZ files are stored once, with aliases.
It freezes input directories referenced by lighting runs and model fixtures,
checks their recorded hashes, and verifies author data against its original
source manifest. Model checkpoints stay in their existing locations.

The figures export at 300 dpi as PNG and PDF. The author figure uses the worst
returned labelled point on its unchanged original source and target frames.
Real-fruit figures require a current-source model run and an explicitly named
tracking donor with its own source hash. They show actual entry/exit crops,
selected views, model overlays, maps and observed cells. Tracking donor frames
are separate evidence when they come from an earlier algorithm run.

`PASS`, `FAIL` and `UNAVAILABLE` retain their stated scope. Stationary reference
zeros are not measured zero-error motion. The fixed real inputs and author
accuracy have no field acceptance truth; their observed results remain reported
without inventing a passing accuracy threshold. Supplied all-clear masks test
class arithmetic separately from pose accuracy and neural segmentation.

Optional `supplementary_collections` entries use `name`, `path` and `scope`. They
are copied as supporting evidence, never counted as current algorithm validation
or used automatically in real-model figures. Caption mocked `*_fixture.png`
dashboard screenshots only as UI/filter tests.

```powershell
./backend/venv/Scripts/python.exe -B backend/build_current_profile_evidence.py --config backend/<selected_configuration.json>
```

The fresh pack contains its configuration, report, gallery, source records, input
hashes, figure provenance, checks, SHA256 manifest and a CRC-checked ZIP. Read the
report and visually inspect the generated figures before reporting an outcome.

Before a long API replay finishes, a report can be marked `awaited: true` in the
configuration. `--preflight` verifies available report sources, settings, referenced
inputs and workspace hashes, then lists missing awaited reports. It creates no
evidence directory, figures or ZIP. Building always requires those reports to
exist; a primary API row must have a successful complete response and the job's
aggregate report. Set `frames: 515` to verify that the complete original clip was
processed, and `runtime_main_sha256` to pin the replay's API implementation.

`workspace_files` entries freeze project documentation and code inside this
workspace. Pin source files with `sha256`; documentation may be copied at its
final reviewed content. A model/software descriptor's `main_sha256` pins its own
execution separately from older source50 tests. Historical API failures are
`primary: false` and retain FAIL for runtime execution; an allocation failure is
not a synthetic motion-error measurement.

`api_examples` select a track from a completed primary API job, with optional
`expected_frames` for entry/last-seen/selected-image checks. They preserve the
actual track JSON and images, separate from `real_examples` using frozen-crop
model replay and historical tracking donors. The complete report includes status
and Review-reason counts per saved track, capture-rejection counts per attempted
view, and motion statuses per pair event. These denominators are not interchangeable.
Original-video hashes, API response/aggregate equality, model source snapshots and
runtime main pins are checked before building.

After building, `validate_current_profile_evidence.py --label <label>` verifies
directory and archived payload hashes, archive membership and CRC, then checks the
local gallery in isolated headless Edge. It saves screenshots for manual visual
review; browser rendering is not a motion or grading accuracy test.

```powershell
./backend/venv/Scripts/python.exe -B backend/build_current_profile_evidence.py --config backend/current_profile_evidence_runtime_20261003.json --preflight
```
