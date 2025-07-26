"""Deadlock detection and prevention utilities."""

import time
import threading
from typing import Dict, Optional
from datetime import datetime, timedelta

class DeadlockDetector:
    """Detects potential deadlocks by monitoring lock acquisition times."""
    
    def __init__(self, max_lock_time: float = 30.0):
        self.max_lock_time = max_lock_time
        self.active_locks: Dict[str, float] = {}
        self._monitor_lock = threading.Lock()
        self._shutdown = False
        
    def register_lock_acquisition(self, lock_name: str) -> None:
        """Register that a lock has been acquired."""
        with self._monitor_lock:
            self.active_locks[lock_name] = time.time()
    
    def register_lock_release(self, lock_name: str) -> None:
        """Register that a lock has been released."""
        with self._monitor_lock:
            if lock_name in self.active_locks:
                del self.active_locks[lock_name]
    
    def check_for_deadlocks(self) -> Optional[str]:
        """Check for potential deadlocks and return warning message if found."""
        with self._monitor_lock:
            current_time = time.time()
            for lock_name, acquire_time in self.active_locks.items():
                if current_time - acquire_time > self.max_lock_time:
                    return f"Potential deadlock detected: {lock_name} held for {current_time - acquire_time:.1f}s"
        return None
    
    def get_active_locks(self) -> Dict[str, float]:
        """Get information about currently active locks."""
        with self._monitor_lock:
            current_time = time.time()
            return {name: current_time - acquire_time 
                   for name, acquire_time in self.active_locks.items()}

class SafeLockWrapper:
    """A wrapper for locks that includes deadlock detection."""
    
    def __init__(self, lock: threading.Lock, name: str, detector: Optional[DeadlockDetector] = None):
        self.lock = lock
        self.name = name
        self.detector = detector
        
    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """Acquire the lock with deadlock detection."""
        if self.detector:
            self.detector.register_lock_acquisition(self.name)
        
        try:
            result = self.lock.acquire(blocking, timeout)
            if not result and self.detector:
                # Failed to acquire, remove from tracking
                self.detector.register_lock_release(self.name)
            return result
        except Exception as e:
            if self.detector:
                self.detector.register_lock_release(self.name)
            raise
    
    def release(self) -> None:
        """Release the lock and update tracking."""
        try:
            self.lock.release()
        finally:
            if self.detector:
                self.detector.register_lock_release(self.name)
    
    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise RuntimeError(f"Failed to acquire lock: {self.name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()

# Global deadlock detector instance
deadlock_detector = DeadlockDetector()
