"""Main application window."""

import os
import sys
import time
import traceback
from typing import Optional, List, Dict, Any
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar,
    QTabWidget, QFrame, QGroupBox, QCheckBox, QSlider,
    QMessageBox, QFileDialog, QSystemTrayIcon, QMenu, QAction,
    QSplitter, QScrollArea, QSpinBox, QSpacerItem, QSizePolicy, QRadioButton
)
from PyQt5.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QSize, QSettings,
    QStandardPaths, pyqtSlot, QMetaType
)
from PyQt5.QtGui import QPixmap, QIcon, QFont, QPalette

from ..core.tracker import TimeTracker, TrackingState
from ..core.process_monitor import ProcessMonitor
from ..utils.config import ConfigManager
from ..utils.system_utils import format_time
from ..utils.i18n import I18nManager

# Suppress Qt threading warnings by redirecting Qt messages
def qt_message_handler(mode, context, message):
    """Filter Qt threading warnings."""
    # Suppress specific harmless warnings
    if "QBasicTimer::start: QBasicTimer can only be used with threads started with QThread" in message:
        return
    if "Cannot queue arguments of type 'QItemSelection'" in message:
        return
    print(f"Qt: {message}")

# Install the custom message handler
try:
    from PyQt5.QtCore import qInstallMessageHandler
    qInstallMessageHandler(qt_message_handler)
except ImportError:
    # Not available in this PyQt5 version
    pass


class ConstrainedSplitter(QSplitter):
    """Custom QSplitter that enforces minimum width constraints."""
    
    def __init__(self, orientation):
        super().__init__(orientation)
        self.min_widths = [380, 300, 450]  # Updated default minimums
    
    def setConstraints(self, min_widths, max_widths):
        """Set the minimum width constraints for each panel."""
        self.min_widths = min_widths[:]
        
        # Apply minimum width constraints to each widget and their content
        for i in range(self.count()):
            widget = self.widget(i)
            if widget and i < len(min_widths):
                # Set minimum width on the widget itself
                widget.setMinimumWidth(min_widths[i])
                
                # Also set minimum size policy to prevent shrinking
                widget.setSizePolicy(
                    QSizePolicy.Minimum,  # Don't allow horizontal shrinking below minimum
                    QSizePolicy.Expanding  # Can expand vertically
                )
    
    def resizeEvent(self, event):
        """Handle resize events to maintain proper proportions."""
        super().resizeEvent(event)
        
        # Only adjust if we have proper constraints set
        if len(self.min_widths) >= 3:
            current_sizes = self.sizes()
            total_width = sum(current_sizes)
            
            # Calculate minimum total width needed including handle space
            handle_space = (len(self.min_widths) - 1) * self.handleWidth()
            min_total = sum(self.min_widths) + handle_space
            
            # If window is smaller than minimum required, don't try to resize panels
            if total_width < min_total:
                return  # Let Qt handle this naturally with minimum constraints
            
            # Calculate available width for distribution
            available_width = total_width - handle_space
            
            # Use proportional sizing: 32%, 25%, 43% but respect minimums
            target_widths = [
                max(self.min_widths[0], int(available_width * 0.32)),
                max(self.min_widths[1], int(available_width * 0.25)),
                max(self.min_widths[2], int(available_width * 0.43))
            ]
            
            # Ensure total doesn't exceed available space
            total_target = sum(target_widths)
            if total_target > available_width:
                # Scale down proportionally while maintaining minimums
                excess = total_target - available_width
                
                # Try to reduce from largest panels first, but never below minimum
                for i in [2, 0, 1]:  # Right, left, middle priority
                    can_reduce = max(0, target_widths[i] - self.min_widths[i])
                    reduction = min(excess, can_reduce)
                    target_widths[i] -= reduction
                    excess -= reduction
                    if excess <= 0:
                        break
            
            # Only update if sizes have changed significantly and are valid
            # Also add a minimum threshold to prevent tiny adjustments that cause layout shifts
            if (any(abs(current_sizes[i] - target_widths[i]) > 15 for i in range(len(target_widths))) and
                all(w >= self.min_widths[i] for i, w in enumerate(target_widths))):
                # Block signals temporarily to prevent cascading layout updates
                self.blockSignals(True)
                self.setSizes(target_widths)
                self.blockSignals(False)

class VNSearchWorker(QThread):
    """Background VN search worker thread."""
    
    search_completed = pyqtSignal(list)
    
    def __init__(self, vndb_client, query: str):
        super().__init__()
        self.vndb_client = vndb_client
        self.query = query
    
    def run(self):
        """Run the search in background."""
        try:
            results = self.vndb_client.search_vn(self.query)
            self.search_completed.emit(results)
        except Exception as e:
            print(f"Search error: {e}")
            self.search_completed.emit([])


class ImageLoadWorker(QThread):
    """Background thread for loading cover images."""
    
    image_loaded = pyqtSignal(object)
    
    def __init__(self, vndb_client, title: str):
        super().__init__()
        self.vndb_client = vndb_client
        self.title = title
    
    def run(self):
        """Load image in background."""
        try:
            image = self.vndb_client.get_cover_image(self.title)
            self.image_loaded.emit(image)
        except Exception as e:
            print(f"Image load error: {e}")
            self.image_loaded.emit(None)


class VNInfoLoadWorker(QThread):
    """Background thread for loading VN info and image."""
    
    vn_info_loaded = pyqtSignal(object, object)  # (image_data, vn_info)
    
    def __init__(self, vndb_client, title: str, config_manager=None):
        super().__init__()
        self.vndb_client = vndb_client
        self.title = title
        self.config_manager = config_manager
    
    def run(self):
        """Load VN info and image in background."""
        try:
            vn_info = None
            
            # If we have a config manager, check for VNDB ID first
            if self.config_manager:
                vndb_id = self.config_manager.get_vndb_id(self.title)
                if vndb_id:
                    print(f"Found VNDB ID for '{self.title}': {vndb_id}")
                    # Try to get cached data by ID first
                    vn_info = self.vndb_client.get_vn_data_by_id(vndb_id)
                    if not vn_info:
                        # Fetch by ID from VNDB
                        vn_info = self.vndb_client.fetch_vn_by_id(vndb_id)
                    
                    # If we got data by ID but title doesn't match exactly, 
                    # update our cache with title mapping
                    if vn_info and vn_info.get("title") != self.title:
                        print(f"Updating title mapping: '{self.title}' -> '{vn_info.get('title')}'")
                        self.vndb_client.vn_data[self.title] = vn_info
                        
                else:
                    # Check if we have cached VNDB data for this title
                    cached_vndb_data = self.config_manager.get_vndb_data(self.title)
                    if cached_vndb_data:
                        print(f"Using cached VNDB data for '{self.title}'")
                        vn_info = cached_vndb_data
            
            # Fall back to regular methods if no VNDB ID or data found
            if not vn_info:
                # First try to get data from cache
                vn_info = self.vndb_client.get_vn_data(self.title)
                
                # If not in cache, fetch from VNDB
                if not vn_info:
                    vn_info = self.vndb_client.fetch_vn_details(self.title)
            
            # Get cover image (this works for both VNDB and cached VNs)
            image_data = self.vndb_client.get_cover_image(self.title)
            
            # Debug output
            print(f"VNInfoLoadWorker for '{self.title}': vn_info={bool(vn_info)}, image_data={bool(image_data)}")
            
            self.vn_info_loaded.emit(image_data, vn_info)
        except Exception as e:
            print(f"VN info load error for '{self.title}': {e}")
            import traceback
            traceback.print_exc()
            # Still try to emit with None values so UI can handle gracefully
            self.vn_info_loaded.emit(None, None)


