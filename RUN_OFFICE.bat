@echo off
setlocal
cd /d "%~dp0"
echo --- SMART OFFICE START ---

start "Smart Office: Core" cmd /k "venv\Scripts\python.exe main.py"
timeout /t 5 >nul
start "Smart Office: Dashboard" cmd /k "venv\Scripts\python.exe -m streamlit run dashboard.py"

echo Smart Office started.
pause
