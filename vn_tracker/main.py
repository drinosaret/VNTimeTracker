"""Main entry point for VN Tracker application."""

import os
import sys
import signal
import atexit
import faulthandler
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

from .ui.main_window_qt import VNTrackerMainWindow
from .utils.crash_logger import CrashLogger

# Enable faulthandler for crash debugging
fault_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "faulthandler.log")
os.makedirs(os.path.dirname(fault_log_path), exist_ok=True)
try:
    fault_file = open(fault_log_path, "w")
    faulthandler.enable(file=fault_file, all_threads=True)
    print(f"Faulthandler enabled, logging to: {fault_log_path}")
except Exception as e:
    print(f"Could not enable faulthandler: {e}")


def get_data_directory() -> str:
    """Get the directory for storing application data."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def safe_emergency_save(window):
    """Safe emergency save without complex crash monitoring."""
    try:
        if window and hasattr(window, 'tracker') and window.tracker:
            print("Performing emergency save...")
            window.tracker.emergency_save()
            print("Emergency save completed")
    except Exception as e:
        print(f"Emergency save failed: {e}")


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print(f"Received signal {signum}, shutting down safely...")
    # Emergency save will be handled by atexit
    sys.exit(0)


def main() -> None:
    """Simplified main application entry point."""
    window = None
    
    def cleanup():
        """Cleanup function for atexit."""
        safe_emergency_save(window)
    
    try:
        # Register cleanup
        atexit.register(cleanup)
        
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        
        print("VN Tracker starting...")
        
        # Setup data paths
        data_dir = get_data_directory()
        config_file = os.path.join(data_dir, "config.json")
        log_file = os.path.join(data_dir, "timelog.json")
        image_cache_dir = os.path.join(data_dir, "image_cache")
        logs_dir = os.path.join(data_dir, "logs")
        
        # Ensure directories exist
        os.makedirs(logs_dir, exist_ok=True)
        os.makedirs(image_cache_dir, exist_ok=True)
        
        print(f"Data directory: {data_dir}")
        print(f"Logs directory: {logs_dir}")
        
        # Initialize minimal crash logger
        crash_logger = CrashLogger(logs_dir, lambda: safe_emergency_save(window))
        crash_logger.log_info("VN Tracker starting in safe mode...")
        
        # Enable high DPI scaling
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        
        # Create application
        app = QApplication(sys.argv)
        app.setApplicationName("VN Tracker Safe")
        app.setApplicationVersion("1.0")
        app.setOrganizationName("VN club Resurrection")
        
        crash_logger.log_info("Qt Application initialized")
        print("Qt Application created successfully")
        
        # Create main window
        window = VNTrackerMainWindow(config_file, log_file, image_cache_dir, crash_logger)
        window.show()
        
        crash_logger.log_info("Main window created and shown")
        print("Main window created and shown")
        
        # Simple Qt event loop without complex monitoring
        crash_logger.log_info("Starting Qt event loop (safe mode)")
        print("Starting Qt event loop...")
        
        exit_code = app.exec_()
        
        crash_logger.log_info(f"Qt event loop exited with code: {exit_code}")
        print(f"Qt event loop exited with code: {exit_code}")
        
        sys.exit(exit_code)
        
    except Exception as e:
        error_msg = f"Application failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        
        # Try to show error dialog
        try:
            app = QApplication([])
            QMessageBox.critical(None, "Critical Error", 
                               f"VN Tracker failed to start:\n{str(e)}\n\n"
                               f"Check faulthandler.log for details.")
        except:
            pass  # If we can't show dialog, just print
        
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
