"""Internationalization support for VN Tracker."""

from typing import Dict, Any
import json
import os


class I18nManager:
    """Manages application internationalization."""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.current_language = config_manager.get("language", "en")  # Default to English
        self.translations: Dict[str, Dict[str, str]] = {}
        self._load_translations()
    
    def _load_translations(self) -> None:
        """Load translation dictionaries."""
        self.translations = {
            "ja": {
                # Main window
                "app_title": "Visual Novel Time Tracker",
                "vn_search": "VN検索",
                "search": "検索",
                "select_game_process": "ゲームとプロセスを選択",
                "tracking": "追跡中",
                "not_selected": "未選択",
                "cover_image": "カバー画像",
                "select_vn": "VNを選択",
                "select_process": "プロセスを選択",
                "time_tracking": "時間追跡",
                
                # Time tracking
                "today_reading_time": "今日の読書時間",
                "statistics": "統計",
                "weekly": "週間",
                "monthly": "月間",
                "total": "合計",
                "minutes": "分",
                
                # Settings
                "goal_settings": "目標設定",
                "goal_time": "目標時間",
                "set_goal": "目標を設定",
                "afk_threshold": "AFK閾値",
                "seconds": "秒",
                "set_afk_threshold": "AFK閾値を設定",
                
                # Overlay settings
                "overlay_settings": "オーバーレイ設定",
                "overlay_transparency": "オーバーレイ透明度",
                "show_overlay": "オーバーレイを表示",
                "show_overlay_percentage": "目標達成率を表示",
                
                # Language settings
                "language_settings": "言語設定",
                "language": "言語",
                "japanese": "日本語",
                "english": "English",
                "set_language": "言語を設定",
                
                # Buttons
                "reset_today": "今日のリセット",
                "export_data": "データエクスポート",
                
                # Messages
                "reset_failed": "リセット失敗",
                "select_vn_first": "ビジュアルノベルを選択してください。",
                "export_failed": "エクスポート失敗",
                "export_success": "成功",
                "data_exported_to": "データが {file} にエクスポートされました。",
                "error": "エラー",
                "export_error": "エクスポート失敗: {error}",
                "invalid_selection": "無効な選択",
                "invalid_minutes": "有効な分数を入力してください。",
                "invalid_seconds": "有効な秒数を入力してください。",
                "goal_positive": "目標時間は正の数でなければなりません。",
                "afk_non_negative": "AFK閾値は0以上でなければなりません。",
                "restart_required": "言語変更を適用するにはアプリケーションを再起動してください。",
                "restart_title": "再起動が必要",
                
                # System tray
                "show_hide_window": "ウィンドウを表示/非表示",
                "exit": "終了",
                "minimize_to_tray": "トレイに最小化"
            },
            "en": {
                # Main window
                "app_title": "Visual Novel Time Tracker",
                "vn_search": "VN Search",
                "search": "Search",
                "select_game_process": "Select Game and Process",
                "tracking": "Tracking",
                "not_selected": "Not Selected",
                "cover_image": "Cover Image",
                "select_vn": "Select VN",
                "select_process": "Select Process",
                "time_tracking": "Time Tracking",
                
                # Time tracking
                "today_reading_time": "Today's Reading Time",
                "statistics": "Statistics",
                "weekly": "Weekly",
                "monthly": "Monthly",
                "total": "Total",
                "minutes": "min",
                
                # Settings
                "goal_settings": "Goal Settings",
                "goal_time": "Goal Time",
                "set_goal": "Set Goal",
                "afk_threshold": "AFK Threshold",
                "seconds": "sec",
                "set_afk_threshold": "Set AFK Threshold",
                
                # Overlay settings
                "overlay_settings": "Overlay Settings",
                "overlay_transparency": "Overlay Transparency",
                "show_overlay": "Show Overlay",
                "show_overlay_percentage": "Show Goal Percentage",
                
                # Language settings
                "language_settings": "Language Settings",
                "language": "Language",
                "japanese": "日本語",
                "english": "English",
                "set_language": "Set Language",
                
                # Buttons
                "reset_today": "Reset Today",
                "export_data": "Export Data",
                
                # Messages
                "reset_failed": "Reset Failed",
                "select_vn_first": "Please select a visual novel first.",
                "export_failed": "Export Failed",
                "export_success": "Success",
                "data_exported_to": "Data exported to {file}.",
                "error": "Error",
                "export_error": "Export failed: {error}",
                "invalid_selection": "Invalid Selection",
                "invalid_minutes": "Please enter a valid number of minutes.",
                "invalid_seconds": "Please enter a valid number of seconds.",
                "goal_positive": "Goal time must be a positive number.",
                "afk_non_negative": "AFK threshold must be 0 or greater.",
                "restart_required": "Please restart the application to apply the language change.",
                "restart_title": "Restart Required",
                
                # System tray
                "show_hide_window": "Show/Hide Window",
                "exit": "Exit",
                "minimize_to_tray": "Minimize to Tray"
            }
        }
    
    def get_language(self) -> str:
        """Get current language."""
        return self.current_language
    
    def set_language(self, language: str) -> None:
        """Set current language."""
        if language in self.translations:
            self.current_language = language
            self.config_manager.set("language", language)
            self.config_manager.save()
    
    def get_available_languages(self) -> Dict[str, str]:
        """Get available languages with their display names."""
        return {
            "ja": self.t("japanese"),
            "en": self.t("english")
        }
    
    def t(self, key: str, **kwargs) -> str:
        """Translate a key to current language with optional formatting."""
        text = self.translations.get(self.current_language, {}).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text
    
    def format_time_with_label(self, hours: int, minutes: int, seconds: int) -> str:
        """Format time with localized label."""
        time_str = f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{self.t('today_reading_time')}: {time_str}"
    
    def format_stats(self, weekly_minutes: int, monthly_minutes: int) -> tuple[str, str]:
        """Format statistics with localized labels."""
        weekly = f"{self.t('weekly')}: {weekly_minutes}{self.t('minutes')}"
        monthly = f"{self.t('monthly')}: {monthly_minutes}{self.t('minutes')}"
        return weekly, monthly
