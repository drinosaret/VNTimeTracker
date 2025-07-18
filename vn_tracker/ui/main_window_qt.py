"""PyQt5-based main application window for superior performance."""

import os
import sys
from typing import Optional, List, Dict, Any
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar,
    QTabWidget, QFrame, QGroupBox, QCheckBox, QSlider,
    QMessageBox, QFileDialog, QSystemTrayIcon, QMenu, QAction,
    QSplitter, QScrollArea, QSpinBox
)
from PyQt5.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QSize, QSettings,
    QStandardPaths, pyqtSlot, QMetaType
)
from PyQt5.QtGui import QPixmap, QIcon, QFont, QPalette

from ..core.tracker import TimeTracker, TrackingState
from ..utils.config import ConfigManager
from ..utils.system_utils import format_time
from ..utils.i18n import I18nManager

# Suppress Qt threading warnings by redirecting Qt messages
def qt_message_handler(mode, context, message):
    """Custom Qt message handler to suppress harmless threading warnings."""
    # Suppress these specific warnings that are not harmful but noisy
    if "QBasicTimer::start: QBasicTimer can only be used with threads started with QThread" in message:
        return
    if "Cannot queue arguments of type 'QItemSelection'" in message:
        return
    # Print other Qt messages normally
    print(f"Qt: {message}")

# Install the custom message handler
try:
    from PyQt5.QtCore import qInstallMessageHandler
    qInstallMessageHandler(qt_message_handler)
except ImportError:
    # Not available in this PyQt5 version
    pass


class VNSearchWorker(QThread):
    """Background thread for VN searches to keep UI responsive."""
    
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


