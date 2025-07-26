"""Process monitoring for detecting active applications."""

import psutil
import threading
import time
from typing import List, Callable, Optional
from ..utils.system_utils import get_active_process_name, get_running_processes
from ..utils.safe_threading import SafeEvent, safe_join_thread


class ProcessMonitor:
    """System process and active application monitor."""
    
    def __init__(self):
        self.running = True
        self.process_list: List[str] = []
        self.process_list_callbacks: List[Callable[[List[str]], None]] = []
        self.refresh_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._shutdown_event = SafeEvent()
    
    def start(self) -> None:
        """Start process monitoring."""
        if self.refresh_thread is None or not self.refresh_thread.is_alive():
            self.running = True
            self.refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
            self.refresh_thread.start()
            # Initial process list load
            self._update_process_list()
    
    def stop(self) -> None:
        """Stop process monitoring."""
        self.running = False
        self._shutdown_event.set()
        if self.refresh_thread and self.refresh_thread.is_alive():
            safe_join_thread(self.refresh_thread, timeout=3.0)
    
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
            # Add validation before accessing shared data
            if not hasattr(self, '_lock') or self._lock is None:
                print("Warning: Process monitor lock is None")
                return
            
            if not hasattr(self, 'process_list_callbacks'):
                print("Warning: Process monitor callbacks not initialized")
                return
            
            new_list = get_running_processes()
            
            # Thread-safe update with timeout
            if self._lock.acquire(timeout=2.0):
                try:
                    # Validate state before updating
                    if not hasattr(self, 'process_list'):
                        self.process_list = []
                    
                    if new_list != self.process_list:
                        self.process_list = new_list
                        # Notify callbacks with defensive copy
                        process_copy = self.process_list.copy() if self.process_list else []
                        
                        for callback in self.process_list_callbacks:
                            try:
                                # Additional validation before callback
                                if callback and callable(callback):
                                    callback(process_copy)
                            except Exception as e:
                                print(f"Process list callback error: {e}")
                finally:
                    self._lock.release()
            else:
                print("Warning: Failed to acquire process monitor lock for update")
                            
        except Exception as e:
            print(f"Process list update error: {e}")
    
    def _refresh_loop(self) -> None:
        """Background loop to refresh process list."""
        refresh_interval = 120  # Increase to 2 minutes to reduce CPU usage
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self.running and not self._shutdown_event.is_set() and consecutive_errors < max_consecutive_errors:
            try:
                # Check if we're still in a valid state
                if not hasattr(self, 'running') or not self.running:
                    break
                
                self._update_process_list()
                consecutive_errors = 0  # Reset on success
                
                # Use safe polling instead of threading.Event.wait()
                start_wait = time.time()
                while time.time() - start_wait < refresh_interval:
                    if self._shutdown_event.is_set() or not self.running:
                        return
                    time.sleep(5.0)  # Poll every 5 seconds
                    
            except Exception as e:
                consecutive_errors += 1
                error_msg = f"Process monitoring error (attempt {consecutive_errors}): {e}"
                print(error_msg)
                
                if self.running and not self._shutdown_event.is_set() and consecutive_errors < max_consecutive_errors:
                    # Exponential backoff on errors
                    sleep_time = min(10.0 * (2 ** (consecutive_errors - 1)), 60.0)
                    time.sleep(sleep_time)
        
        if consecutive_errors >= max_consecutive_errors:
            print(f"Process monitor thread stopping due to {consecutive_errors} consecutive errors")
    
    def refresh_process_list(self) -> None:
        """Force an immediate refresh of the process list."""
        self._update_process_list()
