@echo off
REM Double-click on Windows. Needs Python 3 installed (python.org).
cd /d "%~dp0"
if not exist .venv (
    echo Setting up ^(first run only^)...
    python -m venv .venv || (echo Python 3 is required. & pause & exit /b 1)
)
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt
.venv\Scripts\python -m hearthdelve
pause
