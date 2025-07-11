# Visual Novel Time Tracker

A simple Python app to track time spent playing visual novels on Windows. It includes AFK detection, VNDB cover images, and daily reading goals. Aimed at Japanese learners who wish to maximize their time spent on immersion.

## Installation
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/drinosaret/VNTimeTtracker.git
   cd VNTimeTtracker
   ```

2. **Install Dependencies**:
   Make sure you have Python 3.8 or higher. Then run:
   ```bash
   pip install -r requirements.txt
   ```
   This installs `ttkthemes`, `psutil`, `pywin32`, `requests`, and `Pillow`.

3. **Run the App**:
   ```bash
   python vn_tracker.py
   ```

**Note**: Works only on Windows because of `pywin32`.

## Usage
1. **Select a Visual Novel**:
   - Search for a visual novel using the search bar.
   - Pick one from the dropdown.
2. **Choose a Process**:
   - Select the game's executable from the process list.
   - Click "ゲームとプロセスを選択" to start tracking.
3. **Set Goals**:
   - Enter a daily reading goal (e.g., 90 minutes).
   - Set an AFK timeout (e.g., 60 seconds).
4. **Track Time**:
   - The overlay shows your reading time (Green: active, Yellow: AFK, Red: inactive).
   - See today’s time, weekly/monthly stats, and progress in the main window.
5. **Export or Reset**:
   - Click "データエクスポート" to save time logs as a CSV.
   - Click "今日のリセット" to clear today’s time.

## Notes
- **Windows Only**: This app uses `pywin32`, so it won’t work on Mac or Linux.
