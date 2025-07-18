"""Main entry point for VN Tracker application."""

import os
import sys
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from .ui.main_window_qt import VNTrackerMainWindow


def get_data_directory() -> str:
    """Get the directory for storing application data."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    """Main application entry point."""
    try:
        # Enable high DPI scaling
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        
        # Create application
        app = QApplication(sys.argv)
        app.setApplicationName("VN Tracker")
        app.setApplicationVersion("1.0")
        app.setOrganizationName("VN club Resurrection")
        
        # Setup data paths
        data_dir = get_data_directory()
        config_file = os.path.join(data_dir, "config.json")
        log_file = os.path.join(data_dir, "timelog.json")
        image_cache_dir = os.path.join(data_dir, "image_cache")
        
        # Create main window
        window = VNTrackerMainWindow(config_file, log_file, image_cache_dir)
        window.show()
        
        # Run application
        sys.exit(app.exec_())
        
    except Exception as e:
        # Show error dialog if possible
        try:
            app = QApplication(sys.argv) if 'app' not in locals() else app
            QMessageBox.critical(None, "Error", f"Application startup error: {str(e)}")
        except:
            print(f"Application startup error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
