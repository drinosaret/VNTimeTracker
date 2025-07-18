# Visual Novel Time Tracker

A PyQt5 application for tracking time spent playing visual novels with VNDB integration and AFK detection.

## Quick Start

1. **Clone and setup**:

   ```bash
   git clone https://github.com/drinosaret/VNTimeTracker.git
   cd VNTimeTracker
   pip install -r requirements.txt
   ```

2. **Run the application**:

   ```bash
   python run.py
   ```

## Requirements

- Python 3.8+
- Windows OS
- Dependencies listed in `requirements.txt`

## Features

- Process monitoring and time tracking
- VNDB integration for cover images
- Floating overlay with real-time status
- AFK detection and goal setting
- Data export and statistics

## Building Executable

To create a standalone executable:

```bash
pip install pyinstaller
pyinstaller VN-Tracker.spec
```

Or use this batch file on Windows:

```bash
build.bat
```
