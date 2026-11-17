"""
run_session.py
--------------
Live monitoring session in a native OpenCV window.

Launched by the Streamlit dashboard as a subprocess so the video renders at
full frame rate in its own window (Streamlit itself cannot do realtime
video). Press `q` in the video window to stop, or click "Stop camera" on the
dashboard, which sends SIGTERM — handled here so the final state is flushed
to the CSV log before exit.
"""

import signal

from src.monitor import WorkerActivityMonitor, load_config
from src.multi_monitor import MultiPersonMonitor


def main() -> None:
    def _handle_sigterm(signum, frame):
        # Raise inside the main loop so run()'s `finally` executes and the
        # CSV logger flushes the in-progress state before exiting.
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    config = load_config("config.yaml")
    if config.get("multi_person"):
        monitor = MultiPersonMonitor(config)
    else:
        monitor = WorkerActivityMonitor(config)
    monitor.run()


if __name__ == "__main__":
    main()
