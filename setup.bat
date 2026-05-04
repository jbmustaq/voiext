@echo off
echo === Voice Type Setup ===
echo.

echo Installing Python dependencies for Python 3.11...
py -3.11 -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo.

echo Downloading Vosk model (one-time, ~50MB)...
py -3.11 -c "from voice_type import download_model; download_model()"
if %errorlevel% neq 0 (
    echo ERROR: Failed to download model.
    pause
    exit /b 1
)
echo.

echo === Setup complete! ===
echo Run: py -3.11 voice_type.py   or double-click VoiceType.vbs
pause