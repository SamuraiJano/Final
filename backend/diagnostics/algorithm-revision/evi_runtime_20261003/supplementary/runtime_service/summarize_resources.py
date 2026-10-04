"""Summarize the completed runtime monitor without controlling the app."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


FOLDER = Path(__file__).resolve().parent
GIB = 1024 ** 3


def private_memory(sample, role):
    return sum(process.get('private_bytes') or 0
               for process in sample['owned_processes'] if process['role'] == role)


def main():
    monitor = json.loads((FOLDER/'monitor_summary.json').read_text(encoding='utf-8'))
    assert monitor['stop_reason'] == 'complete', monitor
    rows = [json.loads(line) for line in (FOLDER/'resource_samples.jsonl').read_text(encoding='utf-8').splitlines()]
    assert rows[-1]['analysis']['state'] == 'complete'
    first_time = datetime.fromisoformat(rows[0]['time'])
    minutes = [(datetime.fromisoformat(row['time']) - first_time).total_seconds()/60 for row in rows]
    available = [row['system_memory']['available_bytes'] for row in rows]
    api_private = [private_memory(row, 'api') for row in rows]
    vite_private = [private_memory(row, 'dashboard') for row in rows]
    gpu_used = [sum(device['used_memory_mib'] for device in row.get('gpu', {}).get('devices', [])) for row in rows]
    frames = [row.get('analysis', {}).get('frames_processed', 0) for row in rows]
    api_worker_peaks = [process.get('peak_rss_bytes') or 0 for row in rows
                        for process in row['owned_processes']
                        if process['role'] == 'api' and process.get('name') == 'python.exe']
    summary = {'monitor': monitor, 'sample_interval_seconds': 25,
               'started_at': rows[0]['time'], 'last_sample_at': rows[-1]['time'],
               'minimum_sampled_available_ram_bytes': min(available),
               'maximum_sampled_owned_api_private_bytes': max(api_private),
               'maximum_sampled_owned_dashboard_private_bytes': max(vite_private),
               'maximum_os_reported_api_worker_peak_rss_bytes': max(api_worker_peaks),
               'maximum_sampled_device_gpu_used_mib': max(gpu_used),
               'baseline': rows[0], 'after_completion': rows[-1],
               'limitations': '25-second samples can miss short peaks. Windows peak RSS is separately reported. RAM totals include unrelated applications; GPU usage is total device usage, not per-model allocation. Successful runtime completion does not establish manually verified grading accuracy.',
               'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (FOLDER/'resource_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True, layout='constrained')
    axes[0].plot(minutes, [value/GIB for value in available], color='#247a51', label='System RAM available')
    axes[0].plot(minutes, [value/GIB for value in api_private], color='#225eaa', label='Owned API private memory')
    axes[0].plot(minutes, [value/GIB for value in vite_private], color='#b56524', label='Owned dashboard private memory')
    axes[0].set_ylabel('Memory (GiB)')
    axes[0].set_title('Full original-video runtime retry: 515 frames', loc='left', fontweight='bold')
    axes[0].legend(loc='center left', bbox_to_anchor=(.02, .55), frameon=False)
    axes[1].plot(minutes, [value/1024 for value in gpu_used], color='#76529b', label='Total device GPU memory used')
    axes[1].set_ylabel('GPU memory (GiB)', color='#76529b')
    axes[1].set_ylim(bottom=0)
    progress_axis = axes[1].twinx()
    progress_axis.plot(minutes, frames, '--', color='#60666b', label='Frames processed')
    progress_axis.set_ylabel('Frames processed', color='#60666b')
    progress_axis.set_ylim(0, 550)
    axes[1].set_xlabel('Minutes from first service monitor sample')
    terminal = next(index for index, row in enumerate(rows) if row.get('analysis', {}).get('state') == 'complete')
    for axis in axes:
        axis.axvline(minutes[terminal], color='#888888', linestyle=':', linewidth=1)
        axis.grid(alpha=.18)
    axes[1].legend(loc='upper left', bbox_to_anchor=(.02, .80), frameon=False)
    progress_axis.legend(loc='lower right', frameon=False)
    fig.suptitle('Runtime resources and progress (25-second samples)\nManual grading accuracy was not measured; dotted line marks completion', fontsize=10)
    fig.savefig(FOLDER/'resource_usage.png', dpi=300)
    fig.savefig(FOLDER/'resource_usage.svg')
    fig.savefig(FOLDER/'resource_usage.pdf')
    plt.close(fig)
    print(json.dumps({key: value for key, value in summary.items()
                      if key not in ('baseline', 'after_completion')}, indent=2))


if __name__ == '__main__':
    main()
