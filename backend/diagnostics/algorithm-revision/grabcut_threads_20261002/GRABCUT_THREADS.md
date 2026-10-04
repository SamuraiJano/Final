# GrabCut thread-count microbenchmark

This paired test does **not** support changing production to one OpenCV thread
for speed. On twelve preserved real fruit crops, one thread is about 4.7% slower
in aggregate than the native default of 16 threads. All paired masks are identical.
No production setting, image, box, mask parameter or neural model was changed.

## Exact test

First, middle and last preserved complete crops were selected for each frozen
fruit 98, 1, 14 and 491. Their exact BGR arrays, local detector boxes and input
NPZ hashes are retained. Each crop was tested three times in each thread mode:
**36 paired observations / 72 timed GrabCut calls**.

Each pair uses an identical RNG seed, three GrabCut iterations and the exact
`_grabcut` function from candidate SHA-256
`863fd09cfa629c5b5b8ba7c73963fbe993441b3e3dd989f1e451d0a5f62c9db1`.
Its existing internal crop resizing is unchanged. Native/one-thread order alternates
by case and repetition to limit time-order bias. One untimed warm-up runs per mode.
Thread and RNG settings occur outside the timer. The diagnostic process restores
its original 16-thread setting after the calls.

The machine has 8 physical / 16 logical AMD CPU cores. OpenCV 5.0.0 uses the
Windows Concurrency parallel backend. Hardware, memory, CPU-frequency snapshot,
OpenCL flags and complete OpenCV build information are preserved in this folder.

## Results

| Measurement | Native default, 16 threads | One thread |
| --- | ---: | ---: |
| Mean per call | 28.918 ms | 30.286 ms |
| Median per call | 26.520 ms | 28.728 ms |
| Sum of 36 timed calls | 1041.037 ms | 1090.279 ms |

The native/one-thread aggregate time ratio is 0.955, below a speedup of 1.
For every one of the 36 paired masks, IoU is 1.0 and pixel XOR is zero.
This checks agreement between thread modes; it does not establish that either
mask is correct against manually labelled silhouettes.

![Paired runtime by actual frozen crop](grabcut_threads_timing.png)

![Real crops and mask agreement](grabcut_masks_comparison.png)

## Practical limit

A full API analysis and other diagnostic processes were running concurrently.
Their load can affect wall time. The thread-setting call is excluded, but lazy
worker initialization or thread-pool behavior can still affect the timed function.
The small measured difference should not become a general CPU speed claim.

This microbenchmark does not measure full-video detection, tracking, segmentation,
rotation search, frame decoding or scheduling. It therefore cannot explain the
entire approximately 30-minute analysis time or establish an end-to-end speedup.
On this evidence, retain the production thread setting and use stage timings to
identify the larger runtime costs.

`report.json` preserves every mode order, seed, time, foreground count and paired
IoU/XOR result. All 72 masks, twelve input NPZs, crop PNGs, source snapshots,
300-dpi PNG/PDF figures, hardware/build details and hashes are retained.

Reproduce with a fresh label:

```powershell
./backend/venv/Scripts/python.exe -B backend/validate_grabcut_threads.py --label NEW_GRABCUT_THREADS
```
