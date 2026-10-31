@echo off
setlocal
cd /d "%~dp0"
title Fotorek Auto Upload
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js belum terpasang. Instal Node.js versi LTS dari https://nodejs.org
  echo Setelah instalasi selesai, klik file ini lagi.
  pause
  exit /b 1
)
if not exist "server.mjs" (
  echo File server.mjs tidak ditemukan. Ekstrak seluruh ZIP sebelum menjalankan aplikasi.
  pause
  exit /b 1
)
set "PORT=3000"
echo Fotorek akan terbuka otomatis di browser.
echo Biarkan jendela ini terbuka selama menggunakan aplikasi.
echo Tutup jendela ini untuk menghentikan aplikasi.
node --input-type=module -e "import net from 'node:net';import {spawn} from 'node:child_process';const probe=net.createServer();probe.once('error',()=>{console.error('Port 3000 sedang digunakan. Tutup Fotorek yang sudah berjalan atau aplikasi lain pada port tersebut.');process.exitCode=1;});probe.listen(3000,'127.0.0.1',()=>probe.close(()=>{const server=spawn(process.execPath,['server.mjs'],{stdio:'inherit'});let tries=0;const timer=setInterval(async()=>{if(++tries>30){clearInterval(timer);console.error('Aplikasi belum siap. Periksa pesan server.');return;}try{const r=await fetch('http://localhost:3000');if(r.ok){clearInterval(timer);spawn('cmd.exe',['/c','start','','http://localhost:3000'],{stdio:'ignore'});}}catch{}},500);server.on('exit',code=>{clearInterval(timer);process.exitCode=code??1;});}));"
if errorlevel 1 pause
