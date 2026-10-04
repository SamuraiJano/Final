"""Freeze final source and prove its added guard preserves the measured profile."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parents[2]
MEASURED_SHA = "ed3328de998abba50cf9c135957176649bc2d2ef51ededc9eeed90be1bffc9af"
FINAL_SHA = "cf6c2dd19968f0c159a7e2ecb8d781eee0206a88d0bab104df8d087023706745"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    measured = ROOT / "candidate_03/candidate/algorithm.py"
    production = BACKEND / "algorithm.py"
    assert digest(measured) == MEASURED_SHA
    assert digest(production) == FINAL_SHA
    output = ROOT / "final_scope"
    output.mkdir(parents=True, exist_ok=False)
    frozen = output / "algorithm.py"
    frozen.write_bytes(production.read_bytes())
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    old_text, new_text = measured.read_text(), frozen.read_text()
    (output / "source.diff").write_text("".join(difflib.unified_diff(old_text.splitlines(True),new_text.splitlines(True),fromfile="measured_ed3328",tofile="final_cf6c2d")),encoding="utf-8")
    old_tree, new_tree = ast.parse(old_text), ast.parse(new_text)
    expected_guard = ast.parse("s.max_pair_angle_deg <= 20.",mode="eval").body
    changed = []
    class StripAddedScopeGuard(ast.NodeTransformer):
        def visit_BoolOp(self,node):
            self.generic_visit(node)
            if isinstance(node.op,ast.And) and node.values and ast.dump(node.values[0],include_attributes=False)==ast.dump(expected_guard,include_attributes=False):
                changed.append(node.lineno)
                node.values = node.values[1:]
            return node
    stripped = StripAddedScopeGuard().visit(new_tree)
    assert len(changed)==1
    assert ast.dump(old_tree,include_attributes=False)==ast.dump(stripped,include_attributes=False), "Additional executable change found"
    profiles = {}
    for name in ("candidate_03","stress_candidate_03","spatial_candidate_03"):
        path = ROOT / name / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report.get("completed_at")
        assert report["algorithm_sha256"]["candidate"]==MEASURED_SHA
        values = {case:row["variants"]["candidate"]["settings"]["max_pair_angle_deg"] for case,row in report["cases"].items()}
        assert all(value==20. for value in values.values())
        profiles[name] = {"report_sha256":digest(path),"maximum_pair_angle_deg_by_case":values,"new_guard_always_true":True}
    # Direct controls invoke _search_rotation, whose executable AST is identical.
    old_search = next(node for node in old_tree.body if isinstance(node,ast.FunctionDef) and node.name=="_search_rotation")
    new_search = next(node for node in new_tree.body if isinstance(node,ast.FunctionDef) and node.name=="_search_rotation")
    assert ast.dump(old_search,include_attributes=False)==ast.dump(new_search,include_attributes=False)
    direct = {}
    for name in ("native_spatial_component_03","native_stationary_component_03"):
        path = ROOT / name / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report.get("completed_at") and report["algorithm_sha256"]==MEASURED_SHA
        direct[name] = {"report_sha256":digest(path),"direct_search_executable_AST_unchanged":True}
    evidence = {"verified_at":datetime.now(timezone.utc).isoformat(),"measured_algorithm_sha256":MEASURED_SHA,
        "final_algorithm_sha256":digest(frozen),"only_executable_difference":"One additional s.max_pair_angle_deg <= 20 predicate in failed-coarse native retry eligibility.",
        "whole_algorithm_AST_identical_after_removing_one_predicate":True,"changed_predicate_line":changed[0],
        "tested_20_degree_profiles":profiles,"direct_component_controls":direct,
        "validation_scope":"Static path/output equivalence for the measured 20-degree profiles and unchanged direct-search component, rather than another runtime replay. Existing ed3328 artifacts retain their original source hashes. Wider sparse-view profiles are deliberately outside this equivalence because the new guard disables their retry."}
    (output / "verification.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    lines = ["# Final production source: scope guard and measured controls", "",
        f"The final production source is frozen as [algorithm.py](algorithm.py), SHA256 `{FINAL_SHA}`. The runtime control reports in [CONTROL_FINDINGS.md](../CONTROL_FINDINGS.md) measured source `{MEASURED_SHA}` and keep that provenance unchanged.", "",
        "A complete executable AST comparison verifies that the only production change is the added `s.max_pair_angle_deg <= 20` eligibility predicate for native retries after coarse failure. Three explanatory comments were also added. [Exact source diff](source.diff).", "",
        "Every stored setting in the 19 original controls, eight lighting stress controls, and two full-estimator 3D controls has a 20-degree maximum pair angle. The added predicate is therefore always true for those measured profiles. Their execution paths and outputs are equivalent to the final source. This is a verified static equivalence argument; these measurements were not rerun after the scope-only change.", "",
        "The direct native 3D moving/stationary controls call `_search_rotation`, whose complete executable AST is unchanged. Their previously measured component outputs are preserved as well.", "",
        "Wider sparse-view profiles now retain their earlier behavior when coarse matching fails. They are outside this tested-profile equivalence and do not receive the new retry. The remaining lighting and general tumbling limitations documented in the control findings still apply.", "",
        "[Machine-readable verification and report hashes](verification.json).", ""]
    (output / "FINAL_SCOPE_PROVENANCE.md").write_text("\n".join(lines),encoding="utf-8")
    (output / "sha256.json").write_text(json.dumps({path.name:digest(path) for path in output.iterdir() if path.is_file() and path.name!="sha256.json"},indent=2),encoding="utf-8")
    print(json.dumps({"frozen_final_source":str(frozen),"final_sha256":digest(frozen),"only_added_scope_predicate":True,"tested_profiles_identical":True,"report":str(output/"FINAL_SCOPE_PROVENANCE.md")},indent=2))


if __name__=="__main__":
    main()
