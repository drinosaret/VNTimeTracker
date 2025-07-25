# -*- mode: python ; coding: utf-8 -*-
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.abspath('.'))

# Determine if we're building for debugging
DEBUG_BUILD = os.environ.get('VN_TRACKER_DEBUG', '0') == '1'

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[
        # Explicitly include Windows DLLs that might be needed
        # PyQt5 sometimes needs these
    ],
    datas=[
        # Include any data files your app needs
        # ('path/to/data', 'destination/folder'),
    ],
    hiddenimports=[
        # Explicit imports that PyInstaller might miss
        'PyQt5.QtCore',
        'PyQt5.QtGui', 
        'PyQt5.QtWidgets',
        'win32gui',
        'win32process',
        'win32api',
        'psutil',
        'requests',
        'PIL',
        'PIL.Image',
        'PIL._imaging',
        'json',
        'threading',
        'queue',
        'faulthandler',
        'signal',
        'atexit',
        # Your modules
        'vn_tracker',
        'vn_tracker.main',
        'vn_tracker.ui',
        'vn_tracker.ui.main_window_qt',
        'vn_tracker.ui.overlay_qt',
        'vn_tracker.core',
        'vn_tracker.core.tracker',
        'vn_tracker.core.process_monitor',
        'vn_tracker.core.vndb_api',
        'vn_tracker.utils',
        'vn_tracker.utils.config',
        'vn_tracker.utils.data_storage',
        'vn_tracker.utils.system_utils',
        'vn_tracker.utils.i18n',
        'vn_tracker.utils.safe_threading',
        'vn_tracker.utils.crash_logger',
        'vn_tracker.utils.crash_monitor',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude packages that might cause conflicts
        'tkinter',
        'matplotlib',
        'numpy',  # Unless you actually use it
        'scipy',  # Unless you actually use it
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=0,
)

# Filter out problematic DLLs that might cause crashes
a.binaries = [x for x in a.binaries if not x[0].lower().startswith('api-ms-win-')]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name='vn_tracker',
    debug=DEBUG_BUILD,  # Enable debug mode if environment variable is set
    bootloader_ignore_signals=False,
    strip=False,
    upx=not DEBUG_BUILD,  # Disable UPX for debug builds
    upx_exclude=[],
    runtime_tmpdir=None,
    console=DEBUG_BUILD,  # Show console for debug builds
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    # Windows-specific options for better stability
    manifest=None,
    uac_admin=False,
    uac_uiaccess=False,
)