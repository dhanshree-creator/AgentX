@echo off
setlocal enabledelayedexpansion

title AgentX - Installation & Setup
color 0F

echo ======================================================================
echo                     AgentX Web Studio Setup
echo ======================================================================
echo.

:: 1. Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    color 0C
    echo [ERROR] Python was not found in your PATH!
    echo Please install Python 3.11 or newer from https://www.python.org/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [*] Found %PYTHON_VERSION%
echo.

:: 2. Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo [*] Creating virtual environment in .venv...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        color 0C
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created successfully.
) else (
    echo [OK] Existing virtual environment found in .venv.
)
echo.

:: 3. Upgrade pip and install requirements
echo [*] Installing and upgrading dependencies...
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    color 0C
    echo.
    echo [ERROR] Failed to install dependencies. Check your network or pip logs.
    pause
    exit /b 1
)
echo [OK] All dependencies installed successfully.
echo.

:: 4. Check .env configuration file
if not exist ".env" (
    if exist ".env.example" (
        echo [*] .env not found. Creating .env from .env.example...
        copy .env.example .env >nul
        echo [!] Created .env file. Please edit it with your API endpoint and key.
    ) else (
        echo [!] Warning: Neither .env nor .env.example was found.
    )
) else (
    echo [OK] Configuration file .env is present.
)
echo.

echo ======================================================================
echo                       Installation Complete!
echo ======================================================================
echo.
echo To start the modern web studio, run:
echo    run.bat
echo.
echo (Or execute: python web_server.py --open)
echo.
pause
