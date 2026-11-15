@echo off
title MicroStock Standalone EXE Builder
echo ===================================================
echo   Pakujem MicroStockApp u Windows Desktop (.exe)...
echo ===================================================

call .venv\Scripts\activate
pip install pywebview pyinstaller

pyinstaller --noconfirm --onedir --windowed ^
  --name "MicroStockApp" ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "fonts;fonts" ^
  --add-data "translations;translations" ^
  --add-data "schema.sql;." ^
  desktop.py

echo.
echo ===================================================
echo   GOTOVO! Tvoj paket za prodaju se nalazi u:
echo   F:\VSCodeProjects\MicroStockApp\dist\MicroStockApp\
echo ===================================================
pause