"""Process monitoring for detecting active applications."""

import psutil
import threading
import time
from typing import List, Callable, Optional
from ..utils.system_utils import get_active_process_name, get_running_processes


class ProcessMonitor:
    """Monitors system processes and active application."""
    
    def __init__(self):
        self.running = True
        self.process_list: List[str] = []
        self.process_list_callbacks: List[Callable[[List[str]], None]] = []
        self.refresh_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> None:
        """Start the process monitoring."""
        if self.refresh_thread is None or not self.refresh_thread.is_alive():
            self.running = True
            self.refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
            self.refresh_thread.start()
            # Initial load
            self._update_process_list()
    
    def stop(self) -> None:
        """Stop the process monitoring."""
        self.running = False
        if self.refresh_thread and self.refresh_thread.is_alive():
            self.refresh_thread.join(timeout=1.0)
    
    def get_active_process(self) -> Optional[str]:
        """Get the currently active process name."""
        return get_active_process_name()
    
    def get_process_list(self) -> List[str]:
        """Get the current list of running processes."""
        with self._lock:
            return self.process_list.copy()
    
    def add_process_list_callback(self, callback: Callable[[List[str]], None]) -> None:
        """Add a callback for when process list changes."""
        self.process_list_callbacks.append(callback)
    
    def remove_process_list_callback(self, callback: Callable[[List[str]], None]) -> None:
        """Remove a process list callback."""
        if callback in self.process_list_callbacks:
            self.process_list_callbacks.remove(callback)
    
    def _update_process_list(self) -> None:
        """Update the process list."""
        try:
            new_list = get_running_processes()
            
            with self._lock:
                if new_list != self.process_list:
                    self.process_list = new_list
                    # Notify callbacks
                    for callback in self.process_list_callbacks:
                        try:
                            callback(self.process_list.copy())
                        except Exception as e:
                            print(f"Process list callback error: {e}")
                            
        except Exception as e:
            print(f"Process list update error: {e}")
    
    def _refresh_loop(self) -> None:
        """Background loop to refresh process list."""
        refresh_interval = 120  # Increase to 2 minutes to reduce CPU usage
        while self.running:
            try:
                self._update_process_list()
                time.sleep(refresh_interval)
            except Exception as e:
                print(f"Process monitoring error: {e}")
                if self.running:
                    time.sleep(10)  # Wait before retrying
    
    def refresh_process_list(self) -> None:
        """Force an immediate refresh of the process list."""
        self._update_process_list()
