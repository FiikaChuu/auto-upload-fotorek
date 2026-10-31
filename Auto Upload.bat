@echo off
setlocal
cd /d "%~dp0"
title Auto Upload
where py >nul 2>nul
if errorlevel 1 (
 echo Instal Python 3.12 untuk Windows beserta Python Launcher dari https://python.org
 pause
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
 py -3 -m venv .venv
 if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import sys; assert sys.version_info >= (3,10); import googleapiclient, google_auth_oauthlib" >nul 2>nul
if errorlevel 1 (
 .venv\Scripts\python.exe -m pip install -r requirements.txt
 if errorlevel 1 goto failed
)
.venv\Scripts\python.exe auto_upload.py %*
if errorlevel 1 goto failed
pause
exit /b 0
:failed
 echo Auto Upload belum berhasil. Baca pesan di atas.
 pause
 exit /b 1
