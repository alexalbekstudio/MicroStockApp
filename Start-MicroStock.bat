@echo off
title MicroStock Standalone Pokretac
echo ===================================================
echo   Pokrecem MicroStock Standalone...
echo ===================================================

:: 1. Pokreni PostgreSQL kontejner ako postoji
docker start microstock-pg >nul 2>&1

:: 2. Aktiviraj virtuelno okruzenje i pokreni Flask u pozadini
start /B "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"

:: 3. Sacekaj 2 sekunde da se server podigne i otvori u App prozoru (kao Electron)
timeout /t 2 /nobreak >nul
start msedge --app=http://127.0.0.1:5000 || start chrome --app=http://127.0.0.1:5000 || start http://127.0.0.1:5000
exit