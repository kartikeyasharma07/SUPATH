@echo off
title SUPATH — Strategic Energy Transit Unit
cd /d "%~dp0"

echo ==================================================
echo   SUPATH — Strategic Energy Transit Unit
echo ==================================================
echo.
echo Installing dependencies (first run only takes a minute)...
python -m pip install -r requirements.txt -q
python scripts\install_abce.py

if not exist .env (
  if exist .env.example copy .env.example .env >nul
)

if exist .env (
  for /f "usebackq tokens=1,2 delims==" %%A in (".env") do (
    echo %%A| findstr /r "^#" >nul || if not "%%A"=="" set "%%A=%%B"
  )
)

echo.
echo Starting SUPATH at http://localhost:8000
echo Chrome will open automatically in a couple of seconds.
echo Leave this window open — closing it stops the server.
echo.

start /min cmd /c "timeout /t 3 >nul & start chrome http://localhost:8000 || start http://localhost:8000"

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

pause
