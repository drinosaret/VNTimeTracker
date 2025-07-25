"""Time tracking core functionality."""

import time
import threading
from typing import Optional, Callable, List
from enum import Enum
from ..utils.system_utils import get_last_input_time
from ..utils.data_storage import TimeDataManager
from ..utils.crash_logger import CrashLogger, safe_call
from ..utils.safe_threading import SafeEvent, SafeThread, safe_join_thread
from .process_monitor import ProcessMonitor


class TrackingState(Enum):
    """Tracking state enumeration."""
    ACTIVE = "GREEN"
    AFK = "YELLOW"
    INACTIVE = "RED"


class TimeTracker:
    """Core time tracking functionality."""
    
    def get_state(self):
        """Return current tracking state."""
        return getattr(self, 'current_state', TrackingState.INACTIVE)
    
    def __init__(self, data_manager: TimeDataManager, process_monitor: ProcessMonitor, crash_logger: Optional[CrashLogger] = None):
        self.data_manager = data_manager
        self.process_monitor = process_monitor
        self.crash_logger = crash_logger
        self.running = False
        
        # Tracking state
        self.selected_vn_title: Optional[str] = None
        self.selected_process: Optional[str] = None
        self.last_start: Optional[float] = None
        self.afk_threshold = 60
        
        # Callbacks
        self.state_callbacks: List[Callable[[TrackingState, int], None]] = []
        self.update_callbacks: List[Callable[[], None]] = []
        
        # Threading
        self.track_thread: Optional[SafeThread] = None
        self.autosave_thread: Optional[SafeThread] = None
        self._data_lock = threading.RLock()  # Reentrant lock for data access
        self._shutdown_event = SafeEvent()  # Safe event for clean shutdown
        
        # Emergency save configuration
        self._last_save_time = time.time()
        self._save_interval = 10
    
    def start(self) -> None:
        """Start time tracking threads with safe threading."""
        if not self.running:
            self.running = True
            self._shutdown_event.clear()
            
            self.track_thread = SafeThread(target=self._track_loop, name="VN-Tracker")
            self.autosave_thread = SafeThread(target=self._autosave_loop, name="VN-AutoSave")
            self.track_thread.start()
            self.autosave_thread.start()
    
    def stop(self) -> None:
        """Stop tracking and save pending data."""
        if self.running:
            # Signal shutdown to all threads first
            self._shutdown_event.set()
            
            # Try to acquire lock with timeout to save final data
            if self._data_lock.acquire(timeout=10.0):
                try:
                    # Save pending time
                    if self.selected_vn_title and self.last_start:
                        elapsed = int(time.time() - self.last_start)
                        safe_call(
                            self.data_manager.add_time,
                            self.selected_vn_title, elapsed,
                            operation_name="final time save on stop",
                            logger=self.crash_logger
                        )
                        self.last_start = None
                    
                    # Force data save
                    safe_call(
                        self.data_manager.save,
                        force_backup=True,
                        operation_name="final data save on stop",
                        logger=self.crash_logger
                    )
                finally:
                    self._data_lock.release()
            else:
                # If unable to get lock, do emergency save
                if self.crash_logger:
                    self.crash_logger.log_error("Could not acquire lock for final save, attempting emergency save")
                if hasattr(self.data_manager, 'emergency_save'):
                    self.data_manager.emergency_save()
            
            self.running = False
            
            # Wait for thread completion with timeout using safe join
            if self.track_thread:
                self.track_thread.stop()
                safe_join_thread(self.track_thread, timeout=5.0)
                self.track_thread = None
            
            if self.autosave_thread:
                self.autosave_thread.stop()
                safe_join_thread(self.autosave_thread, timeout=5.0)
                self.autosave_thread = None
    
    def set_target(self, vn_title: str, process_name: str) -> None:
        """Set target VN and process for tracking."""
        with self._data_lock:
            # Save pending time from previous target
            if self.selected_vn_title and self.last_start:
                elapsed = int(time.time() - self.last_start)
                safe_call(
                    self.data_manager.add_time,
                    self.selected_vn_title, elapsed,
                    operation_name="time save on target change",
                    logger=self.crash_logger
                )
                self.last_start = None
            
            self.selected_vn_title = vn_title
            self.selected_process = process_name.lower() if process_name else None
    
    def set_afk_threshold(self, seconds: int) -> None:
        """Set AFK threshold in seconds."""
        with self._data_lock:
            self.afk_threshold = max(0, seconds)
    
    def get_current_seconds(self) -> int:
        """Get current session seconds including active time."""
        with self._data_lock:
            if not self.selected_vn_title:
                return 0
            
            base_seconds = self.data_manager.get_today_seconds(self.selected_vn_title)
            if self.last_start:
                base_seconds += int(time.time() - self.last_start)
            return base_seconds
    
    def get_today_seconds(self) -> int:
        """Get today's seconds for selected VN."""
        if not self.selected_vn_title:
            return 0
        return self.data_manager.get_today_seconds(self.selected_vn_title)
    
    def get_weekly_seconds(self) -> int:
        """Get weekly seconds for selected VN."""
        if not self.selected_vn_title:
            return 0
        return self.data_manager.get_weekly_seconds(self.selected_vn_title)
    
    def get_monthly_seconds(self) -> int:
        """Get monthly seconds for selected VN."""
        if not self.selected_vn_title:
            return 0
        return self.data_manager.get_monthly_seconds(self.selected_vn_title)
    
    def get_total_seconds(self) -> int:
        """Get total seconds for selected VN."""
        if not self.selected_vn_title:
            return 0
        return self.data_manager.get_total_seconds(self.selected_vn_title)
    
    def reset_today(self) -> None:
        """Reset today's time for selected VN."""
        if self.selected_vn_title:
            safe_call(
                self.data_manager.reset_today,
                self.selected_vn_title,
                operation_name="reset today",
                logger=self.crash_logger
            )
            self.last_start = None
    
    def add_state_callback(self, callback: Callable[[TrackingState, int], None]) -> None:
        """Add state change callback."""
        self.state_callbacks.append(callback)
    
    def add_update_callback(self, callback: Callable[[], None]) -> None:
        """Add general update callback."""
        self.update_callbacks.append(callback)
    
    def _track_loop(self) -> None:
        """Main tracking loop."""
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self.running and consecutive_errors < max_consecutive_errors:
            try:
                # Check if required objects are still valid
                if not hasattr(self, 'data_manager') or self.data_manager is None:
                    if self.crash_logger:
                        self.crash_logger.log_error("Data manager is None in track loop")
                    break
                
                if not hasattr(self, 'process_monitor') or self.process_monitor is None:
                    if self.crash_logger:
                        self.crash_logger.log_error("Process monitor is None in track loop")
                    break
                
                if not self.selected_process or not self.selected_vn_title:
                    self.current_state = TrackingState.INACTIVE
                    time.sleep(1)
                    continue

                # Get current process and idle state with safety
                active_process = safe_call(
                    self.process_monitor.get_active_process,
                    operation_name="get active process",
                    logger=self.crash_logger,
                    default_return=None
                )
                
                idle_time = safe_call(
                    get_last_input_time,
                    operation_name="get last input time",
                    logger=self.crash_logger,
                    default_return=0
                )

                is_process_active = (active_process == self.selected_process)

                # Acquire lock with timeout to prevent deadlocks
                state_changed = False
                if self._data_lock.acquire(timeout=2.0):
                    try:
                        # Double check state after acquiring lock
                        if not self.running:
                            return
                        
                        # Determine state and handle time tracking
                        if not is_process_active:
                            state = TrackingState.INACTIVE
                            if self.last_start:
                                elapsed = int(time.time() - self.last_start)
                                safe_call(
                                    self.data_manager.add_time,
                                    self.selected_vn_title, elapsed,
                                    operation_name="add time on process inactive",
                                    logger=self.crash_logger
                                )
                                self.last_start = None
                                state_changed = True
                        elif idle_time > self.afk_threshold:
                            state = TrackingState.AFK
                            if self.last_start:
                                elapsed = int(time.time() - self.last_start)
                                safe_call(
                                    self.data_manager.add_time,
                                    self.selected_vn_title, elapsed,
                                    operation_name="add time on AFK",
                                    logger=self.crash_logger
                                )
                                self.last_start = None
                                state_changed = True
                        else:
                            state = TrackingState.ACTIVE
                            if self.last_start is None:
                                self.last_start = time.time()
                                state_changed = True

                        # Emergency save during active tracking
                        current_time = time.time()
                        if (state == TrackingState.ACTIVE and 
                            self.last_start and 
                            current_time - self._last_save_time > self._save_interval):
                            
                            # Save progress
                            elapsed = int(current_time - self.last_start)
                            if elapsed > 0:
                                safe_call(
                                    self.data_manager.add_time,
                                    self.selected_vn_title, elapsed,
                                    operation_name="emergency save during tracking",
                                    logger=self.crash_logger
                                )
                                # Reset to avoid double counting
                                self.last_start = current_time
                                self._last_save_time = current_time

                        # Store state
                        self.current_state = state

                        # Get total seconds after state changes
                        current_seconds = self.get_current_seconds()
                    finally:
                        self._data_lock.release()
                else:
                    if self.crash_logger:
                        self.crash_logger.log_error("Track loop: Failed to acquire data lock within timeout")
                    consecutive_errors += 1
                    time.sleep(2.0)
                    continue

                # Execute callbacks outside of lock to prevent deadlocks
                for callback in self.state_callbacks:
                    if not self.running:
                        break
                    safe_call(
                        callback, state, current_seconds,
                        operation_name="state callback",
                        logger=self.crash_logger
                    )

                for callback in self.update_callbacks:
                    if not self.running:
                        break
                    safe_call(
                        callback,
                        operation_name="update callback",
                        logger=self.crash_logger
                    )

                # Reset error counter on successful iteration
                consecutive_errors = 0
                
                time.sleep(1)

            except Exception as e:
                consecutive_errors += 1
                error_msg = f"Tracking error (attempt {consecutive_errors}): {e}"
                if self.crash_logger:
                    self.crash_logger.log_error(error_msg)
                else:
                    print(error_msg)
                
                if self.running and consecutive_errors < max_consecutive_errors:
                    # Exponential backoff on errors
                    sleep_time = min(1.0 * (2 ** (consecutive_errors - 1)), 10.0)
                    time.sleep(sleep_time)
        
        if consecutive_errors >= max_consecutive_errors:
            error_msg = f"Track thread stopping due to {consecutive_errors} consecutive errors"
            if self.crash_logger:
                self.crash_logger.log_error(error_msg)
            else:
                print(error_msg)
    
    def _autosave_loop(self) -> None:
        """Periodic data saving loop."""
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self.running and not self._shutdown_event.is_set() and consecutive_errors < max_consecutive_errors:
            try:
                # Check if data manager is still valid
                if not hasattr(self, 'data_manager') or self.data_manager is None:
                    if self.crash_logger:
                        self.crash_logger.log_error("Data manager is None in autosave loop")
                    break
                
                # Acquire lock with timeout to prevent deadlocks
                if self._data_lock.acquire(timeout=5.0):
                    try:
                        # Double check state after acquiring lock
                        if self.running and not self._shutdown_event.is_set():
                            safe_call(
                                self.data_manager.save,
                                operation_name="autosave",
                                logger=self.crash_logger
                            )
                    finally:
                        self._data_lock.release()
                else:
                    if self.crash_logger:
                        self.crash_logger.log_error("Autosave: Failed to acquire data lock within timeout")
                    consecutive_errors += 1
                    time.sleep(5.0)
                    continue
                
                # Reset error counter on successful save
                consecutive_errors = 0
                
                # Wait with safe polling instead of threading.Event.wait()
                # This avoids Windows heap corruption issues
                start_wait = time.time()
                while time.time() - start_wait < 30.0:
                    if self._shutdown_event.is_set():
                        return
                    if not self.running:
                        return
                    time.sleep(1.0)  # Poll every second
                    
            except Exception as e:
                consecutive_errors += 1
                error_msg = f"Auto-save error (attempt {consecutive_errors}): {e}"
                if self.crash_logger:
                    self.crash_logger.log_error(error_msg)
                else:
                    print(error_msg)
                
                if self.running and not self._shutdown_event.is_set() and consecutive_errors < max_consecutive_errors:
                    # Exponential backoff on errors
                    sleep_time = min(10.0 * (2 ** (consecutive_errors - 1)), 60.0)
                    time.sleep(sleep_time)
        
        if consecutive_errors >= max_consecutive_errors:
            error_msg = f"Autosave thread stopping due to {consecutive_errors} consecutive errors"
            if self.crash_logger:
                self.crash_logger.log_error(error_msg)
            else:
                print(error_msg)
    
    def emergency_save(self) -> None:
        """Execute emergency data save."""
        try:
            with self._data_lock:
                # Save pending time
                if self.selected_vn_title and self.last_start:
                    elapsed = int(time.time() - self.last_start)
                    self.data_manager.add_time(self.selected_vn_title, elapsed)
                
                # Execute emergency save
                self.data_manager.emergency_save()
            
            if self.crash_logger:
                self.crash_logger.log_info("Emergency save completed")
        except Exception as e:
            if self.crash_logger:
                self.crash_logger.log_error(f"Emergency save failed: {e}")
            else:
                print(f"Emergency save failed: {e}")
