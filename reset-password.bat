@echo off
cd /d "%~dp0backend"
set /p NAME=Username to reset (usually owner): 
..\.venv\Scripts\python -m app.cli reset-password %NAME%
pause
