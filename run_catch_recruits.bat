@echo off
setlocal
cd /d "%~dp0"

set KEYWORD=%~1
if "%KEYWORD%"=="" set KEYWORD=삼성

set INTERVAL_MINUTES=%~2
if "%INTERVAL_MINUTES%"=="" set INTERVAL_MINUTES=60

python .\crawl_catch_recruits.py "%KEYWORD%" --watch --interval-minutes %INTERVAL_MINUTES% --max-results 30
pause
