@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo Instal Python 3.12 dari python.org dengan Python Launcher, lalu klik lagi.
 pause
 exit /b 1
)
if not exist ".venv-desktop\Scripts\python.exe" (
 py -3 -m venv .venv-desktop
 if errorlevel 1 goto failed
)
.venv-desktop\Scripts\python.exe -m pip install -r requirements-desktop.txt
if errorlevel 1 goto failed
.venv-desktop\Scripts\python.exe desktop.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Aplikasi gagal dijalankan. Periksa pesan di atas.
pause
exit /b 1
