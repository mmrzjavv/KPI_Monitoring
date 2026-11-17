#!/bin/zsh
# Launcher for the KPI Monitoring dashboard in Terminal.
# Terminal already has macOS camera permission, which the in-page
# live camera feature needs.

cd "$(dirname "$0")"
source venv/bin/activate
echo "Starting KPI Monitoring dashboard..."
echo "(If macOS asks for camera access, click Allow. Then open http://localhost:8501)"
streamlit run dashboard/app.py --server.address localhost
echo
echo "Dashboard stopped. You can close this window."
