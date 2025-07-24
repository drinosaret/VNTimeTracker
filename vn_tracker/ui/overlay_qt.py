"""PyQt5-based overlay window for time display."""

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPainter, QColor


class OverlayWindow(QWidget):
    """Overlay window for time and goal progress display."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Default color configuration
        self._bg_color = QColor(30, 30, 30, 200)
        self._text_color = QColor(255, 255, 255)
        self.setup_ui()
    
    def setup_ui(self):
        """Initialize overlay interface."""
        # Window properties
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Drag state variables
        self.dragging = False
        self.drag_position = None
        
        # Layout configuration
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(0)
        
        # Time label configuration
        self.time_label = QLabel("00:00:00")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.time_label.setFont(font)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setFixedHeight(25)
        
        # Percentage label configuration
        self.percentage_label = QLabel("")
        percentage_font = QFont()
        percentage_font.setPointSize(10)
        percentage_font.setBold(True)
        self.percentage_label.setFont(percentage_font)
        self.percentage_label.setAlignment(Qt.AlignCenter)
        self.percentage_label.setFixedHeight(20)
        self.percentage_label.hide()
        
        # Time label styling
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
        
        # Percentage label styling
        self.percentage_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #ffffff;
                border: none;
                padding: 2px 8px;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(self.time_label)
        layout.addWidget(self.percentage_label)
        
        # Initial size and position
        self.setFixedSize(120, 35)
        self.move(20, 20)
    
    def update_time(self, time_str: str):
        """Update displayed time text."""
        if self.time_label.text() != time_str:
            self.time_label.setText(time_str)
    
    def update_percentage(self, percentage: float):
        """Update displayed goal percentage."""
        new_text = f"{percentage:.1f}%"
        if self.percentage_label.text() != new_text:
            self.percentage_label.setText(new_text)
    
    def set_show_percentage(self, show: bool):
        """Toggle percentage label visibility."""
        if show:
            self.percentage_label.show()
            self.setFixedSize(120, 55)
        else:
            self.percentage_label.hide()
            self.setFixedSize(120, 35)
    
    def paintEvent(self, event):
        """Draw overlay background with robust painter handling."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.setBrush(self._bg_color)
        painter.setPen(QColor(100, 100, 100, 150))
        painter.drawRoundedRect(rect, 6, 6)
        painter.end()
        super().paintEvent(event)
    
    def set_alpha(self, alpha: float):
        """Set overlay transparency."""
        self.setWindowOpacity(alpha)
        self._current_opacity = alpha
    
    def show_overlay(self):
        """Display overlay window."""
        self.show()
        self.raise_()
    
    def hide_overlay(self):
        """Hide overlay window."""
        self.hide()
    
    def mousePressEvent(self, event):
        """Handle drag initiation."""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle window dragging."""
        if event.buttons() == Qt.LeftButton and self.dragging:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Handle drag completion."""
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()
    
    def set_color(self, bg_rgba, fg_color):
        """Set overlay background and text colors."""
        try:
            # Parse RGBA background color
            new_bg_color = None
            if bg_rgba.startswith("rgba(") and bg_rgba.endswith(")"):
                values = bg_rgba[5:-1].split(',')
                if len(values) == 4:
                    r, g, b, a = [int(v.strip()) for v in values]
                    new_bg_color = QColor(r, g, b, a)
            
            # Set text color
            new_text_color = None
            if fg_color.startswith("#"):
                new_text_color = QColor(fg_color)
            else:
                new_text_color = QColor(fg_color)
            
            # Only update if colors actually changed
            color_changed = False
            if new_bg_color and new_bg_color != self._bg_color:
                self._bg_color = new_bg_color
                color_changed = True
                
            if new_text_color and new_text_color != self._text_color:
                self._text_color = new_text_color
                color_changed = True
                
                # Apply text color to labels
                style = f"""
                    QLabel {{
                        background-color: transparent;
                        color: {fg_color};
                        border: none;
                        padding: 4px 8px;
                        font-weight: bold;
                    }}
                """
                percentage_style = f"""
                    QLabel {{
                        background-color: transparent;
                        color: {fg_color};
                        border: none;
                        padding: 2px 8px;
                        font-weight: bold;
                    }}
                """
                self.time_label.setStyleSheet(style)
                self.percentage_label.setStyleSheet(percentage_style)
                self._current_style = style
            
            # Only trigger repaint if colors actually changed
            if color_changed:
                self.update()
            
        except Exception as e:
            print(f"Overlay color change error: {e}")
