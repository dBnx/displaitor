@echo off
setlocal
set "DISPLAITOR_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "%DISPLAITOR_PYTHON%" (
    "%DISPLAITOR_PYTHON%" "%~dp0run.py" %*
) else (
    py -3 "%~dp0run.py" %*
)
exit /b %errorlevel%
