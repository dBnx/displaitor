@echo off
setlocal
set "COMPANION_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "%COMPANION_PYTHON%" (
    "%COMPANION_PYTHON%" "%~dp0pixel_companion.py" %*
) else (
    py -3 "%~dp0pixel_companion.py" %*
)
exit /b %errorlevel%
