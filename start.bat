@echo off
cd /d "%~dp0"
set PORT=8000
echo 启动权限系统，监听 0.0.0.0:%PORT% ...
python app.py
pause