class VNTrackerMainWindow(QMainWindow):
    """PyQt5 main window for VN Tracker."""
    
    def __init__(self, config_file: str, log_file: str, image_cache_dir: str):
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
        
        # System tray
        self.tray_icon = None
        self.setup_system_tray()
        
        # Worker threads
        self.search_worker = None
        self.image_worker = None
        
        # Setup UI first (fastest)
        self.setup_ui()
        self.setup_connections()
        
        # Show window immediately
        ui_ready_time = time.time()
        print(f"UI ready in {ui_ready_time - self.startup_time:.3f} seconds")
        
        # Initialize heavy components asynchronously
        QTimer.singleShot(100, self.initialize_heavy_components)
    
    def setup_ui(self):
        """Setup the user interface with PyQt5."""
        self.setWindowTitle(self.i18n.t("app_title"))
        self.setMinimumSize(650, 600)  # Slightly wider minimum to prevent text cutoff
        self.resize(750, 600)  # Slightly wider default size
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout - horizontal splitter
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)  # Minimal margins around the main content
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - VN Selection
        self.create_selection_panel(splitter)
        
        # Right panel - Tracking and Settings
        self.create_tracking_panel(splitter)
        
        # Set splitter proportions (slightly wider left panel)
        splitter.setSizes([320, 430])
        
        # Apply modern styling
        self.apply_modern_style()
    
    def create_selection_panel(self, parent):
        """Create the VN selection panel."""
        selection_widget = QWidget()
        layout = QVBoxLayout(selection_widget)
        layout.setSpacing(8)  # Moderate spacing between major sections
        layout.setContentsMargins(6, 6, 6, 6)  # Smaller margin around the entire panel
        
        # Search section
        search_group = QGroupBox(self.i18n.t("vn_search"))
        search_group.setObjectName("search_group")  # Add object name for consistent styling
        # Remove inline styling to prevent conflicts with global stylesheet
        search_layout = QVBoxLayout(search_group)
        search_layout.setSpacing(6)  # Moderate spacing to prevent overlap
        search_layout.setContentsMargins(12, 10, 12, 10)  # Reasonable margins
        
        # Search input
        search_input_layout = QHBoxLayout()
        search_input_layout.setSpacing(5)  # Reduce spacing between input and button
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search for visual novels...")
        self.search_button = QPushButton(self.i18n.t("search"))
        self.search_button.setMaximumWidth(80)  # Make search button more compact
        
        search_input_layout.addWidget(self.search_entry)
        search_input_layout.addWidget(self.search_button)
        search_layout.addLayout(search_input_layout)
        
        # Add small spacing after search input
        search_layout.addSpacing(4)
        
        # VN dropdown with better spacing
        search_layout.addWidget(QLabel(self.i18n.t("select_vn")))
        self.vn_dropdown = QComboBox()
        self.vn_dropdown.setEditable(False)
        self.vn_dropdown.setMinimumHeight(32)
        search_layout.addWidget(self.vn_dropdown)
        
        # Add small spacing after VN dropdown
        search_layout.addSpacing(4)
        
        # Process dropdown with refresh button
        search_layout.addWidget(QLabel(self.i18n.t("select_process")))
        
        process_layout = QHBoxLayout()
        process_layout.setSpacing(5)  # Reduce spacing between dropdown and button
        self.process_dropdown = QComboBox()
        self.process_dropdown.setMinimumHeight(32)
        self.refresh_processes_button = QPushButton("Refresh")
        self.refresh_processes_button.setMaximumWidth(90)  # Slightly wider to prevent text cutoff
        self.refresh_processes_button.setMinimumHeight(32)  # Match dropdown height
        self.refresh_processes_button.setMaximumHeight(32)
        self.refresh_processes_button.setToolTip("Refresh process list to include newly started programs")
        
        process_layout.addWidget(self.process_dropdown, 1)  # Give dropdown more space
        process_layout.addWidget(self.refresh_processes_button, 0)  # Button with fixed proportions
        
        search_layout.addLayout(process_layout)
        
        # Set target button with proper spacing
        search_layout.addSpacing(8)  # Moderate spacing before button
        self.set_target_button = QPushButton(self.i18n.t("select_game_process"))
        search_layout.addWidget(self.set_target_button)
        
        # Status and loading labels with proper spacing
        search_layout.addSpacing(10)  # Moderate space before status section
        
        # Status label
        self.status_label = QLabel(f"{self.i18n.t('tracking')}: {self.i18n.t('not_selected')}")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(18)  # Reasonable minimum height
        search_layout.addWidget(self.status_label)
        
        # Loading indicator with minimal spacing
        search_layout.addSpacing(4)  # Small spacing before loading indicator
        
        # Loading indicator
        self.loading_label = QLabel("🔄 Loading components...")
        self.loading_label.setStyleSheet("color: #0078d4; font-weight: bold; margin: 0px; padding: 1px;")
        self.loading_label.setWordWrap(True)  # Enable word wrapping
        self.loading_label.setMinimumHeight(36)  # Increased height to accommodate wrapped text
        self.loading_label.setMinimumWidth(200)  # Ensure minimum width to prevent excessive wrapping
        self.loading_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)  # Align to top
        self.loading_label.setContentsMargins(0, 0, 0, 0)  # Remove any content margins
        search_layout.addWidget(self.loading_label)
        
        layout.addWidget(search_group)
        
        # Cover image
        cover_group = QGroupBox(self.i18n.t("cover_image"))
        cover_layout = QVBoxLayout(cover_group)
        cover_layout.setContentsMargins(12, 8, 12, 10)  # Moderate margins for cover image group
        
        # Create horizontal layout to center the image
        cover_h_layout = QHBoxLayout()
        cover_h_layout.addStretch()  # Left spacer
        
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(150, 210)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setScaledContents(False)  # Don't stretch, keep aspect ratio
        self.cover_label.setStyleSheet("border: 1px solid #cccccc; background-color: #ffffff; color: #666666;")
        self.cover_label.setText("No Image")
        
        cover_h_layout.addWidget(self.cover_label)
        cover_h_layout.addStretch()  # Right spacer
        
        cover_layout.addLayout(cover_h_layout)
        
        layout.addWidget(cover_group)
        layout.addStretch()
        
        parent.addWidget(selection_widget)
    
    def create_tracking_panel(self, parent):
        """Create the tracking and settings panel."""
        tracking_widget = QWidget()
        layout = QVBoxLayout(tracking_widget)
        layout.setSpacing(8)  # Moderate spacing between major sections
        layout.setContentsMargins(6, 6, 6, 6)  # Smaller margin around the entire panel
        
        # Time display
        time_group = QGroupBox(self.i18n.t("time_tracking"))
        time_layout = QVBoxLayout(time_group)
        time_layout.setSpacing(6)  # Moderate spacing within time group
        time_layout.setContentsMargins(12, 8, 12, 8)  # Reasonable margins
        
        self.time_label = QLabel(f"{self.i18n.t('today_reading_time')}: 00:00:00")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.time_label.setFont(font)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setWordWrap(True)  # Enable word wrapping
        self.time_label.setMinimumHeight(40)  # Ensure minimum height for the text
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
        
        stats_layout.addWidget(self.week_label)
        stats_layout.addWidget(self.month_label)
        
        layout.addWidget(stats_group)
        
        # Settings tabs
        self.create_settings_tabs(layout)
        
        # Action buttons
        self.create_action_buttons(layout)
        
        parent.addWidget(tracking_widget)
    
    def create_settings_tabs(self, layout):
        """Create settings tabs."""
        tab_widget = QTabWidget()
        
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
        tab_widget.addTab(goal_tab, self.i18n.t("goal_settings"))
        
        # Overlay settings tab
        overlay_tab = QWidget()
        overlay_layout = QVBoxLayout(overlay_tab)
        overlay_layout.setSpacing(8)  # Moderate spacing between elements
        overlay_layout.setContentsMargins(10, 10, 10, 10)  # Reasonable tab margins
        
        self.overlay_checkbox = QCheckBox(self.i18n.t("show_overlay"))
        self.overlay_checkbox.setChecked(self.config_manager.show_overlay)
        overlay_layout.addWidget(self.overlay_checkbox)
        
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
        tab_widget.addTab(overlay_tab, self.i18n.t("overlay_settings"))
        
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
        tab_widget.addTab(language_tab, self.i18n.t("language_settings"))
        
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
        """Apply modern light theme styling."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
                color: #333333;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin: 5px 0px;
                padding-top: 15px;
                padding-bottom: 10px;
                background-color: #ffffff;
                color: #333333;
            }
            /* Ensure consistent styling for all group boxes */
            QGroupBox[objectName="search_group"] {
                background-color: #ffffff;
                border: 2px solid #cccccc;
                border-radius: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 22px;
                padding: 0 5px 0 5px;
                color: #333333;
            }
            QPushButton {
                background-color: #0078d4;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                color: #333333;
                padding: 5px;
                border-radius: 3px;
                selection-background-color: #0078d4;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 2px solid #0078d4;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                color: #333333;
                padding: 8px 12px;
                margin-right: 2px;
                border: 1px solid #cccccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                border-bottom: 1px solid #ffffff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #f0f0f0;
            }
            QProgressBar {
                border: 1px solid #cccccc;
                border-radius: 5px;
                text-align: center;
                background-color: #ffffff;
                color: #333333;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 4px;
            }
            QCheckBox {
                color: #333333;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #cccccc;
                background-color: #ffffff;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #0078d4;
                background-color: #0078d4;
                border-radius: 3px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #cccccc;
                height: 8px;
                background: #ffffff;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                border: 1px solid #0078d4;
                width: 18px;
                border-radius: 9px;
                margin: -5px 0px;
            }
            QSlider::handle:horizontal:hover {
                background: #106ebe;
                border: 1px solid #106ebe;
            }
            QLabel {
                color: #333333;
            }
        """)
    
    def setup_connections(self):
        """Setup signal connections for UI components only."""
        # Search connections
        self.search_button.clicked.connect(self.search_vn)
        self.search_entry.returnPressed.connect(self.search_vn)
        
        # Process refresh
        self.refresh_processes_button.clicked.connect(self.refresh_process_list)
        
        # Target setting
        self.set_target_button.clicked.connect(self.set_target)
        
        # VN selection
        self.vn_dropdown.currentTextChanged.connect(self.on_vn_selected)
        
        # Action buttons
        self.reset_button.clicked.connect(self.reset_today)
        self.export_button.clicked.connect(self.export_data)
        self.minimize_tray_button.clicked.connect(self.minimize_to_tray)
        
        # Settings
        self.overlay_checkbox.toggled.connect(self.toggle_overlay)
        self.transparency_slider.valueChanged.connect(self.update_transparency)
    
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
            
            # Set icon (you can add an actual icon file later)
            self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
            self.tray_icon.show()
    
    def load_initial_data(self):
        """Load initial data asynchronously."""
        # Load process list
        QTimer.singleShot(100, self.load_process_list)
        
        # Load last VN if available
        last_vn = self.config_manager.last_vn
        if last_vn:
            QTimer.singleShot(200, lambda: self.search_vn(last_vn))
    
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
    def search_vn(self, query=None):
        """Search for VNs asynchronously."""
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
        self.search_button.setText("Searching...")
        
        # Start background search
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.terminate()
            self.search_worker.wait()
        
        self.search_worker = VNSearchWorker(self.vndb_client, query)
        # Don't set parent or move to thread - let it manage its own threading
        self.search_worker.search_completed.connect(self.on_search_completed, Qt.QueuedConnection)
        self.search_worker.start()
    
    @pyqtSlot(list)
    def on_search_completed(self, results):
        """Handle search completion."""
        self.search_button.setEnabled(True)
        self.search_button.setText(self.i18n.t("search"))
        
        self.vn_dropdown.clear()
        self.vn_dropdown.addItems(results)
        
        if results and self.search_entry.text().strip():
            # Try to select exact match
            exact_match = self.search_entry.text().strip()
            index = self.vn_dropdown.findText(exact_match)
            if index >= 0:
                self.vn_dropdown.setCurrentIndex(index)
    
    @pyqtSlot(str)
    def on_vn_selected(self, title):
        """Handle VN selection."""
        # Safety check - don't load image if VNDB client isn't ready
        if not self.vndb_client:
            return
            
        if title:
            # Load cover image asynchronously
            self.cover_label.setText("Loading...")
            
            if self.image_worker and self.image_worker.isRunning():
                self.image_worker.terminate()
                self.image_worker.wait()
            
            self.image_worker = ImageLoadWorker(self.vndb_client, title)
            # Don't set parent or move to thread - let it manage its own threading
            self.image_worker.image_loaded.connect(self.on_image_loaded, Qt.QueuedConnection)
            self.image_worker.start()
    
    @pyqtSlot(object)
    def on_image_loaded(self, image_data):
        """Handle image loading completion."""
        if image_data:
            # Convert raw image data to QPixmap
            try:
                pixmap = QPixmap()
                if pixmap.loadFromData(image_data):
                    # Scale the image to fit the label
                    scaled_pixmap = pixmap.scaled(150, 210, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.cover_label.setPixmap(scaled_pixmap)
                else:
                    self.cover_label.setText("Image Format Error")
            except Exception as e:
                print(f"Image display error: {e}")
                self.cover_label.setText("Image Error")
        else:
            self.cover_label.setText("No Image")
    
    @pyqtSlot()
    def set_target(self):
        """Set the tracking target."""
        # Safety check - don't set target if tracker isn't ready
        if not self.tracker:
            QMessageBox.information(self, "Please Wait", "Application is still loading...")
            return
            
        vn_title = self.vn_dropdown.currentText()
        process_name = self.process_dropdown.currentText()
        
        if vn_title and process_name:
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
        else:
            QMessageBox.warning(self, "Warning", self.i18n.t("invalid_selection"))
    
    def update_display(self):
        """Update the display with current data."""
        # Safety check - don't update if components aren't loaded yet
        if not self.tracker:
            return
            
        try:
            # Get real-time seconds including current tracking session
            today_seconds = self.tracker.get_current_seconds()
            time_str = format_time(today_seconds)
            self.time_label.setText(f"{self.i18n.t('today_reading_time')}: {time_str}")

            # Update progress bar
            self.progress_bar.setValue(min(today_seconds, self.progress_bar.maximum()))

            # Update statistics
            week_minutes = self.tracker.get_weekly_seconds() // 60
            month_minutes = self.tracker.get_monthly_seconds() // 60

            self.week_label.setText(f"{self.i18n.t('weekly')}: {week_minutes} {self.i18n.t('minutes')}")
            self.month_label.setText(f"{self.i18n.t('monthly')}: {month_minutes} {self.i18n.t('minutes')}")

            # Update overlay time only (color is handled by state change callback)
            if self.overlay and self.config_manager.show_overlay:
                self.overlay.update_time(time_str)
        except Exception as e:
            print(f"Display update error: {e}")
    
    def on_tracking_state_changed(self, state: TrackingState, current_seconds: int):
        """Handle tracking state changes."""
        # Update time display immediately with the passed current_seconds to ensure sync
        time_str = format_time(current_seconds)
        self.time_label.setText(f"{self.i18n.t('today_reading_time')}: {time_str}")
        
        # Update time label color based on tracking state
        if state == TrackingState.ACTIVE:
            # Green for active tracking
            self.time_label.setStyleSheet("""
                QLabel {
                    color: #2d5f2d;
                    background-color: rgba(144, 238, 144, 0.3);
                    border: 2px solid #90EE90;
                    border-radius: 5px;
                    padding: 5px;
                    font-weight: bold;
                }
            """)
        elif state == TrackingState.AFK:
            # Yellow for AFK
            self.time_label.setStyleSheet("""
                QLabel {
                    color: #b8860b;
                    background-color: rgba(255, 255, 0, 0.2);
                    border: 2px solid #FFD700;
                    border-radius: 5px;
                    padding: 5px;
                    font-weight: bold;
                }
            """)
        else:  # INACTIVE
            # Red for inactive
            self.time_label.setStyleSheet("""
                QLabel {
                    color: #8b0000;
                    background-color: rgba(255, 182, 193, 0.3);
                    border: 2px solid #FF6B6B;
                    border-radius: 5px;
                    padding: 5px;
                    font-weight: bold;
                }
            """)
        
        # Also update overlay color and time immediately when state changes
        if self.overlay and self.config_manager.show_overlay:
            # Update overlay immediately on state change for responsive feedback
            self.update_overlay_color(state)
            self.overlay.update_time(time_str)
    
    def on_tracking_updated(self):
        """Handle tracking data updates."""
        # Don't update overlay here - let update_display handle it to avoid conflicts
        pass
    
    def on_process_list_updated(self, processes):
        """Handle process list updates."""
        current_process = self.process_dropdown.currentText()
        self.process_dropdown.clear()
        self.process_dropdown.addItems(processes)
        
        # Restore selection if possible
        index = self.process_dropdown.findText(current_process)
        if index >= 0:
            self.process_dropdown.setCurrentIndex(index)
    
    @pyqtSlot()
    def set_goal(self):
        """Set the goal time."""
        minutes = self.goal_spinbox.value()
        self.progress_bar.setMaximum(minutes * 60)
        self.config_manager.set("goal_minutes", minutes)
        self.config_manager.save()
        
        QMessageBox.information(self, "Success", f"Goal set to {minutes} minutes")
    
    @pyqtSlot()
    def set_afk_threshold(self):
        """Set the AFK threshold."""
        # Safety check - don't set threshold if tracker isn't ready
        if not self.tracker:
            QMessageBox.information(self, "Please Wait", "Application is still loading...")
            return
            
        seconds = self.afk_spinbox.value()
        self.tracker.set_afk_threshold(seconds)
        self.config_manager.set("afk_threshold", seconds)
        self.config_manager.save()
        
        QMessageBox.information(self, "Success", f"AFK threshold set to {seconds} seconds")
    
    @pyqtSlot()
    def set_language(self):
        """Set the application language."""
        lang_code = self.language_dropdown.currentData()
        if lang_code:
            self.i18n.set_language(lang_code)
            QMessageBox.information(self, "Success", "Language changed. Please restart the application.")
    
    @pyqtSlot(bool)
    def toggle_overlay(self, show):
        """Toggle overlay visibility."""
        self.config_manager.set("show_overlay", show)
        self.config_manager.save()
        
        if self.overlay:
            if show:
                self.overlay.show()
            else:
                self.overlay.hide()
    
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
        
        if self.image_worker and self.image_worker.isRunning():
            self.image_worker.terminate()
            self.image_worker.wait(1000)  # Wait max 1 second
            if self.image_worker.isRunning():
                self.image_worker.kill()
        
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
            
            # Show overlay if enabled
            if self.config_manager.show_overlay:
                self.overlay.show()
    
    def update_overlay_color(self, state):
        """Update overlay color based on tracking state."""
        if not self.overlay:
            return
            
        # Always set a color regardless of state
        if state == TrackingState.ACTIVE:
            self.overlay.set_color("rgba(40, 80, 40, 200)", "#ffffff")
        elif state == TrackingState.AFK:
            self.overlay.set_color("rgba(100, 80, 0, 200)", "#ffffff")
        else:  # INACTIVE or None - use red for inactive
            self.overlay.set_color("rgba(80, 40, 40, 200)", "#ffffff")
    
    def initialize_heavy_components(self):
        """Initialize heavy components asynchronously after UI is shown."""
        try:
            import time
            heavy_start = time.time()
            
            # Update loading indicator with progress
            self.loading_label.setText("🔄 Loading data manager...")
            
            # Lazy import and initialize components one by one for better feedback
            from ..utils.data_storage import TimeDataManager
            self.data_manager = TimeDataManager(self.log_file)
            
            self.loading_label.setText("🔄 Loading process monitor...")
            from ..core.process_monitor import ProcessMonitor
            self.process_monitor = ProcessMonitor()
            
            self.loading_label.setText("🔄 Loading VNDB client...")
            from ..core.vndb_api import VNDBClient
            self.vndb_client = VNDBClient(self.image_cache_dir)
            
            self.loading_label.setText("🔄 Initializing tracker...")
            # Initialize tracker
            self.tracker = TimeTracker(self.data_manager, self.process_monitor)
            
            # Load AFK threshold from config
            self.tracker.set_afk_threshold(self.config_manager.afk_threshold)
            
            self.loading_label.setText("🔄 Setting up overlay...")
            from .overlay_qt import OverlayWindow
            self.overlay = OverlayWindow()
            
            self.loading_label.setText("🔄 Connecting components...")
            # Setup connections that require heavy components with proper threading
            self.tracker.add_state_callback(self.on_tracking_state_changed)
            self.tracker.add_update_callback(self.on_tracking_updated)
            self.process_monitor.add_process_list_callback(self.on_process_list_updated)
            
            # Setup timers for updates (fix threading issue)
            self.update_timer = QTimer(self)  # Parent the timer to this widget
            self.update_timer.timeout.connect(self.update_display)
            self.update_timer.start(1000)  # Update every second
            
            self.loading_label.setText("🔄 Starting services...")
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
            
            # More concise ready message that fits better
            self.loading_label.setText(f"✅ Ready! ({ui_time:.1f}s + {heavy_time:.1f}s = {total_time:.1f}s)")
            self.loading_label.setStyleSheet("color: #2d5f2d; font-weight: bold; margin: 0px; padding: 2px;")
            self.loading_label.setContentsMargins(0, 0, 0, 0)  # Ensure no margins for ready state
            
            print(f"Heavy components loaded in {heavy_time:.3f} seconds")
            print(f"Total startup time: {total_time:.3f} seconds")
            print(f"Performance improvement: UI responsive {heavy_time:.3f}s earlier!")
            
        except Exception as e:
            print(f"Error initializing heavy components: {e}")
            # Show error to user
            self.loading_label.setText("❌ Failed to load components")
            self.loading_label.setStyleSheet("color: #8b0000; font-weight: bold; margin: 0px; padding: 2px;")
            self.loading_label.setContentsMargins(0, 0, 0, 0)  # Ensure no margins for error state
            QMessageBox.critical(self, "Initialization Error", 
                               f"Failed to initialize application components: {str(e)}")
            self.close()
