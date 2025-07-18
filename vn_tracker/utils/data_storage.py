"""Data storage utilities for time tracking."""

import json
import os
import csv
import urllib.parse
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class TimeDataManager:
    """Manages time tracking data storage."""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self._data: Dict[str, Dict[str, int]] = {}
        self.load()
    
    def load(self) -> None:
        """Load time data from file."""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            else:
                self._data = {}
        except Exception as e:
            print(f"時間データロードエラー: {e}")
            self._data = {}
    
    def save(self) -> None:
        """Save time data to file."""
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"時間データ保存エラー: {e}")
    
    def add_time(self, vn_title: str, seconds: int, date: Optional[str] = None) -> None:
        """Add time for a specific VN and date."""
        if not vn_title:
            return
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            self._data.setdefault(vn_title, {})
            current_time = self._data[vn_title].get(date, 0)
            self._data[vn_title][date] = current_time + seconds
        except Exception as e:
            print(f"時間追加エラー: {e}")
    
    def get_today_seconds(self, vn_title: str) -> int:
        """Get today's seconds for a VN."""
        if not vn_title:
            return 0
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            return self._data.get(vn_title, {}).get(today, 0)
        except Exception as e:
            print(f"今日の秒数取得エラー: {e}")
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
            print(f"週間秒数取得エラー: {e}")
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
            print(f"月間秒数取得エラー: {e}")
            return 0
    
    def reset_today(self, vn_title: str) -> None:
        """Reset today's time for a VN."""
        if not vn_title:
            return
        
        today = datetime.now().strftime("%Y-%m-%d")
        self._data.setdefault(vn_title, {})
        self._data[vn_title][today] = 0
    
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
