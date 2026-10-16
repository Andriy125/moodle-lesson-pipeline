from __future__ import annotations

import os

import msvcrt


def dependency_env() -> dict[str, str]:
    """Environment for child step processes (UTF-8 console output)."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def wait_for_key() -> str:
    while True:
        key = msvcrt.getch()
        if key in (b"\r", b"\n"):
            return "enter"
        if key == b"\x12":
            return "restart"
        if key == b"\x03":
            raise KeyboardInterrupt
        if key in (b"\x00", b"\xe0"):
            msvcrt.getch()
