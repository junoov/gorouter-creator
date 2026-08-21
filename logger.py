"""Shared logger — writes to stdout + log file"""
from datetime import datetime
from pathlib import Path

_LOG_FILE = None


def set_log_file(path):
    global _LOG_FILE
    _LOG_FILE = path


def log(msg=""):
    print(msg)
    if _LOG_FILE:
        try:
            with open(_LOG_FILE, "a") as f:
                ts = datetime.now().strftime("%H:%M:%S")
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass
