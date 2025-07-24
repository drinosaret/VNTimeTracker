"""Safe threading utilities to replace problematic threading.Event usage."""

import time
import threading
from typing import Optional


class SafeEvent:
    """Safe event implementation that avoids Windows threading issues."""
    
    def __init__(self):
        self._is_set = False
        self._lock = threading.Lock()
        
    def set(self):
        """Set the event."""
        with self._lock:
            self._is_set = True
    
    def clear(self):
        """Clear the event."""
        with self._lock:
            self._is_set = False
    
    def is_set(self):
        """Check if event is set."""
        with self._lock:
            return self._is_set
    
    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for event with timeout using polling instead of threading.Event.wait().
        This avoids Windows heap corruption issues with threading.Event.wait().
        """
        start_time = time.time()
        poll_interval = 0.1  # Poll every 100ms
        
        while True:
            with self._lock:
                if self._is_set:
                    return True
            
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False
                
                # Sleep for remaining time or poll interval, whichever is smaller
                sleep_time = min(poll_interval, timeout - elapsed)
                time.sleep(sleep_time)
            else:
                time.sleep(poll_interval)


class SafeThread(threading.Thread):
    """Safe thread implementation with better cleanup."""
    
    def __init__(self, target=None, name=None, daemon=True):
        super().__init__(target=target, name=name, daemon=daemon)
        self._stop_event = SafeEvent()
        self._original_target = target
        
    def run(self):
        """Override run to add safety checks."""
        try:
            if self._original_target:
                self._original_target()
        except Exception as e:
            print(f"Thread {self.name} error: {e}")
        finally:
            print(f"Thread {self.name} completed")
    
    def stop(self):
        """Signal thread to stop."""
        self._stop_event.set()
    
    def should_stop(self) -> bool:
        """Check if thread should stop."""
        return self._stop_event.is_set()
    
    def safe_sleep(self, duration: float) -> bool:
        """Sleep with stop check. Returns True if should continue, False if should stop."""
        return not self._stop_event.wait(duration)


def safe_join_thread(thread: threading.Thread, timeout: float = 5.0) -> bool:
    """Safely join a thread with timeout."""
    if not thread or not thread.is_alive():
        return True
    
    try:
        thread.join(timeout=timeout)
        return not thread.is_alive()
    except Exception as e:
        print(f"Error joining thread {getattr(thread, 'name', 'unknown')}: {e}")
        return False
