"""Data storage utilities for time tracking."""

import json
import os
import csv
import urllib.parse
import shutil
import threading
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class TimeDataManager:
    """Time tracking data storage with backup and recovery."""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.backup_file = log_file + ".backup"
        self.temp_file = log_file + ".tmp"
        self._data: Dict[str, Dict[str, int]] = {}
        self._lock = threading.Lock()
        self._pending_changes = False
        self.load()
    
    def _create_backup(self) -> None:
        """Create data file backup."""
        try:
            if os.path.exists(self.log_file):
                shutil.copy2(self.log_file, self.backup_file)
        except Exception as e:
            print(f"Backup creation error: {e}")
    
    def _recover_from_backup(self) -> bool:
        """Recover data from backup file."""
        try:
            if os.path.exists(self.backup_file):
                with open(self.backup_file, "r", encoding="utf-8") as f:
                    backup_data = json.load(f)
                self._data = backup_data
                print("Data recovered from backup")
                return True
        except Exception as e:
            print(f"Backup recovery error: {e}")
        return False
    
    def load(self) -> None:
        """Load time data from file."""
        with self._lock:
            try:
                if os.path.exists(self.log_file):
                    with open(self.log_file, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
                    self._pending_changes = False
                else:
                    self._data = {}
                    self._pending_changes = False
            except Exception as e:
                print(f"Time data load error: {e}")
                # Try to recover from backup
                if not self._recover_from_backup():
                    print("Creating new data file")
                    self._data = {}
                self._pending_changes = False
    
    def save(self, force_backup: bool = False) -> None:
        """Save time data with atomic write and backup."""
        # Use timeout to prevent deadlocks
        if self._lock.acquire(timeout=10.0):
            try:
                # Check if we have valid data to save
                if not hasattr(self, '_data') or self._data is None:
                    print("Warning: No data to save")
                    return
                
                # Create backup if changes exist or forced
                if self._pending_changes or force_backup:
                    self._create_backup()
                
                # Ensure temp file directory exists
                temp_dir = os.path.dirname(self.temp_file)
                if temp_dir and not os.path.exists(temp_dir):
                    os.makedirs(temp_dir, exist_ok=True)
                
                # Atomic write operation with error handling
                try:
                    with open(self.temp_file, "w", encoding="utf-8") as f:
                        json.dump(self._data, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"Failed to write temporary file: {e}")
                    raise
                
                # Atomic file replacement with validation
                if os.path.exists(self.temp_file):
                    # Verify the temp file was written correctly
                    try:
                        with open(self.temp_file, "r", encoding="utf-8") as f:
                            test_data = json.load(f)
                        
                        # Replace the main file
                        if os.path.exists(self.log_file):
                            os.replace(self.temp_file, self.log_file)
                        else:
                            os.rename(self.temp_file, self.log_file)
                        
                        self._pending_changes = False
                        
                    except Exception as e:
                        print(f"Failed to validate or replace file: {e}")
                        # Clean up temp file if replacement failed
                        try:
                            if os.path.exists(self.temp_file):
                                os.remove(self.temp_file)
                        except:
                            pass
                        raise
                else:
                    raise Exception("Temporary file was not created")
                    
            except Exception as e:
                print(f"Data save error: {e}")
                raise
            finally:
                self._lock.release()
        else:
            raise Exception("Failed to acquire data lock for save operation within timeout")
    
    def add_time(self, vn_title: str, seconds: int, date: Optional[str] = None) -> None:
        """Add time for a VN with improved thread safety."""
        if not vn_title or seconds <= 0:
            return
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # Use timeout to prevent deadlocks
        if self._lock.acquire(timeout=5.0):
            try:
                # Check if we have valid data structure
                if not hasattr(self, '_data') or self._data is None:
                    self._data = {}
                
                self._data.setdefault(vn_title, {})
                current_time = self._data[vn_title].get(date, 0)
                self._data[vn_title][date] = current_time + seconds
                self._pending_changes = True
            except Exception as e:
                print(f"Time addition error: {e}")
                raise  # Re-raise to allow caller to handle
            finally:
                self._lock.release()
        else:
            raise Exception("Failed to acquire data lock for add_time operation within timeout")
    
    def get_today_seconds(self, vn_title: str) -> int:
        """Get today's seconds for a VN."""
        if not vn_title:
            return 0
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            return self._data.get(vn_title, {}).get(today, 0)
        except Exception as e:
            print(f"Today's seconds retrieval error: {e}")
            return 0
    
    def get_weekly_seconds(self, vn_title: str) -> int:
        """Get weekly seconds for a VN."""
        if not vn_title:
            return 0
        
        try:
            total = 0
            today = datetime.now()
            for i in range(7):
                date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                total += self._data.get(vn_title, {}).get(date, 0)
            return total
        except Exception as e:
            print(f"Weekly seconds retrieval error: {e}")
            return 0
    
    def get_monthly_seconds(self, vn_title: str) -> int:
        """Get monthly seconds for a VN."""
        if not vn_title:
            return 0
        
        try:
            total = 0
            today = datetime.now()
            for i in range(30):
                date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                total += self._data.get(vn_title, {}).get(date, 0)
            return total
        except Exception as e:
            print(f"Monthly seconds retrieval error: {e}")
            return 0
    
    def get_total_seconds(self, vn_title: str) -> int:
        """Get total seconds for a VN across all time."""
        if not vn_title:
            return 0
        
        try:
            total = 0
            vn_data = self._data.get(vn_title, {})
            for date, seconds in vn_data.items():
                total += seconds
            return total
        except Exception as e:
            print(f"Total seconds retrieval error: {e}")
            return 0
    
    def emergency_save(self) -> None:
        """Execute emergency data save with fallback strategies."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        emergency_file = f"{self.log_file}.emergency_{timestamp}"
        
        try:
            # Try regular save first
            self.save(force_backup=True)
            print(f"Emergency save successful: regular save method")
        except Exception as e1:
            print(f"Regular save failed: {e1}")
            try:
                # Fallback: direct write to emergency file
                with open(emergency_file, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                print(f"Emergency save successful: {emergency_file}")
            except Exception as e2:
                print(f"Emergency save failed: {e2}")
                try:
                    # Last resort: write to text file
                    text_file = f"{self.log_file}.emergency_{timestamp}.txt"
                    with open(text_file, "w", encoding="utf-8") as f:
                        f.write(f"Emergency data dump - {datetime.now()}\n")
                        f.write("=" * 50 + "\n")
                        for vn_title, dates in self._data.items():
                            f.write(f"\nVN: {vn_title}\n")
                            for date, seconds in dates.items():
                                f.write(f"  {date}: {seconds} seconds\n")
                    print(f"Final emergency save successful: {text_file}")
                except Exception as e3:
                    print(f"Final emergency save also failed: {e3}")
    
    def reset_today(self, vn_title: str) -> None:
        """Reset today's time for a VN."""
        if not vn_title:
            return
        
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            self._data.setdefault(vn_title, {})
            self._data[vn_title][today] = 0
            self._pending_changes = True
    
    def has_pending_changes(self) -> bool:
        """Check if there are unsaved changes."""
        return self._pending_changes
    
    def export_vn_data(self, vn_title: str, export_dir: str) -> str:
        """Export VN data to CSV file."""
        if not vn_title:
            raise ValueError("VN title is required")
        
        filename = f"{urllib.parse.quote(vn_title, safe='')}_timelog.csv"
        export_file = os.path.join(export_dir, filename)
        
        with open(export_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Seconds"])
            for date, seconds in self._data.get(vn_title, {}).items():
                writer.writerow([date, seconds])
        
        return export_file
    
    def export_data(self, filename: str) -> None:
        """Export all time tracking data to a JSON file."""
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise Exception(f"Failed to export data: {e}")
    
    @property
    def data(self) -> Dict[str, Dict[str, int]]:
        """Get all time data."""
        return self._data.copy()
