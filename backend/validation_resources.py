"""Pause offline validation when Windows lacks physical or commit headroom.

This changes scheduling only. It never changes model inputs, rotation searches,
thresholds, or production application behavior. Windows commit headroom can be
exhausted even when several GB of physical RAM remain available.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import shutil
import time


class _MemoryStatus(ctypes.Structure):
    _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                ('total_physical', ctypes.c_ulonglong), ('available_physical', ctypes.c_ulonglong),
                ('total_pagefile', ctypes.c_ulonglong), ('available_pagefile', ctypes.c_ulonglong),
                ('total_virtual', ctypes.c_ulonglong), ('available_virtual', ctypes.c_ulonglong),
                ('available_extended', ctypes.c_ulonglong)]


def memory_headroom() -> dict:
    if os.name == 'nt':
        status = _MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError()
        return dict(available_physical_bytes=status.available_physical,
                    available_commit_bytes=status.available_pagefile)
    import psutil
    memory = psutil.virtual_memory()
    return dict(available_physical_bytes=memory.available,
                available_commit_bytes=memory.available + psutil.swap_memory().free)


def wait_for_memory(path: Path, *, physical_gib: float = 0, commit_gib: float = 4,
                    disk_gib: float = 0, context: str = 'validation') -> float:
    started = time.perf_counter()
    waiting = False
    while True:
        headroom = memory_headroom()
        if disk_gib:
            headroom['available_disk_bytes'] = shutil.disk_usage(path.parent).free
        ready = (headroom['available_physical_bytes'] >= physical_gib * 2**30
                 and headroom['available_commit_bytes'] >= commit_gib * 2**30
                 and headroom.get('available_disk_bytes', 0) >= disk_gib * 2**30)
        if ready:
            elapsed = time.perf_counter() - started
            if waiting:
                _write_status(path, dict(state='resumed', context=context, waited_seconds=elapsed, **headroom))
                print('Validation memory wait resumed:', context, round(elapsed, 1), 's', flush=True)
            return elapsed if waiting else 0.
        if not waiting:
            print('Validation waiting for memory:', context, headroom, flush=True)
        waiting = True
        _write_status(path, dict(state='waiting_for_memory', context=context,
                               waited_seconds=time.perf_counter()-started,
                               required_physical_gib=physical_gib, required_commit_gib=commit_gib,
                               required_disk_gib=disk_gib,
                               **headroom))
        time.sleep(5)


def _write_status(path: Path, payload: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    temporary.replace(path)
