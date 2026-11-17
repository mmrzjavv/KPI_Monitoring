"""
Streamlit dashboard for the KPI Monitoring.

The live video is NOT rendered in this page (Streamlit cannot do realtime
video). Instead, the Start button spawns `run_session.py` as a subprocess,
which opens a native OpenCV window at full frame rate and logs activity to
the CSV. This page is the control panel + data viewer.

Run with:
    streamlit run dashboard/app.py
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import Optional

import streamlit as st
import plotly.express as px

from src.logger import (
    load_log,
    summarize,
    summarize_by_day,
    summarize_by_person,
)
from src.monitor import load_config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = load_config(os.path.join(BASE_DIR, "config.yaml"))
DEFAULT_LOG = os.path.join(BASE_DIR, "data", "activity_log.csv")
SESSION_SCRIPT = os.path.join(BASE_DIR, "run_session.py")
STDERR_LOG = os.path.join(BASE_DIR, "data", "session_stderr.log")

st.set_page_config(page_title="KPI Monitoring", layout="wide")
st.title("🖥️ KPI Monitoring")


@st.cache_resource
def session_holder() -> dict:
    """Process-wide slot holding the live-session subprocess.

    cache_resource survives browser refreshes (unlike session_state), so the
    Stop button can still reach the session after a reload.
    """
    return {"proc": None}


HOLDER = session_holder()


def _session_running() -> bool:
    proc = HOLDER["proc"]
    if proc is None:
        return False
    if proc.poll() is not None:  # exited on its own (e.g. user pressed q)
        HOLDER["proc"] = None
        return False
    return True


def _start_session() -> Optional[str]:
    """Spawn the native-window monitor. Returns an error message on failure."""
    err_f = open(STDERR_LOG, "ab")
    proc = subprocess.Popen(
        [sys.executable, SESSION_SCRIPT],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=err_f,
    )
    time.sleep(2.0)  # give it a moment to fail fast (camera busy, etc.)
    if proc.poll() is not None:
        err_f.close()
        try:
            with open(STDERR_LOG, "r", errors="replace") as f:
                tail = f.read()[-400:].strip()
        except OSError:
            tail = "unknown error"
        return f"The live session exited immediately:\n\n```\n{tail}\n```"
    HOLDER["proc"] = proc
    return None


def _stop_session() -> None:
    proc = HOLDER["proc"]
    if proc is None:
        return
    proc.terminate()  # SIGTERM → graceful shutdown, CSV flushed
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    HOLDER["proc"] = None


# ----------------------------------------------------------------------
# Control panel
# ----------------------------------------------------------------------

st.subheader("📷 Live monitoring")
st.caption(
    "Start opens a **separate video window** with realtime detection boxes "
    "and per-person state labels (ID / WORKING / PHONE / IDLE / AWAY), "
    "logging to the CSV as it runs. Press `q` in that window — or the Stop "
    "button here — to end the session."
)

running = _session_running()
st.markdown(
    "**🟢 Live — video window is open**" if running
    else "**⚪ Idle — no session running**"
)

log_file = st.sidebar.text_input(
    "Log file path", DEFAULT_LOG, disabled=running
)

if running:
    if st.button("⏹ Stop camera", type="secondary"):
        _stop_session()
        st.success("Session stopped — log saved.")
        time.sleep(1)
        st.rerun()
else:
    if st.button("▶️ Start camera", type="primary"):
        error = _start_session()
        if error:
            st.error(error)
        else:
            st.rerun()

# Poll session status every 2s so the badge flips to Idle when the window
# is closed with `q`. Lightweight — no video processing in Streamlit.
@st.fragment(run_every=2.0)
def session_status() -> None:
    was_running = _session_running()
    if not was_running and HOLDER.get("_was_running"):
        HOLDER["_was_running"] = False
        st.rerun()  # session just ended → refresh charts
    elif was_running:
        HOLDER["_was_running"] = True


if running:
    session_status()

# ----------------------------------------------------------------------
# Historical data
# ----------------------------------------------------------------------

df = load_log(log_file)

if df.empty:
    st.info(f"No data in `{log_file}` yet — start the camera above to begin logging.")
else:
    is_multi_person = "person_id" in df.columns
    selected = "All"

    if is_multi_person:
        people = sorted(df["person_id"].dropna().unique().tolist())
        selected = st.sidebar.selectbox("Person", ["All"] + [str(p) for p in people])
        if selected != "All":
            df = df[df["person_id"].astype(str) == selected]

    # --- Overall summary ---
    totals = summarize(df)
    total_seconds = sum(totals.values())

    st.subheader("Overall breakdown")
    cols = st.columns(len(totals) if totals else 1)
    for col, (state, secs) in zip(cols, sorted(totals.items(), key=lambda x: -x[1])):
        pct = secs / total_seconds * 100 if total_seconds else 0
        col.metric(state, f"{secs/60:.1f} min", f"{pct:.1f}%")

    pie = px.pie(
        names=list(totals.keys()),
        values=list(totals.values()),
        title="Time distribution by state",
    )
    st.plotly_chart(pie, width="stretch")

    # --- Daily breakdown ---
    st.subheader("Daily breakdown")
    daily = summarize_by_day(df)
    daily["minutes"] = daily["duration_seconds"] / 60

    bar = px.bar(
        daily,
        x="date",
        y="minutes",
        color="state",
        title="Minutes per state, per day",
        barmode="stack",
    )
    st.plotly_chart(bar, width="stretch")

    # --- Per-person breakdown (multi-person mode only) ---
    if is_multi_person and selected == "All":
        st.subheader("Per-person breakdown")
        by_person = summarize_by_person(df)
        by_person["minutes"] = by_person["duration_seconds"] / 60
        by_person["person_id"] = by_person["person_id"].astype(str)
        person_bar = px.bar(
            by_person,
            x="person_id",
            y="minutes",
            color="state",
            title="Minutes per state, per person",
            barmode="stack",
        )
        st.plotly_chart(person_bar, width="stretch")

    # --- Raw log ---
    with st.expander("Raw event log"):
        st.dataframe(df.sort_values("timestamp", ascending=False), width="stretch")
