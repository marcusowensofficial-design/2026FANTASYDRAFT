@echo off
title 2026 Fantasy Football PPR Draft Assistant
echo ========================================================
echo   2026 FANTASY FOOTBALL PPR DRAFT ASSISTANT WAR ROOM
echo ========================================================
echo.

:: Ensure working directory is the script location
cd /d "%~dp0"

echo [1/2] Opening browser at http://localhost:8501 ...
start "" http://localhost:8501

echo [2/2] Starting Streamlit live draft server...
echo.
python -m streamlit run app.py --server.port 8501

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application encountered an issue.
    echo Make sure dependencies are installed with: pip install -r requirements.txt
    echo.
    pause
)
