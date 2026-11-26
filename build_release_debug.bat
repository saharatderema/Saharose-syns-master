@echo off
chcp 65001 >nul
echo ==========================================
echo  SAHARose Sync Master v1.0.0 - DEBUG Build (with Console)
echo ==========================================
echo.

REM Check if we're in the right directory
if not exist "main.py" (
    echo ERROR: main.py not found. Please run this script from the project root.
    pause
    exit /b 1
)

REM Use the virtual environment's python directly
set PYTHON_EXE=.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Installing requirements...
    %PYTHON_EXE% -m pip install --upgrade pip
    %PYTHON_EXE% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install requirements
        pause
        exit /b 1
    )
    echo Installing PyInstaller...
    %PYTHON_EXE% -m pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

echo.
echo ==========================================
echo  Building with PyInstaller (--onefile --console)
echo ==========================================
echo.

REM Clean previous builds
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
if exist "SAHARose_Sync_Master_v1.0.0.spec" del SAHARose_Sync_Master_v1.0.0.spec

REM Install Pillow for icon support
%PYTHON_EXE% -m pip install pillow
if errorlevel 1 (
    echo WARNING: Failed to install Pillow, continuing without icon support
)

REM Run PyInstaller using the venv python directly - WITH CONSOLE FOR DEBUGGING
%PYTHON_EXE% -m PyInstaller ^
    --onefile ^
    --console ^
    --name "SAHARose_Sync_Master_v1.0.0_DEBUG" ^
    --add-data "config.example.json;." ^
    --add-data "setup_district_db.sql;." ^
    --add-data "setup_hostatom_db.sql;." ^
    --add-data "README.md;." ^
    --collect-all mysql.connector ^
    --hidden-import=mysql.connector.locales.eng.client_error ^
    --hidden-import=mysql.connector.locales.eng.server_error ^
    --hidden-import=schedule ^
    --hidden-import=customtkinter ^
    --hidden-import=ctk_widgets ^
    --hidden-import=ui_theme ^
    --hidden-import=ddl_generator ^
    --hidden-import=notifier ^
    --hidden-import=sync_engine ^
    --hidden-import=district_sync_ui ^
    --hidden-import=app_paths ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.ttk ^
    --hidden-import=tkinter.filedialog ^
    --hidden-import=tkinter.messagebox ^
    --hidden-import=json ^
    --hidden-import=logging ^
    --hidden-import=threading ^
    --hidden-import=queue ^
    --hidden-import=subprocess ^
    --hidden-import=winreg ^
    --hidden-import=socket ^
    --hidden-import=hashlib ^
    --hidden-import=uuid ^
    --hidden-import=requests ^
    --hidden-import=concurrent.futures ^
    main.py

if errorlevel 1 (
    echo.
    echo ==========================================
    echo  BUILD FAILED
    echo ==========================================
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  BUILD SUCCESSFUL!
echo ==========================================
echo.
echo Executable created at: dist\SAHARose_Sync_Master_v1.0.0_DEBUG.exe
echo.

REM Verify the exe exists
if exist "dist\SAHARose_Sync_Master_v1.0.0_DEBUG.exe" (
    echo File size:
    dir dist\SAHARose_Sync_Master_v1.0.0_DEBUG.exe
) else (
    echo ERROR: Executable not found!
    pause
    exit /b 1
)

echo.
pause