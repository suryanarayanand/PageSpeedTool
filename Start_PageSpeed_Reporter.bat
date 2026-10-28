@echo off
setlocal
cd /d "%~dp0"
set "REPORT_PYTHON=%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
if exist "%REPORT_PYTHON%" goto run
set "REPORT_PYTHON=python"
:run
echo RSS PageSpeed Reporter - open http://127.0.0.1:5055
"%REPORT_PYTHON%" server.py
pause
