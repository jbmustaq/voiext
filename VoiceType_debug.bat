@echo off
title VoiceType debug
cd /d "%~dp0"
echo Installing dependencies for Python 3.11 (safe to repeat)...
py -3.11 -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo pip failed. If "py -3.11" is not found, reinstall Python 3.11 with "py launcher" checked.
  pause
  exit /b 1
)
echo.
echo Starting app (errors will show below)...
py -3.11 voice_type.py
echo.
echo Exit code %errorlevel%
pause
