"""System utilities for Windows-specific operations."""

import win32gui
import win32process
import win32api
import psutil
from typing import Optional
from datetime import datetime


def get_today() -> str:
    """Get today's date as string."""
    return datetime.now().strftime("%Y-%m-%d")


def get_last_input_time() -> float:
    """Get time since last user input in seconds."""
    try:
        lii = win32api.GetLastInputInfo()
        current_time = win32api.GetTickCount()
        elapsed_ms = current_time - lii
        return elapsed_ms / 1000.0  # Convert milliseconds to seconds
    except Exception as e:
        print(f"Input time retrieval error: {e}")
        return 0


def get_active_process_name() -> Optional[str]:
    """Get the name of the currently active process."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:  # No foreground window
            return None
            
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid <= 0:  # Invalid PID
            return None
            
        proc = psutil.Process(pid)
        return proc.name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None
    except Exception as e:
        print(f"Active process retrieval error: {e}")
        return None


def get_running_processes() -> list[str]:
    """Get list of currently running process names."""
    names = set()
    for proc in psutil.process_iter(['name']):
        try:
            names.add(proc.info['name'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return sorted(list(names))


def format_time(seconds: int) -> str:
    """Format seconds into HH:MM:SS string."""
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hrs:02}:{mins:02}:{secs:02}"
