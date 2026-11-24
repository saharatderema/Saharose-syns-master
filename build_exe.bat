@echo off
cd /d "%~dp0"
echo ============================================
echo  Building SAHARose Sync Master (.exe)
echo ============================================
echo.
if not exist ".venv" (
    echo Virtual Environment ยังไม่มี กำลังสร้าง...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
echo.
echo กำลังรัน PyInstaller...
pyinstaller --onefile --windowed --add-data "sql;sql" --add-data "config.json;." --add-data "setup_district_db.sql;." --add-data "setup_hostatom_db.sql;." --name "SAHARose_Sync_Master" main.py
echo.
echo ============================================
echo  สร้างไฟล์ .exe เรียบร้อยแล้ว
echo ไฟล์อยู่ที่โฟลเดอร์ dist\SAHARose_Sync_Master.exe
echo ============================================
pause