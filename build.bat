@echo off
echo Building VN Tracker executable...
echo.

REM Check for debug flag
set DEBUG_MODE=0
if "%1"=="debug" set DEBUG_MODE=1

if %DEBUG_MODE%==1 (
    echo Building in DEBUG mode...
    set VN_TRACKER_DEBUG=1
) else (
    echo Building in RELEASE mode...
    set VN_TRACKER_DEBUG=0
)

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
)

REM Clean previous builds
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

REM Build the executable
echo Building executable with PyInstaller...
pyinstaller vn_tracker.spec

if exist "dist\vn_tracker.exe" (
    echo.
    echo Build successful! Executable created at: dist\vn_tracker.exe
    if %DEBUG_MODE%==1 (
        echo DEBUG BUILD - Console window will be visible
    )
    echo File size: 
    dir "dist\vn_tracker.exe" | findstr "vn_tracker.exe"
    echo.
    echo You can now run: dist\vn_tracker.exe
) else (
    echo.
    echo Build failed! Check the output above for errors.
    exit /b 1
)

pause