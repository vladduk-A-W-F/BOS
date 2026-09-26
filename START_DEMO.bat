@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title BoS - Локальний запуск
if not exist "manage.py" goto not_extracted
if not exist "scripts\start_local.py" goto not_extracted
py -3.12 -c "import sys; sys.exit(not ((3,12) <= sys.version_info[:2] < (3,15)))" >nul 2>&1
if not errorlevel 1 goto py312
py -3.13 -c "import sys; sys.exit(not ((3,12) <= sys.version_info[:2] < (3,15)))" >nul 2>&1
if not errorlevel 1 goto py313
py -3.14 -c "import sys; sys.exit(not ((3,12) <= sys.version_info[:2] < (3,15)))" >nul 2>&1
if not errorlevel 1 goto py314
python -c "import sys; sys.exit(not ((3,12) <= sys.version_info[:2] < (3,15)))" >nul 2>&1
if not errorlevel 1 goto python_path
echo.
echo Python 3.12, 3.13 або 3.14 не знайдено.
echo Встановіть Python 3.12: https://www.python.org/downloads/windows/
echo Під час встановлення увімкніть Python Launcher або додавання до PATH.
echo Потім повторно запустіть START_DEMO.bat.
goto failed
:py312
py -3.12 scripts\start_local.py %*
goto finished
:py313
py -3.13 scripts\start_local.py %*
goto finished
:py314
py -3.14 scripts\start_local.py %*
goto finished
:python_path
python scripts\start_local.py %*
goto finished
:not_extracted
echo Спочатку розпакуйте весь архів, потім запустіть START_DEMO.bat.
goto failed
:finished
if errorlevel 1 goto failed
echo BoS зупинено.
pause
exit /b 0
:failed
echo.
echo BoS не запущено. Вікно залишиться відкритим.
echo Зробіть знімок повідомлення про помилку вище.
echo За наявності перевірте BoS_STARTUP.log у цій папці.
pause
exit /b 1
