"""Regression coverage for the shared Qt desktop runtime."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_desktop_loop_exits_when_idle_after_signal(signum: signal.Signals) -> None:
    """The Qt dispatcher must return after a signal arrives while it is idle."""
    child = f"""
import os
import signal
import threading
from PySide6.QtCore import QTimer
from linux_whispr.ui.desktop import ensure_application, run_desktop_loop

ensure_application()
QTimer.singleShot(
    0,
    lambda: threading.Timer(
        0.05, lambda: os.kill(os.getpid(), {int(signum)})
    ).start(),
)
raise SystemExit(run_desktop_loop())
"""
    environment = os.environ | {"QT_QPA_PLATFORM": "offscreen"}
    source_path = str(_PROJECT_ROOT / "src")
    existing_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_path if not existing_path else f"{source_path}{os.pathsep}{existing_path}"
    )

    result = subprocess.run(
        [sys.executable, "-c", child],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        env=environment,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stderr
