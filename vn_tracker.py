import tkinter as tk
from tkinter import ttk, messagebox
from ttkthemes import ThemedTk
import psutil
import win32gui
import win32process
import win32api
import win32con
import time
import threading
import json
import os
import csv
import requests
from PIL import Image, ImageTk
from io import BytesIO
from datetime import datetime, timedelta
import urllib.parse
import queue

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "timelog.json")
IMAGE_CACHE_DIR = os.path.join(os.path.dirname(__file__), "image_cache")
DEFAULT_GOAL_MINUTES = 90
DEFAULT_AFK_THRESHOLD = 60  # デフォルトAFK閾値（秒）
VNDB_API_URL = "https://api.vndb.org/kana/vn"

def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def get_last_input_time():
    """最後のユーザー入力からの経過時間（秒）を返す"""
    try:
        lii = win32api.GetLastInputInfo()
        current_time = win32api.GetTickCount()
        elapsed_ms = current_time - lii
        return elapsed_ms / 1000.0  # ミリ秒を秒に変換
    except Exception as e:
        print(f"入力時間取得エラー: {e}")
        return 0

class OverlayWindow(tk.Toplevel):
    def __init__(self, root):
        super().__init__(root)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.8)
        self.geometry("180x45+100+100")
        self.configure(bg="#1e1e1e")

        self.label = tk.Label(self, text="00:00:00", font=("Segoe UI", 14, "bold"),
                              fg="#00ff00", bg="#1e1e1e")
        self.label.pack(expand=True, fill="both")

        self.offset_x = 0
        self.offset_y = 0
        self.bind("<Button-1>", self.start_drag)
        self.bind("<B1-Motion>", self.do_drag)
        self.bind("<Configure>", self.on_resize)

    def start_drag(self, event):
        self.offset_x = event.x
        self.offset_y = event.y

    def do_drag(self, event):
        x = self.winfo_pointerx() - self.offset_x
        y = self.winfo_pointery() - self.offset_y
        self.geometry(f"+{x}+{y}")

    def on_resize(self, event):
        width = event.width
        font_size = max(14, int(width / 12))
        self.label.config(font=("Segoe UI", font_size, "bold"))
        self.geometry(f"{width}x45")

    def update_time(self, seconds, state="GREEN"):
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = seconds % 60
        self.label.config(text=f"{hrs:02}:{mins:02}:{secs:02}")
        if state == "GREEN":
            self.label.config(fg="#00ff00")
        elif state == "YELLOW":
            self.label.config(fg="#ffff00")
        else:  # RED
            self.label.config(fg="#ff5555")

    def set_alpha(self, alpha):
        self.attributes("-alpha", alpha)

class VNTimeTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Visual Novel Time Tracker")
        self.root.geometry("600x525")
        self.root.minsize(500, 400)
        self.root.resizable(True, True)
        self.selected_process = None
        self.selected_vn_title = None
        self.last_start = None
        self.overlay = OverlayWindow(root)
        self.time_data = self.load_time_data()
        self.config_data = self.load_config()
        self.goal_minutes = self.config_data.get("goal_minutes", DEFAULT_GOAL_MINUTES)
        self.goal_seconds = self.goal_minutes * 60
        self.afk_threshold = self.config_data.get("afk_threshold", DEFAULT_AFK_THRESHOLD)
        self.overlay_alpha = self.config_data.get("overlay_alpha", 0.8)
        self.process_to_vn = self.config_data.get("process_to_vn", {})
        self.vn_data = {}
        self.image_cache = {}
        self.update_queue = queue.Queue()
        self.running = True
        os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

        self.style = ttk.Style()
        self.style.configure("TButton", font=("Segoe UI", 9))
        self.style.configure("TLabel", font=("Segoe UI", 9))
        self.style.configure("TCombobox", font=("Segoe UI", 9))

        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.pack(fill="both", expand=True)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(0, weight=1)

        # 左側：ゲーム選択
        self.selection_frame = ttk.Frame(self.main_frame)
        self.selection_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.selection_frame.columnconfigure(0, weight=1)

        self.search_frame = ttk.LabelFrame(self.selection_frame, text="VN検索", padding=5)
        self.search_frame.grid(row=0, column=0, sticky="ew", pady=5)
        self.search_frame.columnconfigure(0, weight=1)

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.search_frame, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=0, padx=3, sticky="ew")
        self.search_entry.bind("<Return>", self.search_vn)

        self.search_button = ttk.Button(self.search_frame, text="検索", command=self.search_vn)
        self.search_button.grid(row=0, column=1, padx=3)

        self.vn_list = []
        self.vn_var = tk.StringVar(value=self.config_data.get("last_vn", ""))
        self.dropdown = ttk.Combobox(self.selection_frame, textvariable=self.vn_var,
                                     values=self.vn_list, state="readonly")
        self.dropdown.grid(row=1, column=0, pady=5, sticky="ew")

        self.process_list = self.get_process_list()
        self.process_var = tk.StringVar(value=self.process_to_vn.get(self.vn_var.get(), ""))
        self.process_dropdown = ttk.Combobox(self.selection_frame, textvariable=self.process_var,
                                            values=self.process_list, state="readonly")
        self.process_dropdown.grid(row=2, column=0, pady=5, sticky="ew")

        self.set_button = ttk.Button(self.selection_frame, text="ゲームとプロセスを選択", command=self.set_target)
        self.set_button.grid(row=3, column=0, pady=5, sticky="ew")

        self.status_label = ttk.Label(self.selection_frame, text=f"追跡中: {self.selected_vn_title or '未選択'}")
        self.status_label.grid(row=4, column=0, pady=5, sticky="ew")

        self.cover_frame = ttk.Frame(self.selection_frame)
        self.cover_frame.grid(row=5, column=0, pady=5, sticky="ew")
        self.cover_label = ttk.Label(self.cover_frame, text="カバー画像:")
        self.cover_label.pack(side="left")
        self.cover_canvas = tk.Canvas(self.cover_frame, width=100, height=140, bg="#1e1e1e", highlightthickness=0)
        self.cover_canvas.pack(side="left", padx=5)

        # 右側：時間追跡
        self.tracking_frame = ttk.Frame(self.main_frame)
        self.tracking_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.tracking_frame.columnconfigure(0, weight=1)

        self.time_label = ttk.Label(self.tracking_frame, text="今日の読書時間: 00:00:00", font=("Segoe UI", 11, "bold"))
        self.time_label.grid(row=0, column=0, pady=5, sticky="ew")

        self.progress = ttk.Progressbar(self.tracking_frame, length=200, mode='determinate', maximum=self.goal_seconds)
        self.progress.grid(row=1, column=0, pady=5, sticky="ew")

        self.stats_frame = ttk.LabelFrame(self.tracking_frame, text="統計", padding=5)
        self.stats_frame.grid(row=2, column=0, pady=5, sticky="ew")
        self.stats_frame.columnconfigure(0, weight=1)

        self.week_label = ttk.Label(self.stats_frame, text="週間: 0分")
        self.week_label.grid(row=0, column=0, sticky="ew")
        self.month_label = ttk.Label(self.stats_frame, text="月間: 0分")
        self.month_label.grid(row=1, column=0, sticky="ew")

        self.goal_frame = ttk.LabelFrame(self.tracking_frame, text="目標設定", padding=5)
        self.goal_frame.grid(row=3, column=0, pady=5, sticky="ew")
        self.goal_frame.columnconfigure(0, weight=1)

        self.goal_label = ttk.Label(self.goal_frame, text=f"目標時間: {self.goal_minutes}分")
        self.goal_label.grid(row=0, column=0, sticky="ew")
        self.goal_entry = ttk.Entry(self.goal_frame, width=10)
        self.goal_entry.insert(0, str(self.goal_minutes))
        self.goal_entry.grid(row=1, column=0, pady=5, sticky="ew")
        self.set_goal_button = ttk.Button(self.goal_frame, text="目標を設定", command=self.set_goal)
        self.set_goal_button.grid(row=2, column=0, pady=5, sticky="ew")

        self.afk_label = ttk.Label(self.goal_frame, text=f"AFK閾値: {self.afk_threshold}秒")
        self.afk_label.grid(row=3, column=0, sticky="ew")
        self.afk_entry = ttk.Entry(self.goal_frame, width=10)
        self.afk_entry.insert(0, str(self.afk_threshold))
        self.afk_entry.grid(row=4, column=0, pady=5, sticky="ew")
        self.set_afk_button = ttk.Button(self.goal_frame, text="AFK閾値を設定", command=self.set_afk_threshold)
        self.set_afk_button.grid(row=5, column=0, pady=5, sticky="ew")

        self.alpha_frame = ttk.LabelFrame(self.tracking_frame, text="オーバーレイ設定", padding=5)
        self.alpha_frame.grid(row=4, column=0, pady=5, sticky="ew")
        self.alpha_frame.columnconfigure(0, weight=1)

        self.alpha_label = ttk.Label(self.alpha_frame, text=f"オーバーレイ透明度: {int(self.overlay_alpha * 100)}%")
        self.alpha_label.grid(row=0, column=0, sticky="ew")
        self.alpha_scale = ttk.Scale(self.alpha_frame, from_=0.1, to=1.0, orient="horizontal",
                                    command=self.update_alpha, value=self.overlay_alpha)
        self.alpha_scale.grid(row=1, column=0, pady=5, sticky="ew")

        self.button_frame = ttk.Frame(self.tracking_frame)
        self.button_frame.grid(row=5, column=0, pady=10, sticky="ew")
        self.button_frame.columnconfigure(0, weight=1)
        self.button_frame.columnconfigure(1, weight=1)

        self.reset_button = ttk.Button(self.button_frame, text="今日のリセット", command=self.reset_today)
        self.reset_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.export_button = ttk.Button(self.button_frame, text="データエクスポート", command=self.export_data)
        self.export_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # スレッドの初期化
        self.track_thread = threading.Thread(target=self.track_loop, daemon=False)
        self.autosave_thread = threading.Thread(target=self.auto_save_loop, daemon=False)
        self.process_refresh_thread = threading.Thread(target=self.refresh_process_list, daemon=False)
        self.track_thread.start()
        self.autosave_thread.start()
        self.process_refresh_thread.start()

        # 定期的なキュー処理
        self.process_queue()

        # 起動時に前回のVNデータをロード
        last_vn = self.config_data.get("last_vn", "")
        if last_vn:
            self.vn_list = self.get_vn_list(last_vn)
            self.dropdown.configure(values=self.vn_list)
            if last_vn in self.vn_list:
                self.vn_var.set(last_vn)
                self.set_target()

    def process_queue(self):
        if not self.running:
            return
        try:
            while not self.update_queue.empty():
                func = self.update_queue.get_nowait()
                try:
                    func()
                except Exception as e:
                    print(f"キュー内関数実行エラー: {e}")
        except queue.Empty:
            pass
        except Exception as e:
            print(f"キュー処理エラー: {e}")
        self.root.after(10, self.process_queue)

    def get_vn_list(self, query=""):
        try:
            payload = {
                "fields": "title, image.url",
                "sort": "title",
                "results": 50
            }
            if query:
                payload["filters"] = ["search", "=", query]
            response = requests.post(VNDB_API_URL, json=payload,
                                    headers={"Content-Type": "application/json"}, timeout=5)
            response.raise_for_status()
            data = response.json()
            self.vn_data = {item["title"]: item for item in data.get("results", [])}
            return sorted(self.vn_data.keys())
        except Exception as e:
            print(f"VNDB APIエラー: {e}, クエリ: {query}")
            return []

    def search_vn(self, event=None):
        query = self.search_var.get().strip()
        self.vn_list = self.get_vn_list(query)
        self.dropdown.configure(values=self.vn_list)
        if self.vn_list:
            self.vn_var.set(self.vn_list[0])
        else:
            self.vn_var.set("")

    def get_process_list(self):
        names = set()
        for proc in psutil.process_iter(['name']):
            try:
                names.add(proc.info['name'])
            except:
                continue
        return sorted(list(names))

    def set_target(self):
        self.selected_vn_title = self.vn_var.get()
        self.selected_process = self.process_var.get().lower()
        if self.selected_vn_title and self.selected_process:
            self.status_label.config(text=f"追跡中: {self.selected_vn_title} ({self.selected_process})")
            self.process_to_vn[self.selected_vn_title] = self.selected_process
            self.config_data["last_vn"] = self.selected_vn_title
            self.config_data["process_to_vn"] = self.process_to_vn
            self.save_config()
            self.load_cover_image()
        else:
            self.status_label.config(text="無効な選択")
        self.update_queue.put(self.update_display)

    def load_cover_image(self):
        if not self.selected_vn_title or self.selected_vn_title not in self.vn_data:
            self.cover_canvas.delete("all")
            return
        image_url = self.vn_data[self.selected_vn_title].get("image", {}).get("url")
        if not image_url:
            self.cover_canvas.delete("all")
            return

        image_path = os.path.join(IMAGE_CACHE_DIR, f"{urllib.parse.quote(self.selected_vn_title, safe='')}.jpg")
        if image_path in self.image_cache:
            self.display_image(self.image_cache[image_path])
            return

        try:
            response = requests.get(image_url, timeout=5)
            response.raise_for_status()
            img_data = response.content
            img = Image.open(BytesIO(img_data))
            img = img.resize((100, 140), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.image_cache[image_path] = photo
            with open(image_path, "wb") as f:
                f.write(img_data)
            self.display_image(photo)
        except Exception as e:
            print(f"カバー画像の取得エラー: {e}")
            self.cover_canvas.delete("all")

    def display_image(self, photo):
        self.cover_canvas.delete("all")
        self.cover_canvas.create_image(50, 70, image=photo)
        self.cover_canvas.image = photo

    def set_goal(self):
        try:
            minutes = int(self.goal_entry.get())
            if minutes <= 0:
                raise ValueError("目標時間は正の数でなければなりません。")
            self.goal_minutes = minutes
            self.goal_seconds = minutes * 60
            self.goal_label.config(text=f"目標時間: {self.goal_minutes}分")
            self.progress.config(maximum=self.goal_seconds)
            self.config_data["goal_minutes"] = minutes
            self.save_config()
            self.update_queue.put(self.update_display)
        except ValueError as e:
            messagebox.showerror("エラー", str(e) or "有効な分数を入力してください。")

    def set_afk_threshold(self):
        try:
            seconds = int(self.afk_entry.get())
            if seconds < 0:
                raise ValueError("AFK閾値は0以上でなければなりません。")
            self.afk_threshold = seconds
            self.afk_label.config(text=f"AFK閾値: {self.afk_threshold}秒")
            self.config_data["afk_threshold"] = seconds
            self.save_config()
        except ValueError as e:
            messagebox.showerror("エラー", str(e) or "有効な秒数を入力してください。")

    def update_alpha(self, value):
        self.overlay_alpha = float(value)
        self.overlay.set_alpha(self.overlay_alpha)
        self.alpha_label.config(text=f"オーバーレイ透明度: {int(self.overlay_alpha * 100)}%")
        self.config_data["overlay_alpha"] = self.overlay_alpha
        self.save_config()

    def reset_today(self):
        if not self.selected_vn_title:
            messagebox.showinfo("リセット失敗", "ビジュアルノベルを選択してください。")
            return
        today = get_today()
        self.time_data.setdefault(self.selected_vn_title, {})
        self.time_data[self.selected_vn_title][today] = 0
        self.save_time_data()
        self.update_queue.put(self.update_display)

    def get_active_process(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            return proc.name().lower()
        except Exception as e:
            print(f"アクティブプロセス取得エラー: {e}")
            return None

    def track_loop(self):
        while self.running:
            try:
                active_name = self.get_active_process()
                is_process_active = (active_name == self.selected_process)
                idle_time = get_last_input_time()

                # 状態判定
                if not is_process_active:
                    state = "RED"
                    if self.last_start:
                        elapsed = int(time.time() - self.last_start)
                        self.last_start = None
                        self.add_time(elapsed)
                elif idle_time > self.afk_threshold:
                    state = "YELLOW"
                    if self.last_start:
                        elapsed = int(time.time() - self.last_start)
                        self.last_start = None
                        self.add_time(elapsed)
                else:
                    state = "GREEN"
                    if self.last_start is None:
                        self.last_start = time.time()
                    self.update_queue.put(self.overlay.lift)

                secs = self.get_today_seconds()
                if self.last_start:
                    secs += int(time.time() - self.last_start)
                self.update_queue.put(lambda s=secs, st=state: self.overlay.update_time(s, st))
                self.update_queue.put(self.update_display)
                time.sleep(1)
            except Exception as e:
                print(f"トラックエラー: {e}")
                continue

    def auto_save_loop(self):
        while self.running:
            try:
                self.save_time_data()
                time.sleep(10)
            except Exception as e:
                print(f"自動保存エラー: {e}")
                continue

    def refresh_process_list(self):
        while self.running:
            try:
                new_list = self.get_process_list()
                if new_list != self.process_list:
                    self.process_list = new_list
                    self.update_queue.put(lambda: self.process_dropdown.configure(values=self.process_list))
                time.sleep(60)
            except Exception as e:
                print(f"プロセスリストエラー: {e}")
                continue

    def add_time(self, seconds):
        try:
            today = get_today()
            self.time_data.setdefault(self.selected_vn_title, {})
            self.time_data[self.selected_vn_title][today] = self.time_data[self.selected_vn_title].get(today, 0) + seconds
            self.save_time_data()
        except Exception as e:
            print(f"時間追加エラー: {e}")

    def get_today_seconds(self):
        try:
            today = get_today()
            return self.time_data.get(self.selected_vn_title, {}).get(today, 0)
        except Exception as e:
            print(f"今日の秒数取得エラー: {e}")
            return 0

    def get_weekly_seconds(self):
        try:
            if not self.selected_vn_title:
                return 0
            total = 0
            today = datetime.now()
            for i in range(7):
                date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                total += self.time_data.get(self.selected_vn_title, {}).get(date, 0)
            return total
        except Exception as e:
            print(f"週間秒数取得エラー: {e}")
            return 0

    def get_monthly_seconds(self):
        try:
            if not self.selected_vn_title:
                return 0
            total = 0
            today = datetime.now()
            for i in range(30):
                date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                total += self.time_data.get(self.selected_vn_title, {}).get(date, 0)
            return total
        except Exception as e:
            print(f"月間秒数取得エラー: {e}")
            return 0

    def update_display(self):
        try:
            if not self.selected_vn_title:
                self.time_label.config(text="今日の読書時間: 00:00:00")
                self.progress["value"] = 0
                self.week_label.config(text="週間: 0分")
                self.month_label.config(text="月間: 0分")
                self.status_label.config(text="追跡中: 未選択")
                return

            self.status_label.config(text=f"追跡中: {self.selected_vn_title} ({self.selected_process})")
            secs = self.get_today_seconds()
            if self.last_start:
                secs += int(time.time() - self.last_start)

            hrs = secs // 3600
            mins = (secs % 3600) // 60
            s = secs % 60
            self.time_label.config(text=f"今日の読書時間: {hrs:02}:{mins:02}:{s:02}")
            self.progress["value"] = secs

            week_mins = self.get_weekly_seconds() // 60
            month_mins = self.get_monthly_seconds() // 60
            self.week_label.config(text=f"週間: {week_mins}分")
            self.month_label.config(text=f"月間: {month_mins}分")
        except Exception as e:
            print(f"ディスプレイ更新エラー: {e}")

    def export_data(self):
        try:
            if not self.selected_vn_title:
                messagebox.showinfo("エクスポート失敗", "ビジュアルノベルを選択してください。")
                return
            export_file = os.path.join(os.path.dirname(__file__), f"{urllib.parse.quote(self.selected_vn_title, safe='')}_timelog.csv")
            with open(export_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Seconds"])
                for date, seconds in self.time_data.get(self.selected_vn_title, {}).items():
                    writer.writerow([date, seconds])
            messagebox.showinfo("成功", f"データが {export_file} にエクスポートされました。")
        except Exception as e:
            messagebox.showerror("エラー", f"エクスポート失敗: {str(e)}")

    def load_time_data(self):
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"時間データロードエラー: {e}")
            return {}

    def save_time_data(self):
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.time_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"時間データ保存エラー: {e}")

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"設定ロードエラー: {e}")
            return {}

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"設定保存エラー: {e}")

    def on_close(self):
        if not self.running:
            return
        try:
            if self.selected_vn_title and self.last_start:
                elapsed = int(time.time() - self.last_start)
                self.add_time(elapsed)
            self.running = False

            # スレッドの終了を待つ
            for thread in [self.track_thread, self.autosave_thread, self.process_refresh_thread]:
                if thread.is_alive():
                    thread.join(timeout=1.0)

            # ウィンドウがまだ存在する場合のみ破棄
            if self.overlay.winfo_exists():
                self.overlay.destroy()
            if self.root.winfo_exists():
                self.root.destroy()
        except Exception as e:
            print(f"クローズエラー: {e}")

if __name__ == "__main__":
    root = ThemedTk(theme="arc")
    app = VNTimeTracker(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()