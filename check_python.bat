@echo off
setlocal
echo Checking Python launchers...
echo.

echo [Local Python 3.12]
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" --version
) else (
    echo Not found
)
echo.

echo [py]
where py
py -3 --version
echo.

echo [python]
where python
python --version
echo.

echo [python3]
where python3
python3 --version
echo.

echo If all commands fail, install Python 3.10 or newer.
echo Download: https://www.python.org/downloads/windows/
echo During install, check "Add python.exe to PATH".
echo.
pause
