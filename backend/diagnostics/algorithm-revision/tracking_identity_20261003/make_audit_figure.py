"""Create a report figure from saved observations and CPU tracker diagnostics."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
import numpy as np

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
JOB = BACKEND/'results/ea6e595b8f3f45f2b5edfda8dafff3f2'


def row(identity):
    return json.loads((JOB/str(identity)/'result.json').read_text())


plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                     'axes.spines.right': False, 'axes.titlesize': 12})
fig = plt.figure(figsize=(14, 9), facecolor='white')
grid = fig.add_gridspec(3, 2, height_ratios=[1, .65, .55], top=.88, bottom=.15,
                       left=.07, right=.98, wspace=.2, hspace=.8)
ax = fig.add_subplot(grid[0, 0])
normal = row(98)
history = normal['tracking_history']
frames = np.array([item['frame'] for item in history])
boxes = np.array([item['bbox_xyxy'] for item in history])
y = (boxes[:, 1] + boxes[:, 3])/2
complete = np.array([not item['touches_frame_edge'] for item in history])
ax.plot(frames, y, color='#21765e', linewidth=2)
ax.scatter(frames[~complete], y[~complete], color='#c66628', s=15, label='Clipped entry / exit')
ax.set(title='Saved Fruit 98: ID retained on all 88 frames', xlabel='Original video frame', ylabel='Detected centre y (pixels)')
ax.invert_yaxis()
ax.legend(loc='best', fontsize=9, frameon=False)
ax.text(0, -.35, 'First accepted detection: 51. Last seen: 138.\n66 usable map views; clipped observations remain tracking evidence.', transform=ax.transAxes, fontsize=9)

ax = fig.add_subplot(grid[0, 1])
for identity, color in ((59, '#a54132'), (91, '#9c7728'), (102, '#485c9e')):
    history = row(identity)['tracking_history']
    frames = [item['frame'] for item in history]
    y = [(item['bbox_xyxy'][1]+item['bbox_xyxy'][3])/2 for item in history]
    ax.plot(frames, y, 'o-', markersize=3, linewidth=1.3, label=f'Revised ID {identity}', color=color)
ax.set(title='A side-edge association disagreement', xlabel='Original video frame', ylabel='Detected centre y (pixels)')
ax.invert_yaxis()
ax.legend(loc='best', fontsize=9, frameon=False)
ax.text(0, -.35, 'All three matched parts of old ID 82; the old tracker is not ground truth.\nAll three have zero usable map views, so none produced a surface map.', transform=ax.transAxes, fontsize=9)

ax = fig.add_subplot(grid[1, :])
ax.axis('off')
experiment = json.loads((HERE/'no_gmc_experiment.json').read_text())
data = [[name, value['frames'], value['track_records'], value['ids_at_most_two_observations'], value['median_observations_per_id']]
        for name, value in (('Current sparse optical flow', experiment['existing_sparse_optical_flow_gmc']),
                            ('Experimental compensation disabled', experiment['experimental_no_gmc']))]
table = ax.table(cellText=data, colLabels=['CPU cached-box replay', 'Frames', 'Published IDs', 'IDs with ≤ 2\nobservations', 'Median observations\nper ID'],
                 cellLoc='center', colWidths=[.43, .1, .14, .17, .16], loc='center')
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1, 2.0)
for (r, c), cell in table.get_celld().items():
    cell.set_edgecolor('#d9dfdb')
    if r == 0:
        cell.set_facecolor('#e7efe9')
        cell.set_text_props(weight='bold')
ax.set_title('Disabling camera-motion compensation increased short track records', loc='left', pad=14)
ax.text(0, -.27, 'Identical real detections from all 515 original frames. No neural model calls; production tracker unchanged.\nThese are continuity indicators, not a measurement of true ID switches or unique fruit count.', transform=ax.transAxes, fontsize=9)

ax = fig.add_subplot(grid[2, :])
ax.set_xlim(0, 12)
ax.set_ylim(0, 2)
ax.axis('off')
for x, frame, truth in ((1.5, 0, 'A'), (5.5, 1, None), (9.5, 2, 'B')):
    ax.add_patch(Rectangle((x-1.1, .1), 2.2, 1.4, facecolor='#faf9f4', edgecolor='#b8b8b8'))
    if truth:
        ax.add_patch(Circle((x, .8), .45, facecolor='#e89835', edgecolor='#ac6417'))
        ax.text(x, .05, f'Hidden physical identity {truth}', ha='center', va='top', fontsize=9)
        ax.text(x, 1.68, f'Frame {frame}: tracker ID 1', ha='center', fontsize=10)
    else:
        ax.text(x, .8, 'No detection', ha='center', fontsize=10)
        ax.text(x, 1.68, f'Frame {frame}', ha='center', fontsize=10)
for x in (3.5, 7.5):
    ax.annotate('', xy=(x+.6, .8), xytext=(x-.6, .8), arrowprops={'arrowstyle': '->', 'color': '#6b6b6b'})
ax.set_title('Known synthetic replacement: geometry alone cannot distinguish A from B', loc='left', pad=10)

fig.suptitle('Tracking audit of the original conveyor video', x=.07, y=.96, ha='left', fontsize=19, weight='bold')
fig.text(.07, .91, '32,875 saved boxes match the retained tracking replay exactly. No manually labelled physical identities are available.', fontsize=11)
fig.text(.07, .025,
         'Diagnostic scope: original application job ea6e595b8f3f45f2b5edfda8dafff3f2; tracker adapter SHA-256 20049bf4e246… .\n'
         'All 15 revised IDs involved in the seven prior tracker disagreements failed mapping (14 zero-view, one single-view).\n'
         'Smooth swaps can evade geometric checks. The A/B example is synthetic and does not prove a swap in the real conveyor video.', fontsize=9)
fig.savefig(HERE/'tracking_audit.png', dpi=300)
fig.savefig(HERE/'tracking_audit.pdf')
plt.close(fig)
