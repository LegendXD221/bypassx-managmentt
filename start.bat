@echo off
REM BypassX Management - start script (Windows)
cd /d "%~dp0"

if not exist ".env" (
    echo ERROR: .env file not found. Copy .env.example to .env and fill in your values:
    echo   copy .env.example .env
    pause
    exit /b 1
)

python -c "import discord" 2>nul
if errorlevel 1 (
    echo Dependencies not installed. Installing from requirements.txt...
    pip install -r requirements.txt
)

echo Starting BypassX Management...
python main.py
pause
