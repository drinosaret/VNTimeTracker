"""Main entry point for VN Tracker application."""

import os
import sys
import signal
import atexit
import faulthandler
import traceback
import ctypes
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

# Windows-specific crash prevention
if sys.platform == "win32":
    try:
        # Increase stack size to prevent stack overflow crashes
        import threading
        threading.stack_size(8 * 1024 * 1024)  # 8MB stack
        
        # Set Windows error mode to prevent crash dialogs
        kernel32 = ctypes.windll.kernel32
        SEM_FAILCRITICALERRORS = 0x0001
        SEM_NOGPFAULTERRORBOX = 0x0002
        SEM_NOOPENFILEERRORBOX = 0x8000
        kernel32.SetErrorMode(
            SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX
        )
    except Exception as e:
        print(f"Windows crash prevention setup failed: {e}")

from .ui.main_window_qt import VNTrackerMainWindow
from .utils.crash_logger import CrashLogger

# Global application state
_app_instance = None
_main_window = None

def emergency_shutdown():
    """Emergency shutdown procedure."""
    try:
        print("Emergency shutdown initiated...")
        if _main_window:
            _main_window.emergency_save()
        if _app_instance:
            _app_instance.quit()
    except Exception as e:
        print(f"Emergency shutdown error: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print(f"Received signal {signum}")
    emergency_shutdown()
    sys.exit(1)

def main() -> None:
    """Main application entry point."""
    global _app_instance, _main_window
    
    # Register emergency handlers
    atexit.register(emergency_shutdown)
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    # Setup comprehensive fault handling
    setup_fault_handling()
    
    try:
        print("VN Tracker starting...")
        
        # Setup data paths
        data_dir = get_data_directory()
        config_file = os.path.join(data_dir, "config.json")
        log_file = os.path.join(data_dir, "timelog.json")
        image_cache_dir = os.path.join(data_dir, "image_cache")
        logs_dir = os.path.join(data_dir, "logs")
        
        # Ensure directories exist
        for directory in [logs_dir, image_cache_dir]:
            os.makedirs(directory, exist_ok=True)
        
        # Initialize crash logger
        def emergency_save_callback():
            if _main_window and hasattr(_main_window, 'data_manager'):
                _main_window.data_manager.emergency_save()
        
        crash_logger = CrashLogger(logs_dir, emergency_save_callback)
        crash_logger.log_info("VN Tracker starting...")
        
        # Qt Application setup with error handling
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        
        _app_instance = QApplication(sys.argv)
        _app_instance.setApplicationName("VN Tracker")
        _app_instance.setApplicationVersion("1.1.0")
        _app_instance.setOrganizationName("VN club Resurrection")
        
        # Set a global exception handler for Qt
        def qt_exception_handler(exc_type, exc_value, exc_traceback):
            crash_logger.handle_exception(exc_type, exc_value, exc_traceback)
            emergency_shutdown()
        
        sys.excepthook = qt_exception_handler
        
        # Create main window with enhanced error handling
        try:
            _main_window = VNTrackerMainWindow(config_file, log_file, image_cache_dir, crash_logger)
            _main_window.show()
            crash_logger.log_info("Main window created successfully")
        except Exception as e:
            crash_logger.log_error(f"Failed to create main window: {e}")
            raise
        
        # Run application
        crash_logger.log_info("Starting Qt event loop")
        exit_code = _app_instance.exec_()
        
        crash_logger.log_info(f"Application exited with code: {exit_code}")
        return exit_code
        
    except Exception as e:
        error_msg = f"Critical application error: {e}"
        print(error_msg)
        traceback.print_exc()
        
        # Try to show error dialog
        try:
            if not _app_instance:
                _app_instance = QApplication([])
            QMessageBox.critical(None, "Critical Error", 
                               f"VN Tracker encountered a critical error:\n\n{str(e)}")
        except:
            pass
        
        return 1

def setup_fault_handling():
    """Setup comprehensive fault handling."""
    try:
        # Enable faulthandler
        data_dir = get_data_directory()
        fault_log = os.path.join(data_dir, "logs", "faulthandler.log")
        os.makedirs(os.path.dirname(fault_log), exist_ok=True)
        
        with open(fault_log, "w") as f:
            faulthandler.enable(file=f, all_threads=True)
            
        # Register signal handlers for crashes
        try:
            faulthandler.register(signal.SIGSEGV, file=f, all_threads=True)
        except (AttributeError, ValueError):
            pass  # Not available on all platforms
            
        try:
            faulthandler.register(signal.SIGFPE, file=f, all_threads=True)
        except (AttributeError, ValueError):
            pass
            
        print(f"Fault handling enabled, logging to: {fault_log}")
    except Exception as e:
        print(f"Could not setup fault handling: {e}")

def get_data_directory() -> str:
    """Get the directory for storing application data."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    sys.exit(main())
