"""Crash logging and emergency data saving utilities."""

import os
import sys
import json
import logging
import traceback
import threading
from datetime import datetime
from typing import Optional, Any, Dict, Callable
from functools import wraps


class CrashLogger:
    """Comprehensive crash logging and emergency data saving system."""
    
    def __init__(self, log_dir: str, emergency_save_callback: Optional[Callable] = None):
        """
        Initialize crash logger.
        
        Args:
            log_dir: Directory to store crash logs
            emergency_save_callback: Function to call for emergency data saving
        """
        self.log_dir = log_dir
        self.emergency_save_callback = emergency_save_callback
        self._original_excepthook = sys.excepthook
        self._lock = threading.Lock()
        
        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)
        
        # Setup file logging
        self.setup_file_logging()
        
        # Install global exception handler
        sys.excepthook = self.handle_exception
        
        # Auto cleanup old logs on startup
        self._cleanup_old_logs()
        
    def _cleanup_old_logs(self, days_to_keep: int = 30) -> None:
        """Clean up old log files automatically."""
        try:
            import glob
            import time
            
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
            
            # Patterns for files to clean up
            patterns = [
                "crash_report_*.json",
                "crash_report_*.txt", 
                "*.emergency_*",
                "vn_tracker.log.*",  # Rotated log files
            ]
            
            files_removed = 0
            for pattern in patterns:
                file_pattern = os.path.join(self.log_dir, pattern)
                for file_path in glob.glob(file_pattern):
                    try:
                        if os.path.getmtime(file_path) < cutoff_time:
                            os.remove(file_path)
                            files_removed += 1
                    except Exception:
                        pass  # Ignore errors during cleanup
            
            if files_removed > 0:
                self.logger.info(f"Cleaned up {files_removed} old log files")
                
        except Exception as e:
            # Don't let log cleanup errors affect startup
            print(f"Log cleanup warning: {e}")
        
    def setup_file_logging(self) -> None:
        """Setup file logging for the application."""
        log_file = os.path.join(self.log_dir, "vn_tracker.log")
        
        # Create logger
        self.logger = logging.getLogger("vn_tracker")
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # File handler with rotation
        try:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                log_file, 
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
        except ImportError:
            # Fallback to basic file handler
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
        
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Handle unhandled exceptions."""
        if issubclass(exc_type, KeyboardInterrupt):
            # Allow keyboard interrupts to proceed normally
            self._original_excepthook(exc_type, exc_value, exc_traceback)
            return
            
        with self._lock:
            try:
                # Emergency save data if callback is provided
                if self.emergency_save_callback:
                    try:
                        self.emergency_save_callback()
                        self.logger.info("Emergency data save completed successfully")
                    except Exception as save_error:
                        self.logger.error(f"Emergency save failed: {save_error}")
                
                # Create crash report
                crash_info = self.create_crash_report(exc_type, exc_value, exc_traceback)
                
                # Save crash report
                crash_file = self.save_crash_report(crash_info)
                
                # Log the crash
                self.logger.critical(f"UNHANDLED EXCEPTION: {exc_type.__name__}: {exc_value}")
                self.logger.critical(f"Crash report saved to: {crash_file}")
                
                # Print to stderr as well
                print(f"\n=== CRITICAL ERROR ===", file=sys.stderr)
                print(f"An unhandled exception occurred: {exc_type.__name__}: {exc_value}", file=sys.stderr)
                print(f"Crash report saved to: {crash_file}", file=sys.stderr)
                print(f"Check the log file for more details.", file=sys.stderr)
                print("=" * 50, file=sys.stderr)
                
            except Exception as logger_error:
                # If logging fails, at least print to stderr
                print(f"CRITICAL: Crash logger failed: {logger_error}", file=sys.stderr)
                print(f"Original exception: {exc_type.__name__}: {exc_value}", file=sys.stderr)
                traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        
        # Call original exception hook
        self._original_excepthook(exc_type, exc_value, exc_traceback)
    
    def create_crash_report(self, exc_type, exc_value, exc_traceback) -> Dict[str, Any]:
        """Create detailed crash report."""
        import platform
        
        crash_info = {
            "timestamp": datetime.now().isoformat(),
            "exception": {
                "type": exc_type.__name__,
                "message": str(exc_value),
                "traceback": traceback.format_exception(exc_type, exc_value, exc_traceback)
            },
            "system": {
                "platform": platform.platform(),
                "python_version": sys.version,
                "architecture": platform.architecture(),
                "processor": platform.processor(),
            },
            "application": {
                "argv": sys.argv,
                "executable": sys.executable,
                "path": sys.path,
                "working_directory": os.getcwd(),
            },
            "memory": {},
            "threads": {}
        }
        
        # Try to get memory info
        try:
            import psutil
            process = psutil.Process()
            crash_info["memory"] = {
                "memory_info": process.memory_info()._asdict(),
                "memory_percent": process.memory_percent(),
                "cpu_percent": process.cpu_percent(),
            }
        except ImportError:
            crash_info["memory"] = {"error": "psutil not available"}
        except Exception as e:
            crash_info["memory"] = {"error": str(e)}
        
        # Thread information
        try:
            crash_info["threads"] = {
                "active_count": threading.active_count(),
                "thread_names": [t.name for t in threading.enumerate()],
            }
        except Exception as e:
            crash_info["threads"] = {"error": str(e)}
        
        return crash_info
    
    def save_crash_report(self, crash_info: Dict[str, Any]) -> str:
        """Save crash report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = os.path.join(self.log_dir, f"crash_report_{timestamp}.json")
        
        try:
            with open(crash_file, "w", encoding="utf-8") as f:
                json.dump(crash_info, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            # Fallback to a simpler format
            crash_file = os.path.join(self.log_dir, f"crash_report_{timestamp}.txt")
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(f"Crash Report - {crash_info['timestamp']}\n")
                f.write("=" * 50 + "\n")
                f.write(f"Exception: {crash_info['exception']['type']}: {crash_info['exception']['message']}\n")
                f.write("\nTraceback:\n")
                f.write("".join(crash_info['exception']['traceback']))
                f.write(f"\nSystem: {crash_info['system']['platform']}\n")
                f.write(f"Python: {crash_info['system']['python_version']}\n")
        
        return crash_file
    
    def log_error(self, message: str, exc_info: bool = True) -> None:
        """Log an error with optional exception info."""
        self.logger.error(message, exc_info=exc_info)
    
    def log_warning(self, message: str) -> None:
        """Log a warning message."""
        self.logger.warning(message)
    
    def log_info(self, message: str) -> None:
        """Log an info message."""
        self.logger.info(message)
    
    def log_debug(self, message: str) -> None:
        """Log a debug message."""
        self.logger.debug(message)


def safe_execute(operation_name: str = "operation", logger: Optional[CrashLogger] = None):
    """
    Decorator to safely execute functions with error logging.
    
    Args:
        operation_name: Name of the operation for logging
        logger: CrashLogger instance to use for logging
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = f"Error in {operation_name}: {e}"
                if logger:
                    logger.log_error(error_msg)
                else:
                    print(f"ERROR: {error_msg}")
                    traceback.print_exc()
                return None
        return wrapper
    return decorator


def safe_call(func: Callable, *args, operation_name: str = "function call", 
              logger: Optional[CrashLogger] = None, default_return=None, **kwargs):
    """
    Safely call a function with error handling.
    
    Args:
        func: Function to call
        operation_name: Name of the operation for logging
        logger: CrashLogger instance to use for logging
        default_return: Value to return if function fails
        *args, **kwargs: Arguments to pass to the function
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        error_msg = f"Error in {operation_name}: {e}"
        if logger:
            logger.log_error(error_msg)
        else:
            print(f"ERROR: {error_msg}")
            traceback.print_exc()
        return default_return
