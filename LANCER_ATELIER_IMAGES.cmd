@echo off
setlocal
chcp 65001 >nul
where py >nul 2>&1
if errorlevel 1 (
    echo Python introuvable. Installe Python 3.10 ou plus recent.
    pause
    exit /b 1
)
py -3 "%~dp0atelier.py"
if errorlevel 1 pause
