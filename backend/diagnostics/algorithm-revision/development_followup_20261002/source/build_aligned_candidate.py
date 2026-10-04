"""Freeze an experiment that removes smooth brightness after aligning a patch."""
from pathlib import Path
import hashlib
import json


ROOT=Path(__file__).resolve().parent
BASE=ROOT/'diagnostics/algorithm-revision/hybrid_photometric_source/algorithm_snapshot.py'
OUT=ROOT/'diagnostics/algorithm-revision/aligned_patch_source'


def main():
    source=BASE.read_text(encoding='utf-8')
    def change(old,new):
        nonlocal source
        assert old in source,old
        source=source.replace(old,new,1)
    helper='''def _surface_patches(points, matrix, sigma):
    """Lift a small Gaussian neighborhood onto the same fruit surface."""
    offsets = np.array([(x, y) for y in (-1., 0., 1.) for x in (-1., 0., 1.)])
    xy = points[:, None, :2] + offsets[None, :, :] * (sigma * np.sqrt(2.))
    z = _height(matrix, xy[:, :, 0], xy[:, :, 1])
    return np.concatenate((xy, z[:, :, None]), axis=2)


def _patch_response(green, patches, center, mask, matrix):
    """Compare the center with its neighbors after projecting the whole patch."""
    px, py = patches[:, :, :, 0] + center[0], patches[:, :, :, 1] + center[1]
    h, w = green.shape
    ix = np.rint(np.nan_to_num(px)).astype(int)
    iy = np.rint(np.nan_to_num(py)).astype(int)
    valid = (np.isfinite(patches).all(axis=3) & (patches @ matrix[:, 2] > 0)
             & (ix >= 0) & (iy >= 0) & (ix < w) & (iy < h))
    valid &= mask[np.clip(iy, 0, h-1), np.clip(ix, 0, w-1)] > 0
    shape = px.shape
    values = cv2.remap(green, np.nan_to_num(px).astype(np.float32).reshape(shape[0], -1),
                       np.nan_to_num(py).astype(np.float32).reshape(shape[0], -1),
                       cv2.INTER_LINEAR).reshape(shape)
    weights = np.array([1., 2., 1., 2., 4., 2., 1., 2., 1.]) / 16.
    return values[:, :, 4] - values @ weights, valid.all(axis=2)


'''
    change('def _cost(vector:',helper+'def _cost(vector:')
    change('target_matrix: np.ndarray, normalize: bool = True, compensate_brightness: bool = False\n',
           'target_matrix: np.ndarray, normalize: bool = True, compensate_brightness: bool = False,\n          source_patches: np.ndarray | None = None\n')
    change("    delta = source_values[valid] - values\n",'''    if source_patches is not None:
        patches = np.einsum('ij,pkj->pki', R, source_patches)
        patch_values, patch_valid = _patch_response(target_high, patches[None], center,
                                                  target_mask, target_matrix)
        valid &= patch_valid[0]
        if int(valid.sum()) < min_points:
            return float('inf')
        values = patch_values[0, valid]
    delta = source_values[valid] - values
''')
    change('target_matrix: np.ndarray, normalize: bool = True, compensate_brightness: bool = False) -> np.ndarray:',
           'target_matrix: np.ndarray, normalize: bool = True, compensate_brightness: bool = False,\n               source_patches: np.ndarray | None = None) -> np.ndarray:')
    change('    rotations = np.array([cv2.Rodrigues(vector)[0] for vector in vectors])', '''    if source_patches is not None and len(vectors) > 128:
        return np.concatenate([_cost_many(chunk, points, source_values, target_high,
                               target_mask, target_view, center, min_points, target_matrix,
                               normalize, compensate_brightness, source_patches)
                               for chunk in np.array_split(vectors, int(np.ceil(len(vectors)/128)))])
    rotations = np.array([cv2.Rodrigues(vector)[0] for vector in vectors])''')
    change('    delta = source_values[None,:]-values\n','''    if source_patches is not None:
        patches = np.einsum('nij,pkj->npki', rotations, source_patches)
        values, patch_valid = _patch_response(target_high, patches, center, target_mask, target_matrix)
        valid &= patch_valid
        counts = valid.sum(axis=1)
    delta = source_values[None,:]-values
''')
    change("if s.matching_cost not in ('mad', 'normalized', 'green_mad'):",
           "if s.matching_cost not in ('mad', 'normalized', 'green_mad', 'aligned_mad'):")
    change("green_mad = s.matching_cost == 'green_mad'", "green_mad = s.matching_cost in ('green_mad', 'aligned_mad')\n    patches, reverse_patches = None, None")
    change('    step = s.search_step_deg\n','''    if s.matching_cost == 'aligned_mad':
        patches = _surface_patches(points, model.matrices[index], s.highpass_sigma)
        response, good = _patch_response(source_green, patches[None], model.ellipses[index].center,
                                         source.object_mask, model.matrices[index])
        points, patches, values = points[good[0]], patches[good[0]], response[0, good[0]]
        if len(points) < s.min_pair_points:
            raise MappingError('Insufficient visible source neighborhoods')
        if reverse is not None:
            reverse_patches = _surface_patches(reverse_points, model.matrices[index+1], s.highpass_sigma)
            response, good = _patch_response(target_green, reverse_patches[None], model.ellipses[index+1].center,
                                             target.object_mask, model.matrices[index+1])
            reverse_patches = reverse_patches[good[0]]
            reverse = (reverse_points[good[0]], response[0, good[0]], source_green, source_mask)
            if len(reverse_patches) < s.min_pair_points:
                raise MappingError('Insufficient visible target neighborhoods')
    step = s.search_step_deg
''')
    change('model.matrices[index+1], normalize=normalize, compensate_brightness=green_mad)',
           'model.matrices[index+1], normalize=normalize, compensate_brightness=green_mad, source_patches=patches)')
    change('model.matrices[index], normalize=normalize, compensate_brightness=green_mad)',
           'model.matrices[index], normalize=normalize, compensate_brightness=green_mad, source_patches=reverse_patches)')
    change("model.matrices[index+1],normalize=s.matching_cost=='normalized', compensate_brightness=green_mad)",
           "model.matrices[index+1],normalize=s.matching_cost=='normalized', compensate_brightness=green_mad, source_patches=patches)")
    change("normalize=s.matching_cost=='normalized', compensate_brightness=green_mad)",
           "normalize=s.matching_cost=='normalized', compensate_brightness=green_mad, source_patches=reverse_patches)")
    change("if s.native_matching_cost == 'green_mad' and abs(angle-coarse_angle) > 3.:",
           "if s.native_matching_cost in ('green_mad', 'aligned_mad') and abs(angle-coarse_angle) > 3.:")
    OUT.mkdir(exist_ok=False)
    (OUT/'algorithm_snapshot.py').write_text(source,encoding='utf-8')
    metadata={'baseline_sha256':hashlib.sha256(BASE.read_bytes()).hexdigest(),
              'candidate_sha256':hashlib.sha256((OUT/'algorithm_snapshot.py').read_bytes()).hexdigest(),
              'changes':'Optional native aligned_mad: lift a Gaussian 3x3 neighborhood, project its samples, then remove the neighborhood mean and compare MAD. Native green smoothing2, existing strong points, coarse gate, 3-degree consensus, and map selection stay. Legacy costs unchanged. Experimental, not production.',
              'limitations':'Approximate Gaussian, shape model and multiplicative shading; requires known-motion, stationary, author and fixed-input validation.'}
    (OUT/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    (OUT/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':main()
