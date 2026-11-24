@echo off
setlocal

title AgentX Web Studio
color 0F

echo ======================================================================
echo                     AgentX Modern Web Studio
echo ======================================================================
echo.

:: 1. Check if .venv exists
if not exist ".venv\Scripts\python.exe" (
    color 0C
    echo [ERROR] Virtual environment not found!
    echo Please run 'install.bat' first to set up Python dependencies.
    echo.
    pause
    exit /b 1
)

:: 2. Check if .env exists
if not exist ".env" (
    color 0E
    echo [WARNING] .env file not found!
    if exist ".env.example" (
        copy .env.example .env >nul
        echo Created .env from .env.example.
    )
    echo Please configure your AGENTX_API_KEY and AGENTX_BASE_URL in .env
    echo before running tasks.
    echo.
)

:: 3. Launch Web Server and open browser
echo [*] Starting AgentX Web Studio at http://127.0.0.1:8000 ...
echo [*] Opening your default web browser...
echo.

.\.venv\Scripts\python.exe web_server.py --open

if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] Server stopped with exit code %ERRORLEVEL%.
    pause
)
