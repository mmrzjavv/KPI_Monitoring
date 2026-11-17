"""
monitor.py
----------
Wires together the webcam feed, object detector, optional gaze heuristic,
activity state machine, and CSV logger into a runnable monitoring session.
"""

import time

import cv2
import yaml

from src.detector import ObjectDetector
from src.activity_tracker import ActivityTracker, classify
from src.logger import CSVActivityLogger, print_summary


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class WorkerActivityMonitor:
    def __init__(self, config: dict):
        self.config = config
        self.cap = self._open_camera(config["camera_index"])

        self.detector = ObjectDetector(
            model_name=config["model_name"],
            confidence_threshold=config["confidence_threshold"],
        )

        self.gaze = None
        if config.get("use_gaze_heuristic"):
            from src.gaze import GazeEstimator  # lazy import (optional dep)
            self.gaze = GazeEstimator()

        self.logger = CSVActivityLogger(config["log_file"], multi_person=False)
        self.tracker = ActivityTracker(on_transition=self._on_transition)

        self.labels = config["labels"]
        self.detect_every_n = config.get("detect_every_n_frames", 5)
        self.frame_count = 0

    def _open_camera(self, index: int, retries: int = 3):
        """Open the camera and wait until it actually delivers frames.

        macOS cameras (AVFoundation) often open successfully but return
        empty frames for the first moments, so we warm it up here instead
        of failing on the first read in run().
        """
        cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
        for attempt in range(1, retries + 1):
            if cap.isOpened():
                for _ in range(30):  # up to ~3s of warm-up reads
                    ok, _ = cap.read()
                    if ok:
                        return cap
                    time.sleep(0.1)
            print(f"Camera at index {index} not delivering frames "
                  f"(attempt {attempt}/{retries}), retrying...")
            cap.release()
            time.sleep(1.0)
            cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
        raise RuntimeError(
            f"Could not open webcam at index {index} after {retries} attempts. "
            "Check `camera_index` in config.yaml and macOS camera permissions "
            "(System Settings → Privacy & Security → Camera)."
        )

    def _on_transition(self, old_state: str, duration: float) -> None:
        self.logger.log(old_state, duration)

    def _classify_frame(self, frame) -> str:
        detected = self.detector.detect_labels(frame)

        looking_at_phone = None
        if self.gaze is not None and self.labels["phone"] in detected:
            looking_at_phone = self.gaze.is_looking_down(frame)

        return classify(
            detected,
            person_label=self.labels["person"],
            laptop_label=self.labels["laptop"],
            phone_label=self.labels["phone"],
            looking_at_phone=looking_at_phone,
        )

    def run(self) -> None:
        print("Monitoring started. Press 'q' in the video window to stop.")
        try:
            consecutive_failures = 0
            while True:
                ok, frame = self.cap.read()
                if not ok:
                    # macOS cameras drop frames occasionally; tolerate brief
                    # gaps instead of exiting on the first empty read.
                    consecutive_failures += 1
                    if consecutive_failures > 60:
                        print("Camera stopped delivering frames. Exiting.")
                        break
                    time.sleep(0.03)
                    continue
                consecutive_failures = 0

                self.frame_count += 1
                if self.frame_count % self.detect_every_n == 0:
                    state = self._classify_frame(frame)
                    self.tracker.update(state)

                self._draw_overlay(frame)
                cv2.imshow("KPI Monitoring", frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            self.tracker.finalize()
            self.cap.release()
            cv2.destroyAllWindows()
            self.logger.close()
            if self.gaze is not None:
                self.gaze.close()
            print_summary(self.config["log_file"])

    def _draw_overlay(self, frame) -> None:
        elapsed = self.tracker.current_elapsed()
        text = f"State: {self.tracker.state}  ({elapsed:.0f}s)"
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 255, 0), 2)
