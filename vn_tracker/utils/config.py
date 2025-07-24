"""Configuration management utilities."""

import json
import os
import threading
from typing import Dict, Any, Optional

DEFAULT_GOAL_MINUTES = 90
DEFAULT_AFK_THRESHOLD = 60


class ConfigManager:
    """Application configuration management."""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self._config: Dict[str, Any] = {}
        self._lock = threading.RLock()  # Reentrant lock for config access
        self.load()
    
    def load(self) -> None:
        """Load configuration from file."""
        with self._lock:
            try:
                if os.path.exists(self.config_file):
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        self._config = json.load(f)
                else:
                    self._config = {}
            except Exception as e:
                print(f"Configuration load error: {e}")
                self._config = {}
    
    def save(self) -> None:
        """Save configuration to file."""
        with self._lock:
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(self._config, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Configuration save error: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        with self._lock:
            return self._config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        with self._lock:
            self._config[key] = value
    
    def update(self, data: Dict[str, Any]) -> None:
        """Update multiple configuration values."""
        with self._lock:
            self._config.update(data)
    
    @property
    def data(self) -> Dict[str, Any]:
        """Get all configuration data."""
        return self._config.copy()
    
    @property
    def goal_minutes(self) -> int:
        """Get goal minutes with default."""
        return self.get("goal_minutes", DEFAULT_GOAL_MINUTES)
    
    @property
    def afk_threshold(self) -> int:
        """Get AFK threshold with default."""
        return self.get("afk_threshold", DEFAULT_AFK_THRESHOLD)
    
    @property
    def overlay_alpha(self) -> float:
        """Get overlay alpha with default."""
        return self.get("overlay_alpha", 0.8)
    
    @property
    def last_vn(self) -> str:
        """Get last selected VN."""
        return self.get("last_vn", "")
    
    @property
    def process_to_vn(self) -> Dict[str, str]:
        """Get process to VN mapping."""
        return self.get("process_to_vn", {})
    
    @property
    def language(self) -> str:
        """Get language setting."""
        return self.get("language", "en")
    
    @property
    def show_overlay(self) -> bool:
        """Get overlay visibility setting."""
        return self.get("show_overlay", True)
    
    @property
    def show_overlay_percentage(self) -> bool:
        """Get overlay goal percentage visibility setting."""
        return self.get("show_overlay_percentage", False)
