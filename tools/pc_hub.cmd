@echo off
setlocal
set "HUB_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "%HUB_PYTHON%" (
    "%HUB_PYTHON%" "%~dp0pc_hub.py" %*
) else (
    py -3 "%~dp0pc_hub.py" %*
)
exit /b %errorlevel%
