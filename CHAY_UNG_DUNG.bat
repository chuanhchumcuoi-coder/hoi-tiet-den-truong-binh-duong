@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ================================================================
echo   BAN DO THOI TIET DEN TRUONG BINH DUONG - V7.3 NHANH + NGUON DU PHONG
echo ================================================================
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo [LOI] Chua tim thay Python tren may.
    echo Hay cai Python 3.10 tro len, sau do chay lai tep nay.
    echo Khi cai Python, nho chon Add Python to PATH.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import flask" >nul 2>nul
if errorlevel 1 (
    echo Dang cai Flask lan dau...
    %PYTHON_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [LOI] Khong cai duoc Flask. Hay kiem tra ket noi Internet.
        pause
        exit /b 1
    )
)

echo Dang khoi dong ung dung...
%PYTHON_CMD% app.py

if errorlevel 1 (
    echo.
    echo [LOI] Ung dung da dung do gap loi. Xem thong bao phia tren.
    pause
)
endlocal
