"""PyQt5-based overlay window for time display."""

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPainter, QColor


class OverlayWindow(QWidget):
    """PyQt5 overlay window for displaying time."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Initialize color variables for custom painting
        self._bg_color = QColor(30, 30, 30, 200)  # Default dark background
        self._text_color = QColor(255, 255, 255)  # Default white text
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the overlay UI."""
        # Window properties
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Variables for dragging
        self.dragging = False
        self.drag_position = None
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Time label
        self.time_label = QLabel("00:00:00")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.time_label.setFont(font)
        self.time_label.setAlignment(Qt.AlignCenter)
        
        # Remove background styling from label since we'll paint it manually
        self.time_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #ffffff;
                border: none;
                padding: 4px 8px;
                font-weight: bold;
            }
        """)
        # Store initial style
        self._current_style = self.time_label.styleSheet()
        
        layout.addWidget(self.time_label)
        
        # Set initial size and position (top-right corner for less intrusion)
        self.resize(120, 40)
        self.move(20, 20)
    
    def update_time(self, time_str: str):
        """Update the displayed time and force repaint."""
        self.time_label.setText(time_str)
        # Force a repaint to ensure background is always drawn
        self.update()
    
    def paintEvent(self, event):
        """Custom paint event to ensure background tint always persists."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw the background with rounded corners
        rect = self.rect().adjusted(2, 2, -2, -2)  # Small margin for border
        painter.setBrush(self._bg_color)
        painter.setPen(QColor(100, 100, 100, 150))  # Border color
        painter.drawRoundedRect(rect, 6, 6)
        
        super().paintEvent(event)
    
    def set_alpha(self, alpha: float):
        """Set the overlay transparency and store it for persistence."""
        self.setWindowOpacity(alpha)
        self._current_opacity = alpha
    
    def show_overlay(self):
        """Show the overlay."""
        self.show()
        self.raise_()
    
    def hide_overlay(self):
        """Hide the overlay."""
        self.hide()
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging."""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging."""
        if event.buttons() == Qt.LeftButton and self.dragging:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop dragging."""
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()
    
    def set_color(self, bg_rgba, fg_color):
        """Set the overlay background and text color dynamically and store for persistence."""
        # Parse RGBA string to QColor
        if bg_rgba.startswith("rgba(") and bg_rgba.endswith(")"):
            # Extract values from rgba(r, g, b, a) format
            values = bg_rgba[5:-1].split(',')
            if len(values) == 4:
                r, g, b, a = [int(v.strip()) for v in values]
                self._bg_color = QColor(r, g, b, a)
        
        # Update text color
        if fg_color.startswith("#"):
            self._text_color = QColor(fg_color)
        else:
            self._text_color = QColor(fg_color)
        
        # Update label text color
        style = f"""
            QLabel {{
                background-color: transparent;
                color: {fg_color};
                border: none;
                padding: 4px 8px;
                font-weight: bold;
            }}
        """
        self.time_label.setStyleSheet(style)
        self._current_style = style
        
        # Force repaint to show new colors
        self.update()
