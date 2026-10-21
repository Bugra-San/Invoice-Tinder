@echo off
chcp 65001 >nul
title Rechnungs-Tinder
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

if not exist ".venv\Scripts\python.exe" (
  echo Erster Start: Programm wird eingerichtet. Das dauert einen Moment ...
  %PY% -m venv .venv || goto :fehler
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fehler
)

".venv\Scripts\python.exe" -m rechnungs_tinder %*
if errorlevel 1 pause
goto :eof

:fehler
echo.
echo Es ist ein Fehler aufgetreten. Ist Python installiert? (https://www.python.org/downloads/)
pause
