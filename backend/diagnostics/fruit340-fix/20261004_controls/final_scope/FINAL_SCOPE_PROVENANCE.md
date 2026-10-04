# Final production source: scope guard and measured controls

The final production source is frozen as [algorithm.py](algorithm.py), SHA256 `cf6c2dd19968f0c159a7e2ecb8d781eee0206a88d0bab104df8d087023706745`. The runtime control reports in [CONTROL_FINDINGS.md](../CONTROL_FINDINGS.md) measured source `ed3328de998abba50cf9c135957176649bc2d2ef51ededc9eeed90be1bffc9af` and keep that provenance unchanged.

A complete executable AST comparison verifies that the only production change is the added `s.max_pair_angle_deg <= 20` eligibility predicate for native retries after coarse failure. Three explanatory comments were also added. [Exact source diff](source.diff).

Every stored setting in the 19 original controls, eight lighting stress controls, and two full-estimator 3D controls has a 20-degree maximum pair angle. The added predicate is therefore always true for those measured profiles. Their execution paths and outputs are equivalent to the final source. This is a verified static equivalence argument; these measurements were not rerun after the scope-only change.

The direct native 3D moving/stationary controls call `_search_rotation`, whose complete executable AST is unchanged. Their previously measured component outputs are preserved as well.

Wider sparse-view profiles now retain their earlier behavior when coarse matching fails. They are outside this tested-profile equivalence and do not receive the new retry. The remaining lighting and general tumbling limitations documented in the control findings still apply.

[Machine-readable verification and report hashes](verification.json).
