# -*- coding: utf-8 -*-
"""PyInstaller spec file for SAHARose Sync Master v1.0.0"""

import sys
import os

# Add the project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[os.path.dirname(os.path.abspath(__file__))],
    binaries=[],
    datas=[
        ('config.example.json', '.'),
        ('setup_district_db.sql', '.'),
        ('setup_hostatom_db.sql', '.'),
        ('README.md', '.'),
    ],
    hiddenimports=[
        'mysql.connector',
        'mysql.connector.locales.eng.client_error',
        'mysql.connector.locales.eng.server_error',
        'schedule',
        'customtkinter',
        'ctk_widgets',
        'ui_theme',
        'ddl_generator',
        'notifier',
        'sync_engine',
        'district_sync_ui',
        'app_paths',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'json',
        'logging',
        'threading',
        'queue',
        'subprocess',
        'winreg',
        'socket',
        'hashlib',
        'uuid',
        'requests',
        'concurrent.futures',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SAHARose_Sync_Master_v1.0.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # --windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    version='1.0.0',
    company_name='SAHARose',
    product_name='SAHARose Sync Master',
    file_description='SAHARose Sync Master - ระบบลิงค์ข้อมูลอัตโนมัติ',
    copyright='Copyright (c) 2026 SAHARose',
)

# For onefile mode, we need to not use COLLECT
# The EXE will be created at dist/SAHARose_Sync_Master_v1.0.0.exe

# Use EXE directly (onefile mode) - no COLLECT needed
# The EXE will be created at dist/SAHARose_Sync_Master_v1.0.0.exe