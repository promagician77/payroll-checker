@echo off
cd /d "%~dp0"
where python >nul 2>nul || (echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
if not exist .venv (
  echo First run: setting things up, this takes a minute...
  python -m venv .venv || (pause & exit /b 1)
  .venv\Scripts\python -m pip install --quiet -r requirements.txt || (pause & exit /b 1)
)
.venv\Scripts\python run.py
pause
