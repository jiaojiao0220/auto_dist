@echo off
chcp 65001 >nul 2>&1
title 自动化分发系统
cd /d "%~dp0"

set PYTHON=C:\Users\Admin\.workbuddy\binaries\python\envs\auto-distribute\Scripts\python.exe

echo ============================================
echo   自动化分发系统
echo   访问地址: http://127.0.0.1:8765
echo ============================================
echo.

"%PYTHON%" main.py

pause
