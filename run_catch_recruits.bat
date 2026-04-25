@echo off
setlocal
cd /d "%~dp0"

set KEYWORD=%~1

python .\crawl_catch_recruits.py "%KEYWORD%"
pause
