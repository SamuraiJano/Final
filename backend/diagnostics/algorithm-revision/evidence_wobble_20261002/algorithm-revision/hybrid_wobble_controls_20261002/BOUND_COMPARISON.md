# Transverse search bound comparison

The exact same source, four frozen image sets and acceptance limits were used at 10 and 20 degrees. All input hashes match. The transverse bound is the only settings change. Every control outcome and summary is identical.

Both moving textures return all ten pairs. Maximum 3D pose errors are 0.221953 and 0.094169 degrees; maximum projected landmark RMS errors are 0.202319 and 0.085987 pixels. Both 120-frame stationary textures reject all 119 pairs, producing no propagated endpoint, map or grade. Those unavailable results do not establish zero stationary pose error. Both brightness-offset controls pass.

The [2021 paper, Section 3.2](https://pmc.ncbi.nlm.nih.gov/articles/PMC8004661/) describes a typical 10-degree transverse bound. Trying 20 degrees adapts the search region to the setup while retaining the existing objective and rejection limits. These short-motion controls cover small transverse motion; they do not validate large transverse wobble, actual conveyor pose or defect grades.

Machine-readable checks and exact hashes are in [bound_comparison.json](bound_comparison.json).
