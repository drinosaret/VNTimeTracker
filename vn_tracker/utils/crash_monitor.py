"""Crash monitoring and debugging utilities."""

import os
import sys
import traceback
import threading
import time
import signal
import atexit
import logging
import ctypes
from datetime import datetime
from contextlib import contextmanager

# Windows-specific crash detection
if sys.platform == "win32":
    import ctypes.wintypes
    
    # Windows error mode flags
    SEM_FAILCRITICALERRORS = 0x0001
    SEM_NOALIGNMENTFAULTEXCEPT = 0x0004
    SEM_NOGPFAULTERRORBOX = 0x0002
    SEM_NOOPENFILEERRORBOX = 0x8000
    
    # Set error mode to prevent crash dialogs
    try:
        ctypes.windll.kernel32.SetErrorMode(
            SEM_FAILCRITICALERRORS | 
            SEM_NOGPFAULTERRORBOX | 
            SEM_NOOPENFILEERRORBOX
        )
    except:
        pass


class CrashMonitor:
    """Advanced crash monitoring system for debugging random crashes."""
    
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self.crash_log_file = os.path.join(log_dir, "crash_monitor.log")
        self.is_monitoring = False
        self.monitor_thread = None
        self.app_start_time = time.time()
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 5.0  # seconds
        
        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)
        
        # Setup logging
        self.setup_logging()
        
        # Register exit handlers
        atexit.register(self.on_exit)
        
        # Windows-specific crash handling
        if sys.platform == "win32":
            self.setup_windows_crash_handling()
    
    def setup_logging(self):
        """Setup crash monitor logging."""
        # Create logger for crash monitor
        self.logger = logging.getLogger("crash_monitor")
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # File handler
        handler = logging.FileHandler(self.crash_log_file, encoding='utf-8')
        handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            '%(asctime)s - CRASH_MONITOR - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        self.log(f"Crash monitor initialized - PID: {os.getpid()}")
    
    def setup_windows_crash_handling(self):
        """Setup Windows-specific crash handling."""
        try:
            # Try to set up Windows structured exception handling
            import faulthandler
            
            # Enable faulthandler
            fault_log = os.path.join(self.log_dir, "faulthandler.log")
            fault_file = open(fault_log, "w")
            faulthandler.enable(file=fault_file, all_threads=True)
            
            # Register faulthandler for common signals
            if hasattr(faulthandler, 'register'):
                try:
                    faulthandler.register(signal.SIGSEGV, file=fault_file, all_threads=True)
                except:
                    pass
                try:
                    faulthandler.register(signal.SIGFPE, file=fault_file, all_threads=True)
                except:
                    pass
            
            self.log("Windows crash handling enabled with faulthandler")
        except Exception as e:
            self.log(f"Could not setup Windows crash handling: {e}")
    
    def log(self, message: str):
        """Log a message with timestamp."""
        try:
            self.logger.info(message)
            # Also print to stderr for immediate visibility
            print(f"[CRASH_MONITOR] {message}", file=sys.stderr)
        except:
            print(f"[CRASH_MONITOR] {message}", file=sys.stderr)
    
    def start_monitoring(self):
        """Start the crash monitoring thread."""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.log("Started crash monitoring thread")
    
    def stop_monitoring(self):
        """Stop the crash monitoring."""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        self.log("Stopped crash monitoring")
    
    def heartbeat(self):
        """Call this regularly to indicate the application is alive."""
        self.last_heartbeat = time.time()
    
    def _monitor_loop(self):
        """Main monitoring loop running in background thread."""
        while self.is_monitoring:
            try:
                current_time = time.time()
                time_since_heartbeat = current_time - self.last_heartbeat
                
                if time_since_heartbeat > (self.heartbeat_interval * 3):
                    self.log(f"WARNING: No heartbeat for {time_since_heartbeat:.1f} seconds - possible hang")
                
                # Log system state periodically
                if int(current_time) % 30 == 0:  # Every 30 seconds
                    self.log_system_state()
                
                time.sleep(1)
            except Exception as e:
                self.log(f"Monitor loop error: {e}")
                time.sleep(5)
    
    def log_system_state(self):
        """Log current system state."""
        try:
            uptime = time.time() - self.app_start_time
            thread_count = threading.active_count()
            
            state_info = f"Uptime: {uptime:.1f}s, Threads: {thread_count}"
            
            # Add memory info if available
            try:
                import psutil
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent()
                state_info += f", Memory: {memory_mb:.1f}MB, CPU: {cpu_percent:.1f}%"
            except:
                pass
            
            self.log(f"System state: {state_info}")
        except Exception as e:
            self.log(f"Error logging system state: {e}")
    
    def on_exit(self):
        """Called when the application exits."""
        uptime = time.time() - self.app_start_time
        self.log(f"Application exiting normally after {uptime:.1f} seconds")
        self.stop_monitoring()


@contextmanager
def crash_protection(operation_name: str, monitor: CrashMonitor):
    """Context manager for crash protection around dangerous operations."""
    monitor.log(f"Starting protected operation: {operation_name}")
    try:
        yield
        monitor.log(f"Completed protected operation: {operation_name}")
    except Exception as e:
        monitor.log(f"Exception in {operation_name}: {type(e).__name__}: {e}")
        monitor.log(f"Traceback: {traceback.format_exc()}")
        raise


def patch_qt_application(app, monitor: CrashMonitor):
    """Patch QApplication with crash monitoring."""
    if not app:
        return
    
    # Override the exec_ method to add monitoring
    original_exec = app.exec_
    
    def monitored_exec():
        monitor.log("Qt event loop starting")
        monitor.start_monitoring()
        
        try:
            # Create a timer to send heartbeats
            from PyQt5.QtCore import QTimer
            heartbeat_timer = QTimer()
            heartbeat_timer.timeout.connect(monitor.heartbeat)
            heartbeat_timer.start(int(monitor.heartbeat_interval * 1000))
            
            result = original_exec()
            monitor.log(f"Qt event loop exited with code: {result}")
            return result
        except Exception as e:
            monitor.log(f"Exception in Qt event loop: {type(e).__name__}: {e}")
            monitor.log(f"Traceback: {traceback.format_exc()}")
            raise
        finally:
            monitor.stop_monitoring()
    
    app.exec_ = monitored_exec
    monitor.log("Patched QApplication with crash monitoring")
