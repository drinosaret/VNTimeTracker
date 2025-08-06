"""Configuration management utilities."""

import json
import os
import threading
from typing import Dict, Any, Optional, List

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

    @property
    def manual_vns(self) -> List[str]:
        """Get list of manually added VNs."""
        return self.get("manual_vns", [])
    
    @property
    def vndb_vns(self) -> Dict[str, Dict[str, Any]]:
        """Get VNDB VNs with their metadata."""
        return self.get("vndb_vns", {})

    def add_manual_vn(self, title: str) -> None:
        """Add a manually registered VN to the list."""
        if title and title.strip():
            manual_vns = self.manual_vns
            title = title.strip()
            if title not in manual_vns:
                manual_vns.append(title)
                self.update({"manual_vns": manual_vns})
                self.save()
    
    def add_vndb_vn(self, title: str, vndb_id: str, vndb_data: Dict[str, Any] = None) -> None:
        """Add a VN from VNDB with its ID and metadata."""
        if title and title.strip() and vndb_id:
            title = title.strip()
            vndb_vns = self.vndb_vns
            
            vndb_vns[title] = {
                "vndb_id": vndb_id,
                "data": vndb_data or {},
                "added_date": __import__("time").time()
            }
            self.update({"vndb_vns": vndb_vns})
            self.save()
    
    def get_vndb_id(self, title: str) -> Optional[str]:
        """Get the VNDB ID for a VN title."""
        if not title:
            return None
        vndb_vns = self.vndb_vns
        return vndb_vns.get(title.strip(), {}).get("vndb_id")
    
    def get_vndb_data(self, title: str) -> Optional[Dict[str, Any]]:
        """Get the stored VNDB data for a VN title."""
        if not title:
            return None
        vndb_vns = self.vndb_vns
        return vndb_vns.get(title.strip(), {}).get("data")

    def remove_manual_vn(self, title: str) -> None:
        """Remove a manually registered VN from the list."""
        if title and title.strip():
            manual_vns = self.manual_vns
            title = title.strip()
            if title in manual_vns:
                manual_vns.remove(title)
                self.update({"manual_vns": manual_vns})
                self.save()
    
    def remove_vndb_vn(self, title: str) -> None:
        """Remove a VNDB VN from the list."""
        if title and title.strip():
            title = title.strip()
            vndb_vns = self.vndb_vns
            
            if title in vndb_vns:
                del vndb_vns[title]
                self.update({"vndb_vns": vndb_vns})
                self.save()

    def get_all_library_vns(self) -> List[str]:
        """Get all VNs in the library (manual + VNDB + from process mapping)."""
        all_vns = set()
        all_vns.update(self.manual_vns)
        all_vns.update(self.vndb_vns.keys())
        all_vns.update(self.process_to_vn.keys())
        return sorted(list(all_vns))

    def remove_vn_completely(self, title: str) -> None:
        """Remove a VN completely from manual_vns, vndb_vns, and process_to_vn mapping."""
        if title and title.strip():
            title = title.strip()
            changes_made = False
            
            # Remove from manual VNs if it exists there
            manual_vns = self.manual_vns
            if title in manual_vns:
                manual_vns.remove(title)
                self.update({"manual_vns": manual_vns})
                changes_made = True
            
            # Remove from VNDB VNs if it exists there
            vndb_vns = self.vndb_vns
            if title in vndb_vns:
                del vndb_vns[title]
                self.update({"vndb_vns": vndb_vns})
                changes_made = True
            
            # Remove from process mapping if it exists there
            process_mapping = self.process_to_vn
            if title in process_mapping:
                del process_mapping[title]
                self.update({"process_to_vn": process_mapping})
                changes_made = True
            
            # Save only if changes were made
            if changes_made:
                self.save()

    def delete_vn_tracking_data(self, title: str) -> None:
        """Delete all tracking data for a VN from timelog.json."""
        if not title or not title.strip():
            return
        
        title = title.strip()
        timelog_file = os.path.join(os.path.dirname(self.config_file), "timelog.json")
        
        try:
            # Load existing timelog data
            if os.path.exists(timelog_file):
                with open(timelog_file, "r", encoding="utf-8") as f:
                    timelog_data = json.load(f)
                
                # Remove the VN's tracking data if it exists
                if title in timelog_data:
                    del timelog_data[title]
                    
                    # Save the updated timelog
                    with open(timelog_file, "w", encoding="utf-8") as f:
                        json.dump(timelog_data, f, indent=2, ensure_ascii=False)
                    
                    print(f"Deleted tracking data for '{title}'")
                else:
                    print(f"No tracking data found for '{title}'")
            else:
                print("No timelog.json file found")
                
        except Exception as e:
            print(f"Error deleting tracking data for '{title}': {e}")

    def remove_vn_completely_with_data(self, title: str) -> None:
        """Remove a VN completely including all tracking data and cached image."""
        if title and title.strip():
            # Remove VN from config (library and process mapping)
            self.remove_vn_completely(title)
            # Delete tracking data
            self.delete_vn_tracking_data(title)
            # Delete cached image
            self.delete_vn_image_cache(title)
    
    def delete_vn_image_cache(self, title: str) -> None:
        """Delete cached image for a VN."""
        if not title or not title.strip():
            return
        
        title = title.strip()
        # Image cache directory is usually in the same directory as config
        image_cache_dir = os.path.join(os.path.dirname(self.config_file), "image_cache")
        
        if not os.path.exists(image_cache_dir):
            return
        
        try:
            import urllib.parse
            # The image file name is URL-encoded title + .jpg
            image_filename = f"{urllib.parse.quote(title, safe='')}.jpg"
            image_path = os.path.join(image_cache_dir, image_filename)
            
            if os.path.exists(image_path):
                os.remove(image_path)
                print(f"Deleted cached image for '{title}': {image_filename}")
            else:
                print(f"No cached image found for '{title}'")
                
        except Exception as e:
            print(f"Error deleting cached image for '{title}': {e}")
