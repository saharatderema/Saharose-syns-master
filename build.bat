@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Building SAHARoseSyncMaster (Windows)
echo ============================================

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 goto :failed
)

echo Installing build dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Running PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onedir ^
    --windowed ^
    --collect-all customtkinter ^
    --collect-all mysql.connector ^
    --hidden-import=mysql.connector ^
    --hidden-import=mysql.connector.plugins.mysql_native_password ^
    --hidden-import=mysql.connector.plugins.caching_sha2_password ^
    --hidden-import=mysql.connector.plugins.sha256_password ^
    --add-data "%CD%\config.example.json;." ^
    --add-data "%CD%\sql;sql" ^
    --add-data "%CD%\setup_district_db.sql;." ^
    --add-data "%CD%\setup_hostatom_db.sql;." ^
    --name "SAHARoseSyncMaster" ^
    --distpath "dist" ^
    --workpath "build\pyinstaller" ^
    --specpath "build\spec" ^
    "main.py"
if errorlevel 1 goto :failed

echo.
echo Build completed:
echo   dist\SAHARoseSyncMaster\SAHARoseSyncMaster.exe
echo.
echo Next: compile installer.iss with Inno Setup 6.
pause
exit /b 0

:failed
echo.
echo Build failed. Review the error messages above.
pause
exit /b 1
