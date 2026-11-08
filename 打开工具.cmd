@echo off
cd /d "%~dp0"
python "%~dp0lanyuext.py" --gui
if errorlevel 1 pause
