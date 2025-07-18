"""Time tracking core functionality."""

import time
import threading
from typing import Optional, Callable, List
from enum import Enum
from ..utils.system_utils import get_last_input_time
from ..utils.data_storage import TimeDataManager
from .process_monitor import ProcessMonitor


class TrackingState(Enum):
    """Enumeration for tracking states."""
    ACTIVE = "GREEN"      # Process is active and user is not AFK
    AFK = "YELLOW"        # Process is active but user is AFK
    INACTIVE = "RED"      # Process is not active


class TimeTracker:
    def get_state(self):
        """Return the current tracking state."""
        return getattr(self, 'current_state', TrackingState.INACTIVE)
    """Core time tracking functionality."""
    
    def __init__(self, data_manager: TimeDataManager, process_monitor: ProcessMonitor):
        self.data_manager = data_manager
        self.process_monitor = process_monitor
        self.running = False
        
        # Tracking state
        self.selected_vn_title: Optional[str] = None
        self.selected_process: Optional[str] = None
        self.last_start: Optional[float] = None
        self.afk_threshold = 60  # seconds
        
        # Callbacks
        self.state_callbacks: List[Callable[[TrackingState, int], None]] = []
        self.update_callbacks: List[Callable[[], None]] = []
        
        # Threading
        self.track_thread: Optional[threading.Thread] = None
        self.autosave_thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """Start time tracking."""
        if not self.running:
            self.running = True
            self.track_thread = threading.Thread(target=self._track_loop, daemon=True)
            self.autosave_thread = threading.Thread(target=self._autosave_loop, daemon=True)
            self.track_thread.start()
            self.autosave_thread.start()
    
    def stop(self) -> None:
        """Stop time tracking."""
        if self.running:
            # Save any pending time before stopping
            if self.selected_vn_title and self.last_start:
                elapsed = int(time.time() - self.last_start)
                self.data_manager.add_time(self.selected_vn_title, elapsed)
                self.last_start = None
            
            self.running = False
            
            # Wait for threads to finish
            for thread in [self.track_thread, self.autosave_thread]:
                if thread and thread.is_alive():
                    thread.join(timeout=1.0)
    
    def set_target(self, vn_title: str, process_name: str) -> None:
        """Set the target VN and process to track."""
        # Save any pending time from previous target
        if self.selected_vn_title and self.last_start:
            elapsed = int(time.time() - self.last_start)
            self.data_manager.add_time(self.selected_vn_title, elapsed)
            self.last_start = None
        
        self.selected_vn_title = vn_title
        self.selected_process = process_name.lower() if process_name else None
    
    def set_afk_threshold(self, seconds: int) -> None:
        """Set the AFK threshold in seconds."""
        self.afk_threshold = max(0, seconds)
    
    def get_current_seconds(self) -> int:
        """Get current session seconds including any active time."""
        if not self.selected_vn_title:
            return 0
        
        base_seconds = self.data_manager.get_today_seconds(self.selected_vn_title)
        if self.last_start:
            base_seconds += int(time.time() - self.last_start)
        return base_seconds
    
    def get_today_seconds(self) -> int:
        """Get today's total seconds for selected VN."""
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
    
    def reset_today(self) -> None:
        """Reset today's time for selected VN."""
        if self.selected_vn_title:
            self.data_manager.reset_today(self.selected_vn_title)
            self.last_start = None
    
    def add_state_callback(self, callback: Callable[[TrackingState, int], None]) -> None:
        """Add callback for state changes."""
        self.state_callbacks.append(callback)
    
    def add_update_callback(self, callback: Callable[[], None]) -> None:
        """Add callback for general updates."""
        self.update_callbacks.append(callback)
    
    def _track_loop(self) -> None:
        """Main tracking loop."""
        while self.running:
            try:
                if not self.selected_process or not self.selected_vn_title:
                    self.current_state = TrackingState.INACTIVE
                    time.sleep(1)
                    continue

                # Get current state
                active_process = self.process_monitor.get_active_process()
                is_process_active = (active_process == self.selected_process)
                idle_time = get_last_input_time()

                # Determine tracking state and handle time
                if not is_process_active:
                    state = TrackingState.INACTIVE
                    if self.last_start:
                        elapsed = int(time.time() - self.last_start)
                        self.data_manager.add_time(self.selected_vn_title, elapsed)
                        self.last_start = None
                elif idle_time > self.afk_threshold:
                    state = TrackingState.AFK
                    if self.last_start:
                        elapsed = int(time.time() - self.last_start)
                        self.data_manager.add_time(self.selected_vn_title, elapsed)
                        self.last_start = None
                else:
                    state = TrackingState.ACTIVE
                    if self.last_start is None:
                        self.last_start = time.time()

                # Save current state for UI polling
                self.current_state = state

                # Get current total seconds (after state changes are applied)
                current_seconds = self.get_current_seconds()

                # Notify callbacks with the corrected time
                for callback in self.state_callbacks:
                    try:
                        callback(state, current_seconds)
                    except Exception as e:
                        print(f"状態コールバックエラー: {e}")

                for callback in self.update_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        print(f"更新コールバックエラー: {e}")

                time.sleep(1)

            except Exception as e:
                print(f"トラックエラー: {e}")
                if self.running:
                    time.sleep(1)
    
    def _autosave_loop(self) -> None:
        """Auto-save loop."""
        while self.running:
            try:
                self.data_manager.save()
                time.sleep(30)  # Increase to 30 seconds to reduce I/O
            except Exception as e:
                print(f"自動保存エラー: {e}")
                if self.running:
                    time.sleep(10)
