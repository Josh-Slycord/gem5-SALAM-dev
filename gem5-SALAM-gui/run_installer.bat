@echo off
REM gem5-SALAM Installer Launcher
REM This script launches the installer GUI

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install Python 3.8 or later.
    pause
    exit /b 1
)

REM Check if PySide6 is installed
python -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo PySide6 not found. Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

REM Run the installer
python installer.py
