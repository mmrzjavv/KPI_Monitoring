#!/bin/zsh
# Launcher for KPI Monitoring in Terminal.
# Running via Terminal.app ensures macOS shows the camera permission prompt
# for Terminal (a proper foreground app), instead of silently denying it.

cd "$(dirname "$0")"
source venv/bin/activate
echo "Starting KPI Monitoring..."
echo "(If macOS asks for camera access, click Allow. Press q in the video window to stop.)"
python main.py
echo
echo "Monitor stopped. You can close this window."
