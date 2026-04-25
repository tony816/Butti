@echo off
setlocal
cd /d "%~dp0"
set LOG=%~dp0run_downloader.log
echo [%date% %time%] Starting OpenDART launcher > "%LOG%"
set LOCAL_PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe

if exist "%LOCAL_PY%" (
    echo Using %LOCAL_PY% >> "%LOG%"
    "%LOCAL_PY%" opendart_gui.py
    echo Exit code: %errorlevel% >> "%LOG%"
    goto :done
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 --version >nul 2>nul
    if not errorlevel 1 (
        echo Using py -3 >> "%LOG%"
        py -3 opendart_gui.py
        echo Exit code: %errorlevel% >> "%LOG%"
        goto :done
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    python --version >nul 2>nul
    if not errorlevel 1 (
        echo Using python >> "%LOG%"
        python opendart_gui.py
        echo Exit code: %errorlevel% >> "%LOG%"
        goto :done
    )
)

where python3 >nul 2>nul
if not errorlevel 1 (
    python3 --version >nul 2>nul
    if not errorlevel 1 (
        echo Using python3 >> "%LOG%"
        python3 opendart_gui.py
        echo Exit code: %errorlevel% >> "%LOG%"
        goto :done
    )
)

echo Python launcher was not found. >> "%LOG%"
echo Python launcher was not found.
echo Install Python 3.10 or newer, then run this file again.
echo Download: https://www.python.org/downloads/windows/
echo.
echo A log was saved here:
echo %LOG%

:done
echo.
pause
