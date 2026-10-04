"""Make a report figure from a completed geometry-only longitude audit."""
import argparse
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    folder = args.folder.resolve()
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    auto = json.loads((folder/'auto/longitude_trace.json').read_text(encoding='utf-8'))
    pair = auto['bad_transitions'][0]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11})
    fig = plt.figure(figsize=(10, 8), constrained_layout=False)
    grid = fig.add_gridspec(2, 2, height_ratios=(1.2, 1), left=.09, right=.98, top=.88, bottom=.16,
                           hspace=.38, wspace=.18)
    fig.suptitle(f'Fruit {report["track"]}: an estimated pair violates map ordering', x=.09, y=.965,
                 ha='left', fontsize=17, fontweight='bold')
    fig.text(.09, .92, 'Cached detector boxes and original images; geometry-only replay', color='#555555')
    for position, frame in enumerate((pair['source_frame'], pair['target_frame'])):
        ax = fig.add_subplot(grid[0, position])
        image = cv2.imread(str(folder/'captured_views'/f'frame_{frame:05d}_crop.png'))
        mask = cv2.imread(str(folder/'captured_views'/f'frame_{frame:05d}_fruit_mask.png'), cv2.IMREAD_GRAYSCALE)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(image, contours, -1, (0, 255, 0), 1)
        ax.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        ax.set_title(f'Actual crop, frame {frame}', loc='left', fontsize=12)
        ax.axis('off')
    ax = fig.add_subplot(grid[1, :])
    ax.plot(auto['selected_frames'], auto['progress_deg'], 'o-', color='#a63735', label='Automatic oblate model')
    ax.plot(auto['selected_frames'][:2], auto['progress_deg'][:2], color='#c60000', linewidth=4)
    if 'sphere' in report['variants']:
        sphere = json.loads((folder/'sphere/longitude_trace.json').read_text(encoding='utf-8'))
        ax.plot(sphere['selected_frames'], sphere['progress_deg'], 'o-', color='#256c97', label='Sphere shape control')
    ax.annotate(f'{pair["longitude_progress_delta_deg"]:.3f}° backwards',
                (auto['selected_frames'][1], auto['progress_deg'][1]), xytext=(309, -10),
                arrowprops={'arrowstyle': '->', 'color': '#a63735'}, color='#a63735')
    ax.set(xlabel='Original frame number', ylabel='Estimated fruit longitude progress (degrees)',
           ylim=(-20, max(135, max(auto['progress_deg'])+10)))
    ax.grid(axis='y', alpha=.2)
    ax.spines[['right', 'top']].set_visible(False)
    ax.legend(loc='upper left', frameon=False, bbox_to_anchor=(.03, 1))
    vector = pair['rotation_vector_deg']
    fig.text(.09, .085, f'Accepted pair rotation: x = {vector[0]:.3f}°, y = {vector[1]:.3f}°. '
             'Positive image-x motion did not ensure forward map longitude.', fontsize=10)
    fig.text(.09, .032, 'The sphere control remains incomplete (214.58° observed longitude).\n'
             'No rotation ground truth, defect inference or grading claim.', fontsize=10, color='#555555')
    fig.savefig(folder/'longitude_failure_comparison.png', dpi=300)
    fig.savefig(folder/'longitude_failure_comparison.pdf')
    (folder/'build_longitude_failure_figure.py.snapshot').write_bytes(Path(__file__).read_bytes())
    print(folder/'longitude_failure_comparison.png')


if __name__ == '__main__':
    main()
