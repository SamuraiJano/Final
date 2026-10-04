# Toward reliable mapping for 80% of fruit

The recommended target is at least 80% of independently counted physical fruit
entering a fixed inspection region receiving a reliably aligned map covering at
least 80% of its surface. Retain the current 350-degree longitude gate during
the first comparison. Report partial maps separately, and keep all failed
entrants in the denominator. This is a proposed acceptance target, not an
achieved result.

The source remains `cf6c2dd19968f0c159a7e2ecb8d781eee0206a88d0bab104df8d087023706745`.
No production mapper was changed in this investigation. A diagnostic fusion
prototype and a reproducible full-run audit were created and reviewed.

## What the evidence says

The last complete video run predates the latest corrections. It has 474 raw
tracker records, including 146 whose boxes always touch the image edge. Raw
records are not verified unique fruit. Of 328 records ever entirely in frame,
294 produce some map (89.6%), but only three have at least 80% estimated area
(0.91%) and two meet both current coverage criteria (0.61%). Thus producing
images is already common; obtaining adequate reliably aligned surface is the
major gap. Changing the longitude gate alone adds only one map.

Mapped records have a median 63.5 captured views but only nine selected views.
Their median surface coverage is 37.7%. The largest motion-split bucket is
6,399 below-minimum rotation events, followed by 1,475 poor residuals and 1,070
coarse/native disagreements. These are algorithm decisions, not measured
physical rotation. Typical observed full transit has about 2.2 seconds inside
the frame, but duration does not prove that the fruit exposes a full turn.

[Complete audit](../20261004_audit/REPORT.md)

## Highest-value software change

Replace the current adjacent, positive two-component rotation chain and
chronologically ordered longitude strips with one coupled alternative:

1. Obtain accurate instance masks for the fruit, including dark defects and
   separating touching neighbours. Start by checking raw IDs 248, 286, 46 and
   214, which have many complete boxes but almost no accepted masks. Mask
   recovery helps these cases; it cannot recover peel outside the camera.
2. Measure signed three-axis rotations with spatially distributed features and
   robust reprojection fitting. Evaluate the alternative even when the old
   coarse match succeeds, since accepted-but-wrong poses are documented.
   Handle glare and blur explicitly. Preserve inverse consistency and motion
   observability; stationary noise must remain insufficient for full coverage.
3. Select keyframes by usable texture, visibility and measurable displacement.
   Directly match overlapping views beyond a failed adjacent crop when identity
   observations remain continuous. Do not assign a pose to an unseen frame or
   connect across an uncertain identity boundary.
4. Align multiple views jointly in a robust rotation graph, using redundant
   edges and returning-surface checks to identify drift and incorrect matches.
   Unregistered components remain excluded.
5. Project every reliable view into a common fruit surface. For each surface
   point, choose its best one or two source views by visibility, viewing angle,
   blur, glare and pose confidence. Count the union of truly supported surface,
   independent of chronological order. Avoid blindly unioning uncertain defect
   masks, which can enlarge a defect through rounding or misalignment.

This is a replacement for the coupled motion/fusion assumptions. A wider
rotation grid, a tracker replacement or relaxed residual limits alone does not
address all of them. A first prototype can use installed OpenCV and SciPy;
deeper point tracking is a separately benchmarked fallback.

[Detailed architecture and test plan](../20261004_architecture/REPORT.md)

## Evidence that fusion redesign is worth testing

The diagnostic uses exact sphere poses and exact masks, bypassing estimation
and neural models. Existing coverage gates are unchanged. A known rocking
sequence with 275 degrees of unique pose span is rejected by the production
ordering rule, while the all-view prototype supports 85.6% surface and 360
degrees of longitude. Stationary duplicates and a 100-degree turn remain below
the target. This demonstrates a mechanism that can recover valid surface;
it does not establish the fraction of real fruit that will succeed.

[Exact-pose prototype and results](../20261004_architecture/oracle_visibility.json)

## Capture changes if observed skin remains the limiter

- Widen or reposition the inspection view, or separate lanes, so inspected
  fruit is fully visible. A declared inspection region must correspond to the
  real intended process rather than removing difficult fruit after evaluation.
- Test diffuse, stable lighting and crossed polarisers to reduce reflections.
  Keep sufficient light and short exposure for sharp peel features. Calibrate
  defect detection and colour again after changing capture conditions.
- Ensure actual fruit rotation over the complete visibility interval. The
  conveyor can slip or the fruit can rock; nominal roller speed is not proof
  of exposed skin. At about 30 FPS, one turn per second gives about 12 degrees
  per frame and requires at least one fully visible second. Allow practical
  margin and verify the observed surface.
- If blind regions persist, test another calibrated camera angle or a second
  controlled orientation. More repeated images from the same direction do not
  observe the hidden surface.

[Cited research review](../20261004_research/REPORT.md) covers the fruit-specific
2021/2022 spheroid methods, 2025 PhenoCitrus and the limits of deeper registration,
cross-polarised capture and recent photometric stereo. Their reported metrics
are not an 80%-of-fruit conveyor acceptance guarantee.

## Concrete evaluation before claiming the target

Freeze a representative set of independently identified complete passages;
reserve a held-out video before tuning. Compare the current mapper and the
candidate using identical input crops/masks, fixed identity boundaries and
unchanged coverage criteria. Inspect source-point projection and seam/defect
consistency independently. Record runtime, coverage and every rejected fruit's
cause. Include insufficient capture as a failure in the fixed entrant count.

Use a pilot to diagnose the limiting stage, then evaluate at least 100 held-out
physical fruit as a practical first acceptance sample: at least 80 must receive
verified maps meeting the coverage rules. Report the observed rate and sample
uncertainty rather than claiming a population guarantee from a small sample.
If software remains capture-limited, repeat the capture comparison with the
same fruit under improved lighting/rotation before escalating model complexity.

No available evidence yet proves that this existing video alone can meet the
target. The proposal keeps that uncertainty visible while specifying the next
testable change.
