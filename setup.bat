@echo off
cd /d "%~dp0"
where python >nul 2>nul || (echo Install Python 3.12 or newer from python.org first and tick "Add python.exe to PATH". & pause & exit /b 1)
if not exist .venv python -m venv .venv || goto failed
.venv\Scripts\python -m pip install -r backend\requirements.txt || goto failed
if not exist frontend\out (
  where npm >nul 2>nul || (echo Install Node.js LTS from nodejs.org to build the dashboard. & pause & exit /b 1)
  pushd frontend
  call npm ci || goto failed
  call npm run build || goto failed
  popd
)
.venv\Scripts\python setup.py || goto failed
pause
exit /b 0
:failed
echo Setup did not finish. Read the message above.
pause
exit /b 1
