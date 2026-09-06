@echo off
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Project Python missing: install requirements in .venv first.
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m tonghoptin.automation %*
exit /b %errorlevel%