class VNTrackerMainWindow(QMainWindow):
    """PyQt5 main window for VN Tracker."""
    
    # Add signals for thread-safe updates
    process_list_updated_signal = pyqtSignal(list)
    tracking_state_changed_signal = pyqtSignal(object, int)  # TrackingState, seconds
    tracking_updated_signal = pyqtSignal()
    
    def __init__(self, config_file: str, log_file: str, image_cache_dir: str, crash_logger=None):
        super().__init__()
        
        # Register Qt meta types to fix threading warnings (if available)
        try:
            from PyQt5.QtCore import qRegisterMetaType, QItemSelection
            # Register all common Qt types that may cause threading issues
            qRegisterMetaType('QItemSelection')
            qRegisterMetaType(QItemSelection)
            
            # Try to register other common types that might cause issues
            try:
                from PyQt5.QtCore import QModelIndex
                qRegisterMetaType('QModelIndex')
                qRegisterMetaType(QModelIndex)
            except:
                pass
                
            try:
                from PyQt5.QtWidgets import QAbstractItemView
                qRegisterMetaType('QAbstractItemView::SelectionFlag')
            except:
                pass
        except ImportError:
            # qRegisterMetaType not available in this PyQt5 version, skip registration
            pass
        
        # Track startup timing
        import time
        self.startup_time = time.time()
        
        # Store initialization parameters
        self.log_file = log_file
        self.image_cache_dir = image_cache_dir
        self.crash_logger = crash_logger
        
        # Initialize lightweight managers first
        self.config_manager = ConfigManager(config_file)
        self.i18n = I18nManager(self.config_manager)
        
        # Initialize heavy components later
        self.data_manager = None
        self.process_monitor = None
        self.vndb_client = None
        self.tracker = None
        self.overlay = None
        self.update_timer = None

        # System tray - will be set up after icon loading
        self.tray_icon = None        # Worker threads
        self.search_worker = None
        self.vn_info_worker = None
        self.vndb_search_results = []  # Store search results for VNDB VN addition
        
        # State for preserving time display when stopping tracking
        self.last_displayed_vn = None
        self.last_displayed_time = 0
        
        # Setup UI first (fastest)
        self.setup_ui()
        self.setup_connections()
        
        # Lock window resizing during initialization to prevent layout shifts
        self.setFixedSize(self.size())
        
        # Show window immediately
        ui_ready_time = time.time()
        print(f"UI ready in {ui_ready_time - self.startup_time:.3f} seconds")
        
        # Set proper splitter sizes immediately to prevent layout shifts
        self.setup_splitter_sizes()
        
        # Initialize heavy components asynchronously
        QTimer.singleShot(100, self.initialize_heavy_components)
    
    def setup_dpi_scaling(self):
        """Setup DPI scaling for high resolution displays."""
        try:
            from PyQt5.QtWidgets import QApplication, QDesktopWidget
            
            # Check for manual scale override first
            manual_scale = self.config_manager.get("ui_scale_override", None)
            if manual_scale and isinstance(manual_scale, (int, float)):
                self.scale_factor = float(manual_scale) / 100.0
                print(f"Using manual UI scale override: {self.scale_factor:.2f}x")
            else:
                # Use automatic DPI detection
                app = QApplication.instance()
                if app and app.property("scale_factor"):
                    self.scale_factor = float(app.property("scale_factor"))
                else:
                    # Fallback DPI detection
                    desktop = QDesktopWidget()
                    dpi = desktop.logicalDpiX()
                    self.scale_factor = max(1.0, dpi / 96.0)
                
                print(f"Automatic UI scale factor: {self.scale_factor:.2f}x")
            
            # Cap scale factor to reasonable limits
            self.scale_factor = min(self.scale_factor, 3.0)  # Max 3x scaling
            self.scale_factor = max(self.scale_factor, 1.0)  # Min 1x scaling
            
            # Calculate scaled sizes for common UI elements
            self.scaled_font_size = max(8, int(9 * self.scale_factor))
            self.scaled_large_font_size = max(10, int(14 * self.scale_factor))
            self.scaled_button_height = int(32 * self.scale_factor)
            self.scaled_spacing = int(8 * self.scale_factor)
            self.scaled_margins = int(6 * self.scale_factor)
            
        except Exception as e:
            print(f"DPI scaling setup failed: {e}")
            # Fallback values
            self.scale_factor = 1.0
            self.scaled_font_size = 9
            self.scaled_large_font_size = 14
            self.scaled_button_height = 32
            self.scaled_spacing = 8
            self.scaled_margins = 6
    
    def setup_ui(self):
        """Setup the user interface with PyQt5."""
        # Detect DPI scaling and adjust UI accordingly
        self.setup_dpi_scaling()
        
        self.setWindowTitle(self.i18n.t("app_title"))
        self.setMinimumSize(int(1200 * self.scale_factor), int(700 * self.scale_factor))
        self.resize(int(1300 * self.scale_factor), int(750 * self.scale_factor))
        
        # Set application icon
        self.set_application_icon()
        
        # Setup system tray after icon is loaded
        self.setup_system_tray()
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout - horizontal splitter for three panels
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        splitter = ConstrainedSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)  # Prevent panels from collapsing completely
        splitter.setHandleWidth(6)  # Slightly smaller handle
        
        # Splitter styling
        splitter.setStyleSheet(
            """
            QSplitter::handle {
                background-color: #cccccc;
                border: 1px solid #aaaaaa;
                margin: 1px;
                padding: 0px;
            }
            QSplitter::handle:horizontal {
                width: 6px;
            }
            QSplitter {
                background: transparent;
            }
            """
        )
        main_layout.addWidget(splitter)
        
        # Left panel - VN Selection and Library Management
        self.create_selection_panel(splitter)
        
        # Middle panel - Cover Image  
        self.create_cover_image_panel(splitter)
        
        # Right panel - Time Tracking and Settings
        self.create_tracking_panel(splitter)
        
        # Store splitter reference for easy access
        self.main_splitter = splitter
        
        # Set realistic constraints based on actual content needs
        # Left panel needs space for buttons, dropdowns, and labels with proper margins
        # Middle panel needs space for 200px image plus margins and group box borders
        # Right panel needs space for time display, statistics, tabs, and buttons
        # Scale all minimum widths with DPI
        min_widths = [
            int(380 * self.scale_factor), 
            int(300 * self.scale_factor), 
            int(450 * self.scale_factor)
        ]
        max_widths = [
            int(500 * self.scale_factor), 
            int(400 * self.scale_factor), 
            None  # No max for right panel
        ]
        splitter.setConstraints(min_widths, max_widths)
        
        # Strictly prevent collapsing for all panels
        splitter.setCollapsible(0, False)  # Left panel cannot collapse
        splitter.setCollapsible(1, False)  # Middle panel cannot collapse
        splitter.setCollapsible(2, False)  # Right panel cannot collapse
        
        # Apply modern styling
        self.apply_modern_style()
    
    def setup_splitter_sizes(self):
        """Set up proper splitter sizes after the window is shown."""
        if hasattr(self, 'main_splitter'):
            # Get the current window width to calculate proportional sizes
            window_width = self.width()
            
            # Calculate available width (subtract space for handles)
            handle_space = (self.main_splitter.count() - 1) * self.main_splitter.handleWidth()
            available_width = window_width - handle_space - 20  # 20px margin
            
            # Use proportional sizing: 35%, 28%, 37% but scale minimum values with DPI
            left_size = max(int(350 * self.scale_factor), int(available_width * 0.35))
            middle_size = max(int(280 * self.scale_factor), int(available_width * 0.28))
            right_size = max(int(420 * self.scale_factor), available_width - left_size - middle_size)
            
            target_sizes = [left_size, middle_size, right_size]
            
            print(f"Window width: {window_width}, Available: {available_width}")
            print(f"Setting splitter sizes: {target_sizes}")
            
            # Block layout signals while setting sizes to prevent recursive updates
            self.main_splitter.blockSignals(True)
            self.main_splitter.setSizes(target_sizes)
            self.main_splitter.blockSignals(False)
    
    def create_selection_panel(self, parent):
        """Create the VN selection panel with library management."""
        # Create scroll area for the selection panel
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        selection_widget = QWidget()
        layout = QVBoxLayout(selection_widget)
        # Set realistic minimum width based on content requirements:
        # - Two buttons side by side (130px each + 15px spacing = 275px)
        # - Plus margins (12px * 2 = 24px) and group box padding (20px * 2 = 40px)
        # - Plus some buffer = 350px minimum, scaled for DPI
        selection_widget.setMinimumWidth(int(380 * self.scale_factor))  # Scale with DPI
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)  # Proper margins for good spacing
        
        # === MANAGE LIBRARY SECTION ===
        library_group = QGroupBox(self.i18n.t("manage_library"))
        library_group.setObjectName("library_group")
        library_layout = QVBoxLayout(library_group)
        library_layout.setSpacing(12)  # Reduced from 15px to 12px for more compact feel
        library_layout.setContentsMargins(20, 15, 20, 20)  # More balanced padding
        
        # Add VN buttons with better spacing
        add_buttons_layout = QHBoxLayout()
        add_buttons_layout.setSpacing(15)  # Increased space between buttons
        self.add_manual_button = QPushButton(self.i18n.t("add_manually"))
        self.add_manual_button.setMinimumHeight(int(40 * self.scale_factor))  # Slightly taller buttons
        self.add_manual_button.setMinimumWidth(int(130 * self.scale_factor))  # Consistent width
        self.add_vndb_button = QPushButton(self.i18n.t("add_from_vndb"))
        self.add_vndb_button.setMinimumHeight(int(40 * self.scale_factor))
        self.add_vndb_button.setMinimumWidth(int(130 * self.scale_factor))  # Consistent width
        
        add_buttons_layout.addWidget(self.add_manual_button)
        add_buttons_layout.addItem(QSpacerItem(15, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))
        add_buttons_layout.addWidget(self.add_vndb_button)
        library_layout.addLayout(add_buttons_layout)
        
        # Add more spacing after main buttons
        library_layout.addSpacing(12)  # Reduced from 15px to 12px
        
        # Manual VN input (initially hidden)
        self.manual_input_widget = QWidget()
        self.manual_input_widget.setVisible(False)
        manual_input_layout = QVBoxLayout(self.manual_input_widget)
        manual_input_layout.setContentsMargins(5, 5, 5, 5)
        manual_input_layout.setSpacing(8)
        
        # Title input with proper spacing
        manual_input_layout.addWidget(QLabel("Enter VN title:"))
        
        manual_buttons_layout = QHBoxLayout()
        manual_buttons_layout.setSpacing(8)
        self.manual_vn_entry = QLineEdit()
        self.manual_vn_entry.setPlaceholderText(self.i18n.t("enter_title"))
        self.manual_vn_entry.setMinimumHeight(int(32 * self.scale_factor))
        self.confirm_manual_button = QPushButton(self.i18n.t("add_vn"))
        self.confirm_manual_button.setMaximumWidth(int(90 * self.scale_factor))  # Increased width for "Add VN" text
        self.confirm_manual_button.setMinimumHeight(int(32 * self.scale_factor))
        self.cancel_manual_button = QPushButton("Cancel")
        self.cancel_manual_button.setMaximumWidth(int(80 * self.scale_factor))
        self.cancel_manual_button.setMinimumHeight(int(32 * self.scale_factor))
        
        manual_buttons_layout.addWidget(self.manual_vn_entry, 1)
        manual_buttons_layout.addWidget(self.confirm_manual_button)
        manual_buttons_layout.addWidget(self.cancel_manual_button)
        manual_input_layout.addLayout(manual_buttons_layout)
        
        library_layout.addWidget(self.manual_input_widget)
        
        # VNDB search widget (initially hidden)
        self.vndb_search_widget = QWidget()
        self.vndb_search_widget.setVisible(False)
        vndb_search_layout = QVBoxLayout(self.vndb_search_widget)
        vndb_search_layout.setContentsMargins(5, 5, 5, 5)
        vndb_search_layout.setSpacing(8)
        
        # Search label
        vndb_search_layout.addWidget(QLabel("Search VNDB:"))
        
        # Search input with proper spacing
        search_input_layout = QHBoxLayout()
        search_input_layout.setSpacing(8)
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search VNDB...")
        self.search_entry.setMinimumHeight(int(32 * self.scale_factor))
        self.search_button = QPushButton(self.i18n.t("search"))
        self.search_button.setMinimumWidth(int(85 * self.scale_factor))  # Ensure button is wide enough for both "Search" and "Working..." states
        self.search_button.setMaximumWidth(int(100 * self.scale_factor))  # Increased to accommodate "Searching..." text
        self.search_button.setMinimumHeight(int(32 * self.scale_factor))
        self.cancel_vndb_button = QPushButton("Cancel")
        self.cancel_vndb_button.setMaximumWidth(int(80 * self.scale_factor))
        self.cancel_vndb_button.setMinimumHeight(int(32 * self.scale_factor))
        
        search_input_layout.addWidget(self.search_entry, 1)
        search_input_layout.addWidget(self.search_button)
        search_input_layout.addWidget(self.cancel_vndb_button)
        vndb_search_layout.addLayout(search_input_layout)
        
        # VNDB results with spacing
        vndb_search_layout.addSpacing(5)
        vndb_search_layout.addWidget(QLabel("Select from results:"))
        self.vndb_results_dropdown = QComboBox()
        self.vndb_results_dropdown.setMinimumHeight(int(35 * self.scale_factor))
        vndb_search_layout.addWidget(self.vndb_results_dropdown)
        
        vndb_search_layout.addSpacing(5)
        
        # Add selected VNDB VN button
        self.add_selected_vndb_button = QPushButton("Add Selected VN to Library")
        self.add_selected_vndb_button.setMinimumHeight(int(35 * self.scale_factor))
        self.add_selected_vndb_button.setMinimumWidth(int(200 * self.scale_factor))  # Ensure enough width for long text
        vndb_search_layout.addWidget(self.add_selected_vndb_button)
        
        library_layout.addWidget(self.vndb_search_widget)
        
        # Delete current VN button with better spacing
        library_layout.addSpacing(12)  # Reduced from 20px to 12px
        
        # Add a separator line for visual separation
        separator_line = QFrame()
        separator_line.setFrameShape(QFrame.HLine)
        separator_line.setFrameShadow(QFrame.Sunken)
        separator_line.setStyleSheet("color: #cccccc;")
        library_layout.addWidget(separator_line)
        
        library_layout.addSpacing(10)  # Reduced from 15px to 10px
        
        delete_layout = QHBoxLayout()
        delete_layout.setSpacing(10)
        
        self.remove_vn_button = QPushButton(self.i18n.t("remove_vn"))
        self.remove_vn_button.setMinimumHeight(int(40 * self.scale_factor))  # Match other buttons
        self.remove_vn_button.setMinimumWidth(int(180 * self.scale_factor))  # Slightly wider for the longer text
        self.remove_vn_button.setMaximumWidth(int(250 * self.scale_factor))
        
        delete_layout.addWidget(self.remove_vn_button)
        delete_layout.addStretch()  # Push button to the left
        library_layout.addLayout(delete_layout)
        
        layout.addWidget(library_group)
        
        # Add spacing between sections
        layout.addSpacing(15)
        
        # === SELECT VN SECTION ===
        selection_group = QGroupBox(self.i18n.t("select_vn"))
        selection_group.setObjectName("selection_group")
        selection_layout = QVBoxLayout(selection_group)
        selection_layout.setSpacing(10)
        selection_layout.setContentsMargins(15, 12, 15, 15)
        
        # VN selection dropdown with label spacing
        selection_layout.addWidget(QLabel("Choose VN from your library:"))
        selection_layout.addSpacing(5)
        self.vn_dropdown = QComboBox()
        self.vn_dropdown.setMinimumHeight(int(35 * self.scale_factor))
        selection_layout.addWidget(self.vn_dropdown)
        
        # Process selection with proper spacing
        selection_layout.addSpacing(12)
        selection_layout.addWidget(QLabel(self.i18n.t("select_process")))
        selection_layout.addSpacing(5)
        
        process_selection_layout = QHBoxLayout()
        process_selection_layout.setSpacing(10)
        self.process_dropdown = QComboBox()
        self.process_dropdown.setMinimumHeight(int(35 * self.scale_factor))
        self.refresh_processes_button = QPushButton("Refresh")
        self.refresh_processes_button.setMaximumWidth(int(100 * self.scale_factor))
        self.refresh_processes_button.setMinimumHeight(int(35 * self.scale_factor))
        self.refresh_processes_button.setToolTip("Refresh process list to include newly started programs")
        
        process_selection_layout.addWidget(self.process_dropdown, 1)
        process_selection_layout.addWidget(self.refresh_processes_button, 0)
        selection_layout.addLayout(process_selection_layout)
        
        # Start tracking button with spacing
        selection_layout.addSpacing(15)
        self.set_target_button = QPushButton(self.i18n.t("select_game_process"))
        self.set_target_button.setMinimumHeight(int(40 * self.scale_factor))  # Prominent button
        selection_layout.addWidget(self.set_target_button)
        
        layout.addWidget(selection_group)
        
        # Status and loading labels with proper spacing
        layout.addSpacing(12)
        
        # Status label
        self.status_label = QLabel(f"{self.i18n.t('tracking')}: {self.i18n.t('not_selected')}")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(int(20 * self.scale_factor))
        layout.addWidget(self.status_label)
        
        # Loading indicator with fixed size to prevent layout shifts
        layout.addSpacing(8)
        self.loading_label = QLabel("🔄 Loading components...        ")
        self.loading_label.setStyleSheet("color: #0078d4; font-weight: bold; margin: 0px; padding: 3px;")
        self.loading_label.setWordWrap(True)
        self.loading_label.setFixedHeight(int(25 * self.scale_factor))  # Scale height with DPI
        self.loading_label.setMinimumWidth(int(200 * self.scale_factor))
        self.loading_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.loading_label.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.loading_label)
        
        # Add stretch to push everything up
        layout.addStretch()
        
        # Set the widget to the scroll area and add to parent
        scroll_area.setWidget(selection_widget)
        # Clear margins for clean appearance
        scroll_area.setContentsMargins(0, 0, 0, 0)
        scroll_area.setMinimumWidth(int(350 * self.scale_factor))
        parent.addWidget(scroll_area)
    
    def create_cover_image_panel(self, parent):
        """Create the cover image and VN info panel."""
        # Create scroll area for the cover panel to match left panel structure
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        cover_widget = QWidget()
        cover_main_layout = QVBoxLayout(cover_widget)
        cover_main_layout.setContentsMargins(12, 12, 12, 12)  # Proper margins for good spacing
        cover_main_layout.setSpacing(8)

        # Set minimum width based on content requirements:
        # - Image size (200px) + margins (12px * 2) + group box padding (15px * 2) + buffer = 260px
        cover_widget.setMinimumWidth(int(300 * self.scale_factor))  # Scale with DPI
        
        # Cover image section
        cover_group = QGroupBox(self.i18n.t("cover_image"))
        cover_layout = QVBoxLayout(cover_group)
        cover_layout.setContentsMargins(15, 12, 15, 15)
        cover_layout.setSpacing(8)
        
        # Create horizontal layout to center the image
        cover_h_layout = QHBoxLayout()
        cover_h_layout.addStretch()  # Left spacer
        
        self.cover_label = QLabel()
        # Scale cover image size with DPI but keep reasonable proportions
        cover_width = int(200 * self.scale_factor)
        cover_height = int(280 * self.scale_factor)
        self.cover_label.setFixedSize(cover_width, cover_height)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setScaledContents(False)  # Keep aspect ratio
        self.cover_label.setStyleSheet("border: 1px solid #cccccc; background-color: #ffffff; color: #666666; padding: 8px;")
        self.cover_label.setText("No Image")
        
        cover_h_layout.addWidget(self.cover_label)
        cover_h_layout.addStretch()  # Right spacer
        
        cover_layout.addLayout(cover_h_layout)
        cover_main_layout.addWidget(cover_group)
        
        # VN Info section
        self.create_vn_info_section(cover_main_layout)
        
        # Add stretch to push content to top
        cover_main_layout.addStretch()
        
        # Set the widget to the scroll area and add to parent
        scroll_area.setWidget(cover_widget)
        # Clear margins for clean appearance
        scroll_area.setContentsMargins(0, 0, 0, 0)
        scroll_area.setMinimumWidth(int(280 * self.scale_factor))
        parent.addWidget(scroll_area)
    
    def create_vn_info_section(self, parent_layout):
        """Create the VN information section."""
        info_group = QGroupBox("VN Information")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(15, 12, 15, 15)
        info_layout.setSpacing(8)
        
        # Title
        self.vn_title_label = QLabel("Title: Not Selected")
        self.vn_title_label.setWordWrap(True)
        self.vn_title_label.setStyleSheet("font-weight: bold; color: #333333;")
        info_layout.addWidget(self.vn_title_label)
        
        # Description (scrollable)
        desc_container = QWidget()
        desc_layout = QVBoxLayout(desc_container)
        desc_layout.setContentsMargins(0, 0, 0, 0)
        desc_layout.setSpacing(4)
        
        desc_label = QLabel("Description:")
        desc_label.setStyleSheet("font-weight: bold; color: #333333;")
        desc_layout.addWidget(desc_label)
        
        self.vn_description_label = QLabel("No description available")
        self.vn_description_label.setWordWrap(True)
        self.vn_description_label.setAlignment(Qt.AlignTop)
        self.vn_description_label.setMaximumHeight(int(140 * self.scale_factor))  # Increased height for better text display
        self.vn_description_label.setStyleSheet("color: #555555; padding: 4px; background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 3px;")
        desc_layout.addWidget(self.vn_description_label)
        
        info_layout.addWidget(desc_container)
        
        # Release Date
        self.vn_release_label = QLabel("Release Date: Unknown")
        self.vn_release_label.setStyleSheet("color: #333333;")
        info_layout.addWidget(self.vn_release_label)
        
        # Rating
        self.vn_rating_label = QLabel("Rating: Not Rated")
        self.vn_rating_label.setStyleSheet("color: #333333;")
        info_layout.addWidget(self.vn_rating_label)
        
        # Developer
        self.vn_developer_label = QLabel("Developer: Unknown")
        self.vn_developer_label.setWordWrap(True)
        self.vn_developer_label.setStyleSheet("color: #333333;")
        info_layout.addWidget(self.vn_developer_label)
        
        # Length
        self.vn_length_label = QLabel("Length: Unknown")
        self.vn_length_label.setStyleSheet("color: #333333;")
        info_layout.addWidget(self.vn_length_label)
        
        parent_layout.addWidget(info_group)
    
    def create_tracking_panel(self, parent):
        """Create the tracking and settings panel."""
        tracking_widget = QWidget()
        layout = QVBoxLayout(tracking_widget)
        layout.setSpacing(self.scaled_spacing)  # Scale spacing between major sections
        layout.setContentsMargins(self.scaled_margins, self.scaled_margins, self.scaled_margins, self.scaled_margins)
        
        tracking_widget.setMinimumWidth(int(450 * self.scale_factor))
        
        # Time display
        time_group = QGroupBox(self.i18n.t("time_tracking"))
        time_layout = QVBoxLayout(time_group)
        time_layout.setSpacing(6)  # Moderate spacing within time group
        time_layout.setContentsMargins(12, 8, 12, 8)  # Reasonable margins
        
        self.time_label = QLabel(f"{self.i18n.t('today_reading_time')}: 00:00:00")
        self.time_label.setObjectName("time_label")  # Add object name for specific styling
        font = QFont()
        font.setPointSize(self.scaled_large_font_size)
        font.setBold(True)
        self.time_label.setFont(font)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setWordWrap(True)  # Enable word wrapping
        self.time_label.setMinimumHeight(int(40 * self.scale_factor))  # Scale minimum height
        time_layout.addWidget(self.time_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(self.config_manager.goal_minutes * 60)
        self.progress_bar.setTextVisible(True)
        time_layout.addWidget(self.progress_bar)
        
        layout.addWidget(time_group)
        
        # Statistics
        stats_group = QGroupBox(self.i18n.t("statistics"))
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setSpacing(4)  # Moderate spacing between statistics
        stats_layout.setContentsMargins(12, 8, 12, 8)  # Reasonable margins
        
        self.week_label = QLabel(f"{self.i18n.t('weekly')}: 0 {self.i18n.t('minutes')}")
        self.month_label = QLabel(f"{self.i18n.t('monthly')}: 0 {self.i18n.t('minutes')}")
        self.total_label = QLabel(f"{self.i18n.t('total')}: 0 {self.i18n.t('minutes')}")
        
        stats_layout.addWidget(self.week_label)
        stats_layout.addWidget(self.month_label)
        stats_layout.addWidget(self.total_label)
        
        layout.addWidget(stats_group)
        
        # Settings tabs
        self.create_settings_tabs(layout)
        
        # Action buttons
        self.create_action_buttons(layout)
        
        # Simple minimum width constraint only
        tracking_widget.setMinimumWidth(int(420 * self.scale_factor))
        
        parent.addWidget(tracking_widget)
    
    def create_settings_tabs(self, layout):
        """Create settings tabs."""
        tab_widget = QTabWidget()
        
        # Configure tab widget for better narrow space handling
        tab_widget.setUsesScrollButtons(True)  # Enable scroll buttons when tabs don't fit
        tab_widget.setElideMode(Qt.ElideNone)  # Don't elide tab text
        tab_widget.setTabsClosable(False)  # No close buttons
        tab_widget.setMovable(False)  # Tabs can't be moved
        
        # Goal settings tab
        goal_tab = QWidget()
        goal_layout = QVBoxLayout(goal_tab)
        goal_layout.setSpacing(8)  # Moderate spacing between groups
        goal_layout.setContentsMargins(10, 10, 10, 10)  # Reasonable margins for tab content
        
        # Goal time setting
        goal_group = QGroupBox(self.i18n.t("goal_time"))
        goal_group_layout = QHBoxLayout(goal_group)
        goal_group_layout.setContentsMargins(10, 6, 10, 6)  # Moderate margins
        
        self.goal_spinbox = QSpinBox()
        self.goal_spinbox.setRange(1, 999)
        self.goal_spinbox.setValue(self.config_manager.goal_minutes)
        self.goal_spinbox.setSuffix(" minutes")
        
        goal_set_button = QPushButton(self.i18n.t("set_goal"))
        goal_set_button.clicked.connect(self.set_goal)
        
        goal_group_layout.addWidget(self.goal_spinbox)
        goal_group_layout.addWidget(goal_set_button)
        goal_layout.addWidget(goal_group)
        
        # AFK threshold setting
        afk_group = QGroupBox(self.i18n.t("afk_threshold"))
        afk_group_layout = QHBoxLayout(afk_group)
        afk_group_layout.setContentsMargins(10, 6, 10, 6)  # Moderate margins
        
        self.afk_spinbox = QSpinBox()
        self.afk_spinbox.setRange(0, 9999)
        self.afk_spinbox.setValue(self.config_manager.afk_threshold)
        self.afk_spinbox.setSuffix(" seconds")
        
        afk_set_button = QPushButton(self.i18n.t("set_afk_threshold"))
        afk_set_button.clicked.connect(self.set_afk_threshold)
        
        afk_group_layout.addWidget(self.afk_spinbox)
        afk_group_layout.addWidget(afk_set_button)
        goal_layout.addWidget(afk_group)
        
        goal_layout.addStretch()
        tab_widget.addTab(goal_tab, "Goals")  # Shorter tab name
        
        # Overlay settings tab
        overlay_tab = QWidget()
        overlay_layout = QVBoxLayout(overlay_tab)
        overlay_layout.setSpacing(8)  # Moderate spacing between elements
        overlay_layout.setContentsMargins(10, 10, 10, 10)  # Reasonable tab margins
        
        self.overlay_checkbox = QCheckBox(self.i18n.t("show_overlay"))
        self.overlay_checkbox.setChecked(self.config_manager.show_overlay)
        overlay_layout.addWidget(self.overlay_checkbox)
        
        # Overlay percentage checkbox
        self.overlay_percentage_checkbox = QCheckBox(self.i18n.t("show_overlay_percentage"))
        self.overlay_percentage_checkbox.setChecked(self.config_manager.show_overlay_percentage)
        overlay_layout.addWidget(self.overlay_percentage_checkbox)
        
        # Overlay transparency
        transparency_group = QGroupBox(self.i18n.t("overlay_transparency"))
        transparency_layout = QVBoxLayout(transparency_group)
        transparency_layout.setSpacing(4)  # Moderate spacing within group
        transparency_layout.setContentsMargins(10, 6, 10, 6)  # Reasonable margins
        
        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setRange(10, 100)
        self.transparency_slider.setValue(int(self.config_manager.overlay_alpha * 100))
        
        self.transparency_label = QLabel(f"{int(self.config_manager.overlay_alpha * 100)}%")
        
        transparency_layout.addWidget(self.transparency_slider)
        transparency_layout.addWidget(self.transparency_label)
        overlay_layout.addWidget(transparency_group)
        
        overlay_layout.addStretch()
        tab_widget.addTab(overlay_tab, "Overlay")  # Shorter tab name
        
        # Language settings tab
        language_tab = QWidget()
        language_layout = QVBoxLayout(language_tab)
        language_layout.setSpacing(8)  # Moderate spacing
        language_layout.setContentsMargins(10, 10, 10, 10)  # Reasonable tab margins
        
        lang_group = QGroupBox(self.i18n.t("language"))
        lang_group_layout = QVBoxLayout(lang_group)
        lang_group_layout.setSpacing(4)  # Moderate spacing within group
        lang_group_layout.setContentsMargins(10, 6, 10, 6)  # Reasonable margins
        
        self.language_dropdown = QComboBox()
        languages = self.i18n.get_available_languages()
        for code, name in languages.items():
            self.language_dropdown.addItem(name, code)
        
        # Set current language
        current_lang = self.i18n.get_language()
        for i in range(self.language_dropdown.count()):
            if self.language_dropdown.itemData(i) == current_lang:
                self.language_dropdown.setCurrentIndex(i)
                break
        
        lang_set_button = QPushButton(self.i18n.t("set_language"))
        lang_set_button.clicked.connect(self.set_language)
        
        lang_group_layout.addWidget(self.language_dropdown)
        lang_group_layout.addWidget(lang_set_button)
        language_layout.addWidget(lang_group)
        
        language_layout.addStretch()
        tab_widget.addTab(language_tab, "Language")  # Shorter tab name
        
        # Display settings tab
        display_tab = QWidget()
        display_layout = QVBoxLayout(display_tab)
        display_layout.setSpacing(8)
        display_layout.setContentsMargins(10, 10, 10, 10)
        
        # UI Scale group
        scale_group = QGroupBox("UI Scale")
        scale_group_layout = QVBoxLayout(scale_group)
        scale_group_layout.setSpacing(4)
        scale_group_layout.setContentsMargins(10, 6, 10, 6)
        
        # Show current DPI info
        try:
            from PyQt5.QtWidgets import QDesktopWidget
            desktop = QDesktopWidget()
            dpi = desktop.logicalDpiX()
            dpi_info = QLabel(f"Detected DPI: {dpi} (Scale: {self.scale_factor:.2f}x)")
            dpi_info.setStyleSheet("color: #666666; font-size: 8pt;")
            scale_group_layout.addWidget(dpi_info)
        except:
            pass
        
        # Manual scale override
        scale_override_layout = QHBoxLayout()
        scale_override_layout.addWidget(QLabel("Manual Scale:"))
        
        self.scale_override_spinbox = QSpinBox()
        self.scale_override_spinbox.setRange(100, 300)  # 100% to 300%
        self.scale_override_spinbox.setValue(int(self.scale_factor * 100))
        self.scale_override_spinbox.setSuffix("%")
        self.scale_override_spinbox.setToolTip("Override automatic scaling (requires restart)")
        
        scale_apply_button = QPushButton("Apply Scale")
        scale_apply_button.clicked.connect(self.set_ui_scale_override)
        
        scale_override_layout.addWidget(self.scale_override_spinbox)
        scale_override_layout.addWidget(scale_apply_button)
        scale_group_layout.addLayout(scale_override_layout)
        
        # Note about restart
        restart_note = QLabel("Note: Scale changes require application restart")
        restart_note.setStyleSheet("color: #666666; font-size: 8pt; font-style: italic;")
        restart_note.setWordWrap(True)
        scale_group_layout.addWidget(restart_note)
        
        display_layout.addWidget(scale_group)
        display_layout.addStretch()
        tab_widget.addTab(display_tab, "Display")
        
        layout.addWidget(tab_widget)
    
    def create_action_buttons(self, layout):
        """Create action buttons."""
        # Add some spacing before buttons
        layout.addSpacing(6)
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(6)  # Moderate spacing between buttons
        button_layout.setContentsMargins(8, 6, 8, 8)  # Reasonable margins around button area
        
        self.reset_button = QPushButton(self.i18n.t("reset_today"))
        self.export_button = QPushButton(self.i18n.t("export_data"))
        self.minimize_tray_button = QPushButton(self.i18n.t("minimize_to_tray"))
        
        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.minimize_tray_button)
        
        layout.addLayout(button_layout)
    
    def apply_modern_style(self):
        """Apply modern light theme styling with DPI-aware sizing."""
        # Calculate scaled values for the stylesheet
        base_font_size = self.scaled_font_size
        button_padding = int(8 * self.scale_factor)
        # Keep button height reasonable - not too tall
        button_min_height = max(int(28 * self.scale_factor), base_font_size + (button_padding * 2))
        input_padding = int(5 * self.scale_factor)
        # Make tabs more compact but ensure text fits
        tab_padding_v = max(int(5 * self.scale_factor), base_font_size + 1)  # More compact vertical padding
        tab_padding_h = max(int(8 * self.scale_factor), base_font_size * 1.2)  # More compact horizontal padding
        tab_padding = f"{tab_padding_v}px {tab_padding_h}px"
        
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: #f0f0f0;
                color: #333333;
                font-size: {base_font_size}pt;
            }}
            QGroupBox {{
                font-weight: bold;
                font-size: {base_font_size}pt;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin: 5px 0px;
                padding-top: {int(15 * self.scale_factor)}px;
                padding-bottom: {int(10 * self.scale_factor)}px;
                background-color: #ffffff;
                color: #333333;
            }}
            /* Ensure consistent styling for all group boxes */
            QGroupBox[objectName="search_group"] {{
                background-color: #ffffff;
                border: 2px solid #cccccc;
                border-radius: 5px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {int(22 * self.scale_factor)}px;
                padding: 0 {int(5 * self.scale_factor)}px 0 {int(5 * self.scale_factor)}px;
                color: #333333;
                font-size: {base_font_size}pt;
            }}
            QPushButton {{
                background-color: #0078d4;
                border: none;
                color: white;
                padding: {button_padding}px {button_padding * 2}px;
                border-radius: 4px;
                font-weight: bold;
                font-size: {base_font_size}pt;
                min-height: {button_min_height}px;
                line-height: {int(base_font_size * 1.2)}px;
            }}
            QPushButton:hover {{
                background-color: #106ebe;
            }}
            QPushButton:pressed {{
                background-color: #005a9e;
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
                color: #666666;
            }}
            QLineEdit, QComboBox, QSpinBox {{
                background-color: #ffffff;
                border: 1px solid #cccccc;
                color: #333333;
                padding: {input_padding}px;
                border-radius: 3px;
                selection-background-color: #0078d4;
                font-size: {base_font_size}pt;
                min-height: {max(int(24 * self.scale_factor), base_font_size + (input_padding * 2))}px;
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
                border: 2px solid #0078d4;
            }}
            QTabWidget::pane {{
                border: 1px solid #cccccc;
                background-color: #ffffff;
            }}
            QTabBar::tab {{
                background-color: #e0e0e0;
                color: #333333;
                padding: {tab_padding};
                margin-right: 1px;
                border: 1px solid #cccccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: {base_font_size}pt;
                min-height: {max(int(16 * self.scale_factor), base_font_size + 2)}px;
                min-width: {max(int(70 * self.scale_factor), base_font_size * 4)}px;
                max-width: {max(int(90 * self.scale_factor), base_font_size * 6)}px;
            }}
            QTabBar::tab:selected {{
                background-color: #ffffff;
                border-bottom: 1px solid #ffffff;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #f0f0f0;
            }}
            QTabBar::scroller {{
                width: 20px;
            }}
            QTabBar QToolButton {{
                background-color: #e0e0e0;
                border: 1px solid #cccccc;
                border-radius: 2px;
                margin: 2px;
                padding: 2px;
                color: #333333;
            }}
            QTabBar QToolButton:hover {{
                background-color: #d0d0d0;
            }}
            QTabBar QToolButton::right-arrow {{
                image: none;
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 5px solid #333333;
                width: 0px;
                height: 0px;
            }}
            QTabBar QToolButton::left-arrow {{
                image: none;
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-bottom: 5px solid #333333;
                width: 0px;
                height: 0px;
            }}
            QProgressBar {{
                border: 1px solid #cccccc;
                border-radius: 5px;
                text-align: center;
                background-color: #ffffff;
                color: #333333;
                font-weight: bold;
                font-size: {base_font_size}pt;
                min-height: {int(20 * self.scale_factor)}px;
            }}
            QProgressBar::chunk {{
                background-color: #0078d4;
                border-radius: 4px;
            }}
            QCheckBox {{
                color: #333333;
                spacing: {int(5 * self.scale_factor)}px;
                font-size: {base_font_size}pt;
            }}
            QCheckBox::indicator {{
                width: {int(18 * self.scale_factor)}px;
                height: {int(18 * self.scale_factor)}px;
            }}
            QCheckBox::indicator:unchecked {{
                border: 2px solid #cccccc;
                background-color: #ffffff;
                border-radius: 3px;
            }}
            QCheckBox::indicator:checked {{
                border: 2px solid #0078d4;
                background-color: #0078d4;
                border-radius: 3px;
            }}
            QSlider::groove:horizontal {{
                border: 1px solid #cccccc;
                height: {int(8 * self.scale_factor)}px;
                background: #ffffff;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #0078d4;
                border: 1px solid #0078d4;
                width: {int(18 * self.scale_factor)}px;
                border-radius: {int(9 * self.scale_factor)}px;
                margin: {int(-5 * self.scale_factor)}px 0px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #106ebe;
                border: 1px solid #106ebe;
            }}
            QLabel {{
                color: #333333;
                font-size: {base_font_size}pt;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            /* Time label state styling */
            QLabel[objectName="time_label"] {{
                color: #333333;
                background-color: transparent;
                border: 2px solid transparent;
                border-radius: 5px;
                padding: {int(5 * self.scale_factor)}px;
                font-weight: bold;
            }}
            QLabel[objectName="time_label"][state="active"] {{
                color: #2d5f2d !important;
                background-color: rgba(144, 238, 144, 0.3) !important;
                border: 2px solid #90EE90 !important;
            }}
            QLabel[objectName="time_label"][state="afk"] {{
                color: #b8860b !important;
                background-color: rgba(255, 255, 0, 0.2) !important;
                border: 2px solid #FFD700 !important;
            }}
            QLabel[objectName="time_label"][state="inactive"] {{
                color: #8b0000 !important;
                background-color: #ffb6c1 !important;
                border: 2px solid #ff6b6b !important;
                border-radius: 5px !important;
                padding: {int(5 * self.scale_factor)}px !important;
                font-weight: bold !important;
            }}
        """)
    
    def setup_connections(self):
        """Setup signal connections for UI components only."""
        # Search connections
        self.search_button.clicked.connect(self.search_vndb)
        self.search_entry.returnPressed.connect(self.search_vndb)
        
        # Process refresh
        self.refresh_processes_button.clicked.connect(self.refresh_process_list)
        
        # Target setting - this will toggle between start and stop
        self.set_target_button.clicked.connect(self.toggle_tracking)
        
        # VN selection (this will be for cover image loading if needed)
        self.vn_dropdown.currentTextChanged.connect(self.on_vn_selected)
        
        # Library management connections
        self.add_manual_button.clicked.connect(self.show_manual_input)
        self.add_vndb_button.clicked.connect(self.show_vndb_search)
        self.confirm_manual_button.clicked.connect(self.add_manual_vn)
        self.cancel_manual_button.clicked.connect(self.hide_input_widgets)
        self.cancel_vndb_button.clicked.connect(self.hide_input_widgets)
        self.manual_vn_entry.returnPressed.connect(self.add_manual_vn)
        self.add_selected_vndb_button.clicked.connect(self.add_vndb_vn_to_library)
        self.remove_vn_button.clicked.connect(self.remove_vn_from_library)
        
        # Action buttons
        self.reset_button.clicked.connect(self.reset_today)
        self.export_button.clicked.connect(self.export_data)
        self.minimize_tray_button.clicked.connect(self.minimize_to_tray)
        
        # Settings
        self.overlay_checkbox.toggled.connect(self.toggle_overlay)
        self.overlay_percentage_checkbox.toggled.connect(self.toggle_overlay_percentage)
        self.transparency_slider.valueChanged.connect(self.update_transparency)
    
    def set_application_icon(self):
        """Set the application icon for window and system tray."""
        # First check if QApplication already has an icon set
        from PyQt5.QtWidgets import QApplication
        app_icon = QApplication.windowIcon()
        if app_icon and not app_icon.isNull():
            print("Using application-level icon")
            self.setWindowIcon(app_icon)
            self.app_icon = app_icon
            return
        
        # Try to load custom icon first
        icon_paths = [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "app_icon.png"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "app_icon.ico"),
            os.path.join("icons", "app_icon.png"),
            os.path.join("icons", "app_icon.ico"),
            "app_icon.png",
            "app_icon.ico"
        ]
        
        icon = None
        for icon_path in icon_paths:
            if os.path.exists(icon_path):
                try:
                    icon = QIcon(icon_path)
                    if not icon.isNull():
                        print(f"Loaded application icon from: {icon_path}")
                        break
                except Exception as e:
                    print(f"Error loading icon from {icon_path}: {e}")
                    continue
        
        # If no custom icon found, create one from the book-clock theme
        if not icon or icon.isNull():
            print("No custom icon found, creating default book-clock icon")
            icon = self.create_book_clock_icon()
        
        # Set window icon
        if icon and not icon.isNull():
            self.setWindowIcon(icon)
            # Store for system tray use
            self.app_icon = icon
        else:
            # Fallback to system icon
            self.app_icon = self.style().standardIcon(self.style().SP_ComputerIcon)
        
        # Update system tray icon if it exists
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.setIcon(self.app_icon)
            print(f"Updated system tray icon: {not self.app_icon.isNull()}")
    
    def create_book_clock_icon(self):
        """Create a book-clock icon similar to the provided image."""
        from PyQt5.QtGui import QPainter, QPen, QBrush, QColor
        from PyQt5.QtCore import QRect
        
        # Create a 64x64 pixmap
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(240, 240, 240, 0))  # Transparent background
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        try:
            # Book base (purple)
            book_color = QColor(120, 81, 169)  # Purple color
            painter.setBrush(QBrush(book_color))
            painter.setPen(QPen(QColor(80, 60, 120), 2))
            
            # Book body
            book_rect = QRect(8, 20, 48, 36)
            painter.drawRoundedRect(book_rect, 3, 3)
            
            # Book pages (lighter)
            painter.setBrush(QBrush(QColor(250, 250, 250)))
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            page_rect = QRect(12, 24, 40, 28)
            painter.drawRoundedRect(page_rect, 2, 2)
            
            # Clock circle (white with dark border)
            clock_center_x, clock_center_y = 45, 20
            clock_radius = 15
            
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(QColor(50, 50, 50), 2))
            painter.drawEllipse(clock_center_x - clock_radius, clock_center_y - clock_radius, 
                              clock_radius * 2, clock_radius * 2)
            
            # Clock hands
            painter.setPen(QPen(QColor(20, 20, 20), 2, Qt.SolidLine, Qt.RoundCap))
            
            # Hour hand (shorter, pointing to 2)
            hour_end_x = clock_center_x + int(clock_radius * 0.5 * 0.866)  # cos(30°) ≈ 0.866
            hour_end_y = clock_center_y - int(clock_radius * 0.5 * 0.5)    # sin(30°) = 0.5
            painter.drawLine(clock_center_x, clock_center_y, hour_end_x, hour_end_y)
            
            # Minute hand (longer, pointing to 12)
            minute_end_x = clock_center_x
            minute_end_y = clock_center_y - int(clock_radius * 0.8)
            painter.drawLine(clock_center_x, clock_center_y, minute_end_x, minute_end_y)
            
            # Clock center dot
            painter.setBrush(QBrush(QColor(20, 20, 20)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(clock_center_x - 2, clock_center_y - 2, 4, 4)
            
        except Exception as e:
            print(f"Error creating book-clock icon: {e}")
        finally:
            painter.end()
        
        return QIcon(pixmap)

    def setup_system_tray(self):
        """Setup system tray icon."""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            
            # Create tray menu
            tray_menu = QMenu()
            
            show_action = QAction("Show", self)
            show_action.triggered.connect(self.show)
            tray_menu.addAction(show_action)
            
            quit_action = QAction("Exit", self)
            quit_action.triggered.connect(self.close)
            tray_menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.tray_icon_activated)
            
            # Set custom icon
            if hasattr(self, 'app_icon') and self.app_icon:
                self.tray_icon.setIcon(self.app_icon)
                print(f"Set system tray icon from app_icon: {not self.app_icon.isNull()}")
            else:
                self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
                print("Set system tray icon to default system icon")
            self.tray_icon.show()
    
    def load_initial_data(self):
        """Load initial data asynchronously."""
        # Get the last VN before loading anything
        last_vn = self.config_manager.last_vn
        
        # Validate that the last VN still exists in the library
        all_library_vns = self.config_manager.get_all_library_vns()
        if last_vn and last_vn not in all_library_vns:
            last_vn = None  # Clear invalid last VN
        
        # Load VN dropdown with the target selection
        QTimer.singleShot(60, lambda: self.refresh_vn_selection(target_vn=last_vn))
        
        # Load process list
        QTimer.singleShot(100, self.load_process_list)
    
    def load_process_list(self):
        """Load the process list."""
        # Safety check - don't load if process monitor isn't ready
        if not self.process_monitor:
            return
            
        try:
            processes = self.process_monitor.get_process_list()
            self.process_dropdown.clear()
            self.process_dropdown.addItems(processes)
        except Exception as e:
            print(f"Error loading process list: {e}")
    
    @pyqtSlot()
    def refresh_process_list(self):
        """Refresh the process list when the refresh button is clicked."""
        # Safety check - don't refresh if process monitor isn't ready
        if not self.process_monitor:
            QMessageBox.information(self, "Please Wait", "Application is still loading...")
            return
            
        # Store current selection
        current_selection = self.process_dropdown.currentText()
        
        # Show updating indicator
        self.refresh_processes_button.setEnabled(False)
        self.refresh_processes_button.setText("Refreshing...")
        
        # Use QTimer to allow UI to update before doing the heavy work
        QTimer.singleShot(50, lambda: self._do_refresh_process_list(current_selection))
    
    def _do_refresh_process_list(self, current_selection):
        """Actually perform the process list refresh."""
        try:
            # Force the process monitor to scan for new processes immediately
            self.process_monitor.refresh_process_list()
            
            # Get the fresh process list (this will be updated after the scan above)
            processes = self.process_monitor.get_process_list()
            self.process_dropdown.clear()
            self.process_dropdown.addItems(processes)
            
            # Try to restore the previous selection if it still exists
            if current_selection:
                index = self.process_dropdown.findText(current_selection)
                if index >= 0:
                    self.process_dropdown.setCurrentIndex(index)
            
            # Show success feedback
            original_text = self.refresh_processes_button.text()
            self.refresh_processes_button.setText("✓ Done")
            QTimer.singleShot(1000, lambda: self._restore_refresh_button("Refresh"))
                    
        except Exception as e:
            print(f"Error refreshing process list: {e}")
            # Show error feedback
            self.refresh_processes_button.setText("Error")
            QTimer.singleShot(2000, lambda: self._restore_refresh_button("Refresh"))
    
    def _restore_refresh_button(self, text):
        """Restore the refresh button to its normal state."""
        self.refresh_processes_button.setEnabled(True)
        self.refresh_processes_button.setText(text)
    
    @pyqtSlot()
    @pyqtSlot(str)
    def on_vn_selected(self, title):
        """Handle VN selection."""
        # Safety check - don't load data if VNDB client isn't ready
        if not self.vndb_client:
            return
            
        if title:
            # Clear current info and show loading
            self.cover_label.setText("Loading...")
            self.clear_vn_info()
            self.vn_title_label.setText(f"Title: {title}")
            
            # Stop any existing worker
            if self.vn_info_worker and self.vn_info_worker.isRunning():
                self.vn_info_worker.terminate()
                self.vn_info_worker.wait()
            
            # Start new worker to load both image and info
            self.vn_info_worker = VNInfoLoadWorker(self.vndb_client, title, self.config_manager)
            self.vn_info_worker.vn_info_loaded.connect(self.on_vn_info_loaded, Qt.QueuedConnection)
            self.vn_info_worker.start()
        else:
            # Clear everything if no title
            self.cover_label.setText("No Image")
            self.clear_vn_info()
    
    @pyqtSlot(object, object)
    def on_vn_info_loaded(self, image_data, vn_info):
        """Handle VN info and image loading completion."""
        print(f"VN info loaded callback - image_data: {bool(image_data)}, vn_info: {bool(vn_info)}")
        
        # Handle image
        if image_data:
            try:
                pixmap = QPixmap()
                if pixmap.loadFromData(image_data):
                    # Scale the image to fit the label using DPI-aware dimensions
                    cover_width = int(200 * self.scale_factor)
                    cover_height = int(280 * self.scale_factor)
                    scaled_pixmap = pixmap.scaled(cover_width, cover_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.cover_label.setPixmap(scaled_pixmap)
                    print("Successfully displayed cover image")
                else:
                    print("Failed to load pixmap from image data")
                    self.cover_label.setText("Image Format Error")
            except Exception as e:
                print(f"Image display error: {e}")
                import traceback
                traceback.print_exc()
                self.cover_label.setText("Image Error")
        else:
            print("No image data received")
            self.cover_label.setText("No Image")
        
        # Handle VN info
        if vn_info:
            print(f"Updating VN info: {vn_info}")
            self.update_vn_info(vn_info)
        else:
            print("No VN info received")
            self.clear_vn_info()
    
    def update_vn_info(self, vn_info):
        """Update VN information display."""
        try:
            print(f"Raw VN info: {vn_info}")
            
            # Description
            description = vn_info.get("description", "No description available")
            if description and description != "No description available" and len(description) > 200:
                description = description[:200] + "..."
            self.vn_description_label.setText(description or "No description available")
            
            # Release Date
            released = vn_info.get("released")
            if released:
                self.vn_release_label.setText(f"Release Date: {released}")
            else:
                self.vn_release_label.setText("Release Date: Unknown")
            
            # Rating - handle the API v2 format
            rating = vn_info.get("rating")
            if rating and rating > 0:
                # API returns rating as a value between 10-100, convert to 1-10 scale
                display_rating = rating / 10.0
                self.vn_rating_label.setText(f"Rating: {display_rating:.1f}/10")
            else:
                self.vn_rating_label.setText("Rating: Not Rated")
            
            # Developer - handle the API v2 format
            developers = vn_info.get("developers", [])
            if developers:
                if isinstance(developers, list):
                    # Extract names from developer objects
                    dev_names = []
                    for dev in developers:
                        if isinstance(dev, dict):
                            name = dev.get("name", "Unknown")
                            dev_names.append(name)
                        else:
                            dev_names.append(str(dev))
                    developer_text = ", ".join(dev_names) if dev_names else "Unknown"
                else:
                    developer_text = str(developers)
                self.vn_developer_label.setText(f"Developer: {developer_text}")
            else:
                self.vn_developer_label.setText("Developer: Unknown")
            
            # Length
            length_minutes = vn_info.get("length_minutes")
            if length_minutes and length_minutes > 0:
                hours = length_minutes // 60
                if hours > 0:
                    self.vn_length_label.setText(f"Length: ~{hours} hours")
                else:
                    self.vn_length_label.setText(f"Length: ~{length_minutes} minutes")
            else:
                self.vn_length_label.setText("Length: Unknown")
                
            print("VN info updated successfully")
                
        except Exception as e:
            print(f"Error updating VN info: {e}")
            import traceback
            traceback.print_exc()
            self.clear_vn_info()
    
    def clear_vn_info(self):
        """Clear VN information display."""
        self.vn_title_label.setText("Title: Not Selected")
        self.vn_description_label.setText("No description available")
        self.vn_release_label.setText("Release Date: Unknown")
        self.vn_rating_label.setText("Rating: Not Rated")
        self.vn_developer_label.setText("Developer: Unknown")
        self.vn_length_label.setText("Length: Unknown")
    
    @pyqtSlot()
    def toggle_tracking(self):
        """Toggle between start and stop tracking."""
        # Safety check - don't set target if tracker isn't ready
        if not self.tracker:
            QMessageBox.information(self, "Please Wait", "Application is still loading...")
            return
        
        # Prevent rapid clicking by disabling button temporarily
        if hasattr(self, '_toggle_in_progress') and self._toggle_in_progress:
            return
        
        try:
            self._toggle_in_progress = True
            self.set_target_button.setEnabled(False)
            
            # Check if currently tracking
            if self.is_tracking_active():
                # Currently tracking - stop tracking
                self.stop_tracking()
            else:
                # Not tracking - start tracking
                self.start_tracking()
        finally:
            # Re-enable button after a short delay to prevent spam clicking
            QTimer.singleShot(200, self._restore_toggle_button)
    
    def _restore_toggle_button(self):
        """Restore the toggle button state after a brief delay."""
        self._toggle_in_progress = False
        self.set_target_button.setEnabled(True)
    
    def is_tracking_active(self):
        """Check if tracking is currently active."""
        return (self.tracker and 
                hasattr(self.tracker, 'selected_vn_title') and 
                hasattr(self.tracker, 'selected_process') and
                self.tracker.selected_vn_title is not None and 
                self.tracker.selected_process is not None)
    
    def start_tracking(self):
        """Start tracking with selected VN and process."""
        vn_title = self.get_selected_vn_title()
        process_name = self.process_dropdown.currentText()
        
        if vn_title and process_name:
            # Only clear preserved state when starting a different VN
            if self.last_displayed_vn and self.last_displayed_vn != vn_title:
                self.last_displayed_vn = None
                self.last_displayed_time = 0
            
            self.tracker.set_target(vn_title, process_name)
            
            # Update config
            process_mapping = self.config_manager.process_to_vn
            process_mapping[vn_title] = process_name
            self.config_manager.update({
                "last_vn": vn_title,
                "process_to_vn": process_mapping
            })
            self.config_manager.save()
            
            self.status_label.setText(f"{self.i18n.t('tracking')}: {vn_title} ({process_name})")
            self.update_tracking_button()
        else:
            QMessageBox.warning(self, "Warning", self.i18n.t("invalid_selection"))
    
    def stop_tracking(self):
        """Stop current tracking."""
        if self.tracker:
            current_vn = None
            current_seconds = 0
            
            # Get current time BEFORE clearing tracker state to avoid flashing to 0
            with self.tracker._data_lock:
                current_vn = self.tracker.selected_vn_title
                # Get the current seconds while VN is still selected
                if current_vn:
                    current_seconds = self.tracker.get_current_seconds()
                
                # Save any pending time before stopping
                if self.tracker.selected_vn_title and self.tracker.last_start:
                    import time
                    elapsed = int(time.time() - self.tracker.last_start)
                    self.tracker.data_manager.add_time(self.tracker.selected_vn_title, elapsed)
                    self.tracker.last_start = None
                
                # Clear tracking target
                self.tracker.selected_vn_title = None
                self.tracker.selected_process = None
            
            # Preserve the state for display purposes - only update if we have valid data
            if current_vn and current_seconds > 0:
                self.last_displayed_vn = current_vn
                self.last_displayed_time = current_seconds
            
            # Immediately update visual state to INACTIVE (red) since we've stopped tracking
            # Use the current_seconds we captured before clearing the tracker
            from ..core.tracker import TrackingState
            self.on_tracking_state_changed(TrackingState.INACTIVE, current_seconds)
            
            # Show feedback message
            if current_vn:
                self.status_label.setText(f"{self.i18n.t('tracking')}: {self.i18n.t('not_selected')} (Stopped tracking {current_vn})")
            else:
                self.status_label.setText(f"{self.i18n.t('tracking')}: {self.i18n.t('not_selected')}")
            
            self.update_tracking_button()
    
    def update_tracking_button(self):
        """Update the tracking button text and appearance based on current state."""
        if self.is_tracking_active():
            # Currently tracking - show stop button with hover effect
            self.set_target_button.setText(self.i18n.t("stop_tracking"))
            self.set_target_button.setStyleSheet("""
                QPushButton { 
                    background-color: #ff6b6b; 
                    color: white; 
                }
                QPushButton:hover { 
                    background-color: #e55555; 
                }
            """)
        else:
            # Not tracking - show start button
            self.set_target_button.setText(self.i18n.t("select_game_process"))
            self.set_target_button.setStyleSheet("")  # Reset to default style
    
    def show_manual_input(self):
        """Show manual VN input widget."""
        self.hide_input_widgets()
        self.manual_input_widget.setVisible(True)
        self.manual_vn_entry.setFocus()
    
    def show_vndb_search(self):
        """Show VNDB search widget."""
        self.hide_input_widgets()
        self.vndb_search_widget.setVisible(True)
        self.search_entry.setFocus()
    
    def hide_input_widgets(self):
        """Hide all input widgets."""
        self.manual_input_widget.setVisible(False)
        self.vndb_search_widget.setVisible(False)
        # Clear inputs
        self.manual_vn_entry.clear()
        self.search_entry.clear()
        self.vndb_results_dropdown.clear()
    
    def add_manual_vn(self):
        """Add a manual VN to the library."""
        title = self.manual_vn_entry.text().strip()
        if not title:
            QMessageBox.warning(self, "Warning", "Please enter a VN title.")
            return
        
        # Check if already exists
        all_library_vns = self.config_manager.get_all_library_vns()
        
        if title in all_library_vns:
            QMessageBox.information(self, "Information", f"'{title}' is already in your library.")
            self.hide_input_widgets()
            return
        
        # Add to config
        self.config_manager.add_manual_vn(title)
        
        # Refresh VN selection display
        self.refresh_vn_selection()
        
        # Hide input and show success
        self.hide_input_widgets()
        QMessageBox.information(self, "Success", f"Added '{title}' to your library.")
    
    @pyqtSlot()
    def search_vndb(self, query=None):
        """Search VNDB for VNs."""
        # Safety check - don't search if VNDB client isn't ready
        if not self.vndb_client:
            QMessageBox.information(self, "Please Wait", "Application is still loading...")
            return
            
        if query is None:
            query = self.search_entry.text().strip()
        
        if not query:
            return
        
        # Disable search while working
        self.search_button.setEnabled(False)
        self.search_button.setText("Working...")  # Keep similar length to original "Search" text
        
        # Start background search
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.terminate()
            self.search_worker.wait()
        
        self.search_worker = VNSearchWorker(self.vndb_client, query)
        self.search_worker.search_completed.connect(self.on_vndb_search_completed, Qt.QueuedConnection)
        self.search_worker.start()
    
    @pyqtSlot(list)
    def on_vndb_search_completed(self, results):
        """Handle VNDB search completion."""
        self.search_button.setEnabled(True)
        self.search_button.setText(self.i18n.t("search"))
        
        self.vndb_results_dropdown.clear()
        
        # Store VN objects for later use
        self.vndb_search_results = results
        
        # Populate dropdown with titles and developers
        for vn_data in results:
            title = vn_data.get("title", "Unknown")
            developers = vn_data.get("developers", [])
            if developers:
                dev_names = ", ".join([dev.get("name", "") for dev in developers])
                display_text = f"{title} ({dev_names})"
            else:
                display_text = title
            self.vndb_results_dropdown.addItem(display_text)
        
        if results and self.search_entry.text().strip():
            # Try to select exact match
            exact_match = self.search_entry.text().strip()
            for i, vn_data in enumerate(results):
                if vn_data.get("title", "").lower() == exact_match.lower():
                    self.vndb_results_dropdown.setCurrentIndex(i)
                    break
    
    def add_vndb_vn_to_library(self):
        """Add selected VNDB VN to the library."""
        selected_index = self.vndb_results_dropdown.currentIndex()
        if selected_index < 0 or selected_index >= len(self.vndb_search_results):
            QMessageBox.warning(self, "Warning", "Please select a VN from the search results.")
            return
        
        # Get the selected VN data
        selected_vn_data = self.vndb_search_results[selected_index]
        vn_title = selected_vn_data.get("title", "").strip()
        vndb_id = selected_vn_data.get("id", "")
        
        if not vn_title:
            QMessageBox.warning(self, "Warning", "Selected VN has no valid title.")
            return
        
        if not vndb_id:
            QMessageBox.warning(self, "Warning", "Selected VN has no VNDB ID.")
            return
        
        # Check if already exists in library
        all_library_vns = self.config_manager.get_all_library_vns()
        
        if vn_title in all_library_vns:
            QMessageBox.information(self, "Information", f"'{vn_title}' is already in your library.")
            self.hide_input_widgets()
            return
        
        # Add to VNDB VNs with ID and metadata
        self.config_manager.add_vndb_vn(vn_title, vndb_id, selected_vn_data)
        
        # Refresh VN selection display
        self.refresh_vn_selection()
        
        # Hide input and show success
        self.hide_input_widgets()
        developers = selected_vn_data.get("developers", [])
        dev_text = ""
        if developers:
            dev_names = ", ".join([dev.get("name", "") for dev in developers])
            dev_text = f" by {dev_names}"
        
        QMessageBox.information(self, "Success", f"Added '{vn_title}'{dev_text} to your library with VNDB ID: {vndb_id}")
        
        print(f"Added VNDB VN: {vn_title} (ID: {vndb_id})")
    
    def remove_vn_from_library(self):
        """Delete the currently selected VN including all tracking data."""
        selected_vn = self.vn_dropdown.currentText().strip()
        if not selected_vn:
            QMessageBox.warning(self, "Warning", "Please select a VN to delete.")
            return
        
        # Check if the VN is currently being tracked
        if self.is_tracking_active() and self.tracker and self.tracker.selected_vn_title == selected_vn:
            QMessageBox.warning(
                self, 
                "Cannot Delete", 
                f"Cannot delete '{selected_vn}' because it is currently being tracked.\n\nPlease stop tracking first, then try deleting again."
            )
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self, 
            "Confirm Deletion", 
            f"Are you sure you want to delete '{selected_vn}'?\n\nThis will permanently remove the VN and ALL its tracking data.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Delete VN data from data manager first
                if self.data_manager:
                    self.data_manager.delete_vn_data(selected_vn)
                    self.data_manager.save(force_backup=True)
                
                # Remove VN completely including all tracking data and cached image
                # This method handles both config cleanup and image deletion
                self.config_manager.remove_vn_completely_with_data(selected_vn)
                
                # Clear cached images for the deleted VN
                if self.vndb_client:
                    try:
                        self.vndb_client.clear_vn_cache(selected_vn)
                        print(f"Cleared cache for deleted VN: {selected_vn}")
                    except Exception as e:
                        print(f"Error clearing cache for deleted VN '{selected_vn}': {e}")
                
                # Refresh displays
                self.refresh_vn_selection()
                
                QMessageBox.information(self, "Success", f"Deleted '{selected_vn}' and all its tracking data.")
                
            except Exception as e:
                print(f"Error deleting VN '{selected_vn}': {e}")
                QMessageBox.critical(self, "Deletion Error", f"Failed to delete '{selected_vn}':\n{str(e)}")
                # Try to refresh displays anyway in case partial deletion occurred
                self.refresh_vn_selection()
    
    def refresh_vn_selection(self, target_vn=None):
        """Refresh the VN selection dropdown and ensure display consistency.
        
        Args:
            target_vn: If provided, will attempt to select this VN instead of preserving current selection
        """
        # Store current selection to try to preserve it (unless target_vn is specified)
        current_selection = self.vn_dropdown.currentText() if target_vn is None else target_vn
        
        # Temporarily disconnect the signal to prevent multiple updates during refresh
        self.vn_dropdown.currentTextChanged.disconnect(self.on_vn_selected)
        
        try:
            self.vn_dropdown.clear()
            
            all_library_vns = self.config_manager.get_all_library_vns()
            
            if all_library_vns:
                self.vn_dropdown.addItems(all_library_vns)
                self.remove_vn_button.setEnabled(True)
                
                # Try to select the target VN or restore the previous selection
                final_selection = None
                if current_selection and current_selection in all_library_vns:
                    index = self.vn_dropdown.findText(current_selection)
                    if index >= 0:
                        self.vn_dropdown.setCurrentIndex(index)
                        final_selection = current_selection
                
                # If we couldn't select the target/previous selection, use the first item
                if final_selection is None:
                    final_selection = self.vn_dropdown.currentText()
                
            else:
                self.vn_dropdown.addItem(self.i18n.t("no_vns_in_library"))
                self.remove_vn_button.setEnabled(False)
                final_selection = ""
                
        finally:
            # Always reconnect the signal
            self.vn_dropdown.currentTextChanged.connect(self.on_vn_selected)
            
            # Now trigger VN info update to ensure consistency with the current selection
            current_text = self.vn_dropdown.currentText()
            if current_text and current_text != self.i18n.t("no_vns_in_library"):
                # Use QTimer to ensure the signal connection is fully restored before triggering
                QTimer.singleShot(50, lambda: self.on_vn_selected(current_text))
            else:
                # Clear the display if no valid VN is selected
                QTimer.singleShot(50, lambda: self.on_vn_selected(""))
    
    def get_selected_vn_title(self):
        """Get the currently selected VN title."""
        selected = self.vn_dropdown.currentText().strip()
        if selected == self.i18n.t("no_vns_in_library"):
            return ""
        return selected

    def update_display(self):
        """Update the display with current data."""
        # Safety check - don't update if components aren't loaded yet
        if not self.tracker:
            return
            
        try:
            # Determine what time to display based on tracking state
            current_vn = getattr(self.tracker, 'selected_vn_title', None)
            
            if current_vn:
                # Currently tracking - show real-time seconds
                today_seconds = self.tracker.get_current_seconds()
                self.last_displayed_vn = current_vn
                self.last_displayed_time = today_seconds
            elif self.last_displayed_vn:
                # Not tracking but we have a last VN - keep showing its time
                today_seconds = self.last_displayed_time
            else:
                # No previous VN to display
                today_seconds = 0
            
            time_str = format_time(today_seconds)
            self.time_label.setText(f"{self.i18n.t('today_reading_time')}: {time_str}")

            # Update progress bar
            self.progress_bar.setValue(min(today_seconds, self.progress_bar.maximum()))

            # Update statistics - these should always be current
            if current_vn:
                # Currently tracking - show stats for current VN
                week_minutes = self.tracker.get_weekly_seconds() // 60
                month_minutes = self.tracker.get_monthly_seconds() // 60
                total_minutes = self.tracker.get_total_seconds() // 60
            elif self.last_displayed_vn and self.data_manager:
                # Not tracking - show stats for last displayed VN
                week_minutes = self.data_manager.get_weekly_seconds(self.last_displayed_vn) // 60
                month_minutes = self.data_manager.get_monthly_seconds(self.last_displayed_vn) // 60
                total_minutes = self.data_manager.get_total_seconds(self.last_displayed_vn) // 60
            else:
                # No VN to show stats for
                week_minutes = month_minutes = total_minutes = 0

            self.week_label.setText(f"{self.i18n.t('weekly')}: {week_minutes} {self.i18n.t('minutes')}")
            self.month_label.setText(f"{self.i18n.t('monthly')}: {month_minutes} {self.i18n.t('minutes')}")
            self.total_label.setText(f"{self.i18n.t('total')}: {total_minutes} {self.i18n.t('minutes')}")

            # Update overlay time only (color is handled by state change callback)
            if self.overlay and self.config_manager.show_overlay:
                self.overlay.update_time(time_str)
                
                # Update goal percentage if enabled
                if self.config_manager.show_overlay_percentage:
                    goal_seconds = self.config_manager.goal_minutes * 60
                    percentage = min((today_seconds / goal_seconds) * 100, 100.0) if goal_seconds > 0 else 0.0
                    self.overlay.update_percentage(percentage)
        except Exception as e:
            print(f"Display update error: {e}")
    
    def on_tracking_state_changed(self, state: TrackingState, current_seconds: int):
        """Handle tracking state changes."""
        # Update time display immediately with the passed current_seconds to ensure sync
        time_str = format_time(current_seconds)
        self.time_label.setText(f"{self.i18n.t('today_reading_time')}: {time_str}")
        
        # Update progress bar immediately to stay in sync with overlay
        self.progress_bar.setValue(min(current_seconds, self.progress_bar.maximum()))
        
        # Update time label color based on tracking state
        try:
            if state == TrackingState.ACTIVE:
                # Green for active tracking
                self.time_label.setProperty("state", "active")
            elif state == TrackingState.AFK:
                # Yellow for AFK
                self.time_label.setProperty("state", "afk")
            else:  # INACTIVE
                # Red for inactive
                self.time_label.setProperty("state", "inactive")
            
            # Force style refresh with error handling
            try:
                self.time_label.style().unpolish(self.time_label)
                self.time_label.style().polish(self.time_label)
                    
            except Exception as e:
                print(f"Style refresh error: {e}")
                
        except Exception as e:
            print(f"State styling error: {e}")
        
        # Also update overlay color and time immediately when state changes
        if self.overlay and self.config_manager.show_overlay:
            # Update overlay immediately on state change for responsive feedback
            self.update_overlay_color(state)
            self.overlay.update_time(time_str)
            
            # Update goal percentage if enabled
            if self.config_manager.show_overlay_percentage:
                goal_seconds = self.config_manager.goal_minutes * 60
                percentage = min((current_seconds / goal_seconds) * 100, 100.0) if goal_seconds > 0 else 0.0
                self.overlay.update_percentage(percentage)
                
        # Update tracking button state
        self.update_tracking_button()
    
    def on_tracking_updated(self):
        """Handle tracking data updates."""
        # Don't update overlay here - let update_display handle it to avoid conflicts
        pass
    
    def on_process_list_updated(self, processes):
        """Handle process list updates in main thread."""
        try:
            current_process = self.process_dropdown.currentText()
            self.process_dropdown.clear()
            self.process_dropdown.addItems(processes)
            
            # Restore selection if possible
            index = self.process_dropdown.findText(current_process)
            if index >= 0:
                self.process_dropdown.setCurrentIndex(index)
        except Exception as e:
            if self.crash_logger:
                self.crash_logger.log_error(f"Error updating process list UI: {e}")
            else:
                print(f"Error updating process list UI: {e}")
    
    def _emit_process_list_signal(self, processes):
        """Thread-safe signal emitter for process list updates."""
        try:
            # Emit signal to be handled in main thread
            self.process_list_updated_signal.emit(processes)
        except Exception as e:
            if self.crash_logger:
                self.crash_logger.log_error(f"Error emitting process list signal: {e}")
            else:
                print(f"Error emitting process list signal: {e}")
    
    def _emit_tracking_state_signal(self, state, current_seconds):
        """Thread-safe signal emitter for tracking state changes."""
        try:
            self.tracking_state_changed_signal.emit(state, current_seconds)
        except Exception as e:
            if self.crash_logger:
                self.crash_logger.log_error(f"Error emitting tracking state signal: {e}")
            else:
                print(f"Error emitting tracking state signal: {e}")
    
    def _emit_tracking_updated_signal(self):
        """Thread-safe signal emitter for tracking updates."""
        try:
            self.tracking_updated_signal.emit()
        except Exception as e:
            if self.crash_logger:
                self.crash_logger.log_error(f"Error emitting tracking updated signal: {e}")
            else:
                print(f"Error emitting tracking updated signal: {e}")
    
    @pyqtSlot()
    def set_goal(self):
        """Set the goal time."""
        try:
            minutes = self.goal_spinbox.value()
            self.progress_bar.setMaximum(minutes * 60)
            
            # Thread-safe config update
            self.config_manager.set("goal_minutes", minutes)
            self.config_manager.save()
            
            # Update overlay percentage immediately if it's shown
            if self.overlay and self.config_manager.show_overlay and self.config_manager.show_overlay_percentage:
                if self.tracker:
                    try:
                        today_seconds = self.tracker.get_current_seconds()
                        goal_seconds = minutes * 60
                        percentage = min((today_seconds / goal_seconds) * 100, 100.0) if goal_seconds > 0 else 0.0
                        self.overlay.update_percentage(percentage)
                    except Exception as e:
                        if self.crash_logger:
                            self.crash_logger.log_error(f"Error updating overlay in set_goal: {e}")
            
            QMessageBox.information(self, "Success", f"Goal set to {minutes} minutes")
        except Exception as e:
            if self.crash_logger:
                self.crash_logger.log_error(f"Error in set_goal: {e}")
            QMessageBox.critical(self, "Error", f"Failed to set goal: {e}")
    
    @pyqtSlot()
    def set_afk_threshold(self):
        """Set the AFK threshold."""
        try:
            # Safety check - don't set threshold if tracker isn't ready
            if not self.tracker:
                QMessageBox.information(self, "Please Wait", "Application is still loading...")
                return
                
            seconds = self.afk_spinbox.value()
            
            # Thread-safe tracker update
            self.tracker.set_afk_threshold(seconds)
            self.config_manager.set("afk_threshold", seconds)
            self.config_manager.save()
            
            QMessageBox.information(self, "Success", f"AFK threshold set to {seconds} seconds")
        except Exception as e:
            if self.crash_logger:
                self.crash_logger.log_error(f"Error in set_afk_threshold: {e}")
            QMessageBox.critical(self, "Error", f"Failed to set AFK threshold: {e}")
    
    @pyqtSlot()
    def set_language(self):
        """Set the application language."""
        lang_code = self.language_dropdown.currentData()
        if lang_code:
            self.i18n.set_language(lang_code)
            QMessageBox.information(self, "Success", "Language changed. Please restart the application.")
    
    @pyqtSlot()
    def set_ui_scale_override(self):
        """Set manual UI scale override."""
        try:
            scale_percent = self.scale_override_spinbox.value()
            self.config_manager.set("ui_scale_override", scale_percent)
            self.config_manager.save()
            
            QMessageBox.information(
                self, 
                "Scale Changed", 
                f"UI scale set to {scale_percent}%.\n\nPlease restart the application for changes to take effect."
            )
        except Exception as e:
            print(f"Error setting UI scale: {e}")
            QMessageBox.warning(self, "Error", f"Failed to set UI scale: {str(e)}")
    
    @pyqtSlot(bool)
    def toggle_overlay(self, show):
        """Toggle overlay visibility."""
        try:
            self.config_manager.set("show_overlay", show)
            self.config_manager.save()
            
            if self.overlay:
                if show:
                    self.overlay.show()
                else:
                    self.overlay.hide()
        except Exception as e:
            if self.crash_logger:
                self.crash_logger.log_error(f"Error in toggle_overlay: {e}")
    
    @pyqtSlot(bool)
    def toggle_overlay_percentage(self, show):
        """Toggle overlay percentage visibility."""
        try:
            self.config_manager.set("show_overlay_percentage", show)
            self.config_manager.save()
            
            if self.overlay:
                self.overlay.set_show_percentage(show)
        except Exception as e:
            if self.crash_logger:
                self.crash_logger.log_error(f"Error in toggle_overlay_percentage: {e}")
    
    @pyqtSlot(int)
    def update_transparency(self, value):
        """Update overlay transparency."""
        alpha = value / 100.0
        self.transparency_label.setText(f"{value}%")
        self.config_manager.set("overlay_alpha", alpha)
        self.config_manager.save()
        
        if self.overlay:
            self.overlay.setWindowOpacity(alpha)
    
    @pyqtSlot()
    def reset_today(self):
        """Reset today's time."""
        # Safety check - don't reset if tracker isn't ready
        if not self.tracker:
            QMessageBox.information(self, "Please Wait", "Application is still loading...")
            return
            
        reply = QMessageBox.question(
            self, "Confirm Reset", 
            "Are you sure you want to reset today's time?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.tracker.reset_today()
            QMessageBox.information(self, "Success", "Today's time has been reset")
    
    @pyqtSlot()
    def export_data(self):
        """Export time tracking data."""
        # Safety check - don't export if data manager isn't ready
        if not self.data_manager:
            QMessageBox.information(self, "Please Wait", "Application is still loading...")
            return
            
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Data", "vn_tracker_data.json", "JSON Files (*.json)"
        )
        
        if filename:
            try:
                self.data_manager.export_data(filename)
                QMessageBox.information(self, "Success", f"Data exported to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")
    
    @pyqtSlot()
    def minimize_to_tray(self):
        """Minimize the window to system tray."""
        if self.tray_icon:
            self.hide()
            self.tray_icon.showMessage(
                "VN Tracker",
                "Application minimized to tray",
                QSystemTrayIcon.Information,
                2000
            )
    
    def tray_icon_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Stop update timer first
        if self.update_timer:
            self.update_timer.stop()
            
        # Cleanup worker threads
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.terminate()
            self.search_worker.wait(1000)  # Wait max 1 second
            if self.search_worker.isRunning():
                self.search_worker.kill()
        
        if self.vn_info_worker and self.vn_info_worker.isRunning():
            self.vn_info_worker.terminate()
            self.vn_info_worker.wait(1000)  # Wait max 1 second
            if self.vn_info_worker.isRunning():
                self.vn_info_worker.kill()
        
        # Cleanup heavy components if they exist
        if self.tracker:
            self.tracker.stop()
        if self.process_monitor:
            self.process_monitor.stop()
        if self.overlay:
            self.overlay.close()
            
        event.accept()
    
    def initialize_overlay_settings(self):
        """Initialize overlay with current settings."""
        if self.overlay:
            # Set initial transparency
            alpha = self.config_manager.overlay_alpha
            self.overlay.setWindowOpacity(alpha)
            
            # Set percentage visibility
            self.overlay.set_show_percentage(self.config_manager.show_overlay_percentage)
            
            # Show overlay if enabled
            if self.config_manager.show_overlay:
                self.overlay.show()
    
    def update_overlay_color(self, state):
        """Update overlay color based on tracking state."""
        if not self.overlay:
            return
            
        try:
            # Always set a color regardless of state
            if state == TrackingState.ACTIVE:
                self.overlay.set_color("rgba(40, 80, 40, 200)", "#ffffff")
            elif state == TrackingState.AFK:
                self.overlay.set_color("rgba(100, 80, 0, 200)", "#ffffff")
            else:  # INACTIVE or None - use red for inactive
                self.overlay.set_color("rgba(80, 40, 40, 200)", "#ffffff")
        except Exception as e:
            print(f"Overlay color update error: {e}")
    
    def initialize_heavy_components(self):
        """Initialize heavy components asynchronously after UI is shown."""
        try:
            import time
            heavy_start = time.time()
            
            # Update loading indicator with progress - using fixed-width format to prevent layout shifts
            self.loading_label.setText("🔄 Loading data manager...      ")
            
            # Lazy import and initialize components one by one for better feedback
            from ..utils.data_storage import TimeDataManager
            self.data_manager = TimeDataManager(self.log_file)
            
            self.loading_label.setText("🔄 Loading process monitor...   ")
            from ..core.process_monitor import ProcessMonitor
            self.process_monitor = ProcessMonitor()
            
            self.loading_label.setText("🔄 Loading VNDB client...       ")
            from ..core.vndb_api import VNDBClient
            self.vndb_client = VNDBClient(self.image_cache_dir)
            
            self.loading_label.setText("🔄 Initializing tracker...      ")
            # Initialize tracker
            self.tracker = TimeTracker(self.data_manager, self.process_monitor, self.crash_logger)
            
            # Load AFK threshold from config
            self.tracker.set_afk_threshold(self.config_manager.afk_threshold)
            
            self.loading_label.setText("🔄 Setting up overlay...        ")
            from .overlay_qt import OverlayWindow
            self.overlay = OverlayWindow()
            
            self.loading_label.setText("🔄 Connecting components...     ")
            # Setup connections that require heavy components with proper threading
            
            # Connect signals for thread-safe updates
            self.tracking_state_changed_signal.connect(self.on_tracking_state_changed, Qt.QueuedConnection)
            self.tracking_updated_signal.connect(self.on_tracking_updated, Qt.QueuedConnection)
            self.process_list_updated_signal.connect(self.on_process_list_updated, Qt.QueuedConnection)
            
            # Register thread-safe signal emitters as callbacks
            self.tracker.add_state_callback(self._emit_tracking_state_signal)
            self.tracker.add_update_callback(self._emit_tracking_updated_signal)
            self.process_monitor.add_process_list_callback(self._emit_process_list_signal)
            
            # Setup timers for updates (fix threading issue)
            self.update_timer = QTimer(self)  # Parent the timer to this widget
            self.update_timer.timeout.connect(self.update_display)
            self.update_timer.start(1000)  # Update every second
            
            self.loading_label.setText("🔄 Starting services...         ")
            # Start components
            self.process_monitor.start()
            self.tracker.start()
            
            # Load initial data
            self.load_initial_data()
            
            # Initialize overlay settings
            self.initialize_overlay_settings()
            
            # Hide loading indicator and show completion time
            heavy_end = time.time()
            total_time = heavy_end - self.startup_time
            heavy_time = heavy_end - heavy_start
            ui_time = heavy_start - self.startup_time
            
            # More concise ready message that fits better - using fixed-width format
            self.loading_label.setText(f"✅ Ready! ({total_time:.1f}s)            ")
            self.loading_label.setStyleSheet("color: #2d5f2d; font-weight: bold; margin: 0px; padding: 3px;")
            self.loading_label.setContentsMargins(0, 0, 0, 0)  # Ensure no margins for ready state
            
            # Unlock window resizing now that initialization is complete
            self.setMinimumSize(int(1200 * self.scale_factor), int(700 * self.scale_factor))
            self.setMaximumSize(16777215, 16777215)  # Reset to default Qt maximum
            
            print(f"Heavy components loaded in {heavy_time:.3f} seconds")
            print(f"Total startup time: {total_time:.3f} seconds")
            print(f"Performance improvement: UI responsive {heavy_time:.3f}s earlier!")
            
            # Initialize tracking button state
            self.update_tracking_button()
            
        except Exception as e:
            print(f"Error initializing heavy components: {e}")
            # Show error to user - using fixed-width format
            self.loading_label.setText("❌ Failed to load components    ")
            self.loading_label.setStyleSheet("color: #8b0000; font-weight: bold; margin: 0px; padding: 3px;")
            self.loading_label.setContentsMargins(0, 0, 0, 0)  # Ensure no margins for error state
            QMessageBox.critical(self, "Initialization Error", 
                               f"Failed to initialize application components: {str(e)}")
            self.close()
