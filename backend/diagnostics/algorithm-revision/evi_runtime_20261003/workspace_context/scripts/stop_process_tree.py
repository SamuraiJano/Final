"""Stop a child started by the app, including Windows Python's worker process."""
import sys

import psutil


def main():
    try:
        parent = psutil.Process(int(sys.argv[1]))
        processes = parent.children(recursive=True) + [parent]
    except psutil.NoSuchProcess:
        return
    # Windows taskkill uses process enumeration that is denied in some setups.
    # psutil opens each owned process directly instead.
    for process in reversed(processes[:-1]):
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        parent.kill()
    except psutil.NoSuchProcess:
        pass


if __name__ == "__main__":
    main()
