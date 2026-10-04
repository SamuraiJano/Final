"""Create an isolated candidate; never overwrite the running production source."""
from pathlib import Path
import hashlib
import json


ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT/'diagnostics/algorithm-revision/photometric_candidate_source'


def main():
    OUTPUT.mkdir(parents=True,exist_ok=False)
    original=(ROOT/'algorithm.py').read_text(encoding='utf-8')
    candidate=original
    replacements=[
        ("matching_cost: str = 'mad'", "matching_cost: str = 'mad'"),
        ("if s.matching_cost not in ('mad', 'normalized'):",
         "if s.matching_cost not in ('mad', 'normalized', 'green_mad'):"),
        ("target_matrix: np.ndarray, normalize: bool = True\n",
         "target_matrix: np.ndarray, normalize: bool = True, compensate_brightness: bool = False\n"),
        ("target_matrix: np.ndarray, normalize: bool = True) -> np.ndarray:",
         "target_matrix: np.ndarray, normalize: bool = True, compensate_brightness: bool = False) -> np.ndarray:"),
        ("difference = float(np.mean(np.abs(source_values[valid] - values)))",
         "delta = source_values[valid] - values\n    if compensate_brightness:\n        delta -= np.median(delta)\n    difference = float(np.mean(np.abs(delta)))"),
        ("scale = max(float(np.mean(np.abs(source_values[valid])) +\n                      np.mean(np.abs(values))), .005)",
         "scale = max(float(np.mean(np.abs(source_values[valid])) +\n                      np.mean(np.abs(values))), .005)\n    if compensate_brightness:\n        scale = max(float(np.std(source_values[valid]) + np.std(values)), .005)"),
        ("differences = np.where(valid,np.abs(source_values[None,:]-values),0).sum(axis=1)/np.maximum(counts,1)",
         "delta = source_values[None,:]-values\n    if compensate_brightness:\n        delta -= np.nanmedian(np.where(valid,delta,np.nan),axis=1)[:,None]\n    differences = np.where(valid,np.abs(delta),0).sum(axis=1)/np.maximum(counts,1)"),
        ("differences /= np.maximum(source_mean+target_mean,.005)",
         "scale = source_mean+target_mean\n        if compensate_brightness:\n            source_std = np.nanstd(np.where(valid,source_values[None,:],np.nan),axis=1)\n            target_std = np.nanstd(np.where(valid,values,np.nan),axis=1)\n            scale = source_std+target_std\n        differences /= np.maximum(scale,.005)"),
        ("return (forward+backward)/2\n", "return (forward+backward)/2\n"),
    ]
    for before,after in replacements:
        if before not in candidate:
            raise ValueError('Expected source fragment missing: '+before)
        candidate=candidate.replace(before,after)
    anchor="        reverse = (reverse_points, reverse_values, source_high, source_mask)\n    step = s.search_step_deg"
    addition='''        reverse = (reverse_points, reverse_values, source_high, source_mask)
    green_mad = s.matching_cost == 'green_mad'
    if green_mad:
        if s.image_downsample != 1:
            raise ValueError('green_mad requires original-resolution images')
        # High-pass texture points remain the paper's. Compare original green
        # values so image-plane filtering cannot deform their appearance.
        source_green = source.image[:, :, 1].astype(np.float32) / 255.
        target_green = target.image[:, :, 1].astype(np.float32) / 255.
        def green_samples(green, xyz, center):
            return cv2.remap(green,(xyz[:,0]+center[0]).astype(np.float32).reshape(1,-1),
                             (xyz[:,1]+center[1]).astype(np.float32).reshape(1,-1),
                             cv2.INTER_LINEAR)[0]
        values = green_samples(source_green,points,model.ellipses[index].center)
        target_high = target_green
        if reverse is not None:
            reverse = (reverse_points,green_samples(target_green,reverse_points,
                       model.ellipses[index+1].center),source_green,source_mask)
    step = s.search_step_deg'''
    if anchor not in candidate: raise ValueError('Search initialization changed')
    candidate=candidate.replace(anchor,addition)
    # Pass the brightness rule explicitly into all scalar and batch costs.
    candidate=candidate.replace("model.matrices[index+1], normalize=normalize)",
                                "model.matrices[index+1], normalize=normalize, compensate_brightness=green_mad)")
    candidate=candidate.replace("model.matrices[index], normalize=normalize)",
                                "model.matrices[index], normalize=normalize, compensate_brightness=green_mad)")
    candidate=candidate.replace("model.matrices[index+1],normalize=s.matching_cost=='normalized')",
                                "model.matrices[index+1],normalize=s.matching_cost=='normalized', compensate_brightness=green_mad)")
    candidate=candidate.replace("normalize=s.matching_cost=='normalized')\n            costs",
                                "normalize=s.matching_cost=='normalized', compensate_brightness=green_mad)\n            costs")
    path=OUTPUT/'algorithm_snapshot.py'
    path.write_text(candidate,encoding='utf-8')
    (OUTPUT/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (OUTPUT/'metadata.json').write_text(json.dumps(dict(
        baseline_sha256=hashlib.sha256((ROOT/'algorithm.py').read_bytes()).hexdigest(),
        candidate_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        change='Optional native green_mad objective. Same high-pass-selected points, 3D projection and MAD search; '
               'subtract median sampled brightness difference, normalize reporting residual by sample contrast. '
               'Paper mad objective unchanged. Explicit native-only settings, not a production default.'),indent=2),encoding='utf-8')
    print(path)


if __name__=='__main__':
    main()
