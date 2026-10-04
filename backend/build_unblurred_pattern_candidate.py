"""Freeze an experiment that projects raw texture patches before filtering."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'diagnostics/algorithm-revision/aligned_pattern_source/algorithm_snapshot.py'
DEST = ROOT / 'diagnostics/algorithm-revision/aligned_unblurred_pattern_source'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    data = BASE.read_bytes()
    assert digest(data) == '9a5a3e13c8b9200958c678110640153022dbe8e59d4e3559ea1743ef579b5067'
    text = data.decode('utf-8')
    before = """        source_green = cv2.GaussianBlur(source_green, (0, 0), 2.)
        target_green = target.image[:, :, 1].astype(np.float32) / 255.
        target_green = cv2.GaussianBlur(target_green, (0, 0), 2.)"""
    after = """        target_green = target.image[:, :, 1].astype(np.float32) / 255.
        if s.matching_cost == 'green_mad':
            source_green = cv2.GaussianBlur(source_green, (0, 0), 2.)
            target_green = cv2.GaussianBlur(target_green, (0, 0), 2.)
        # aligned_mad compares the nine raw samples after surface projection.
        # Filtering before projection would blur along camera coordinates."""
    assert text.count(before) == 1
    result = text.replace(before, after).encode('utf-8')
    DEST.mkdir(parents=True, exist_ok=False)
    (DEST / 'algorithm_snapshot.py').write_bytes(result)
    (DEST / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    metadata = {'baseline_sha256': digest(data), 'candidate_sha256': digest(result),
                'changes': 'Only aligned_mad uses unblurred green samples. The same nine projected samples are locally centered, contrast-normalized and compared by weighted MAD. This avoids Gaussian2 filtering in camera coordinates before projection. Feature selection, search, consensus, thresholds, legacy high-pass/green matching remain unchanged. Experimental.',
                'generator_sha256': digest(Path(__file__).read_bytes())}
    (DEST / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
