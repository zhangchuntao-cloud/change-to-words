@echo off
setlocal

set "ROOT=%~dp0"

if not exist "%ROOT%.deps\faster_whisper" goto missing

set "PYTHONPATH=%ROOT%src;%ROOT%.deps;%PYTHONPATH%"

if defined CTW_PYTHON goto custom
where py >nul 2>nul
if not errorlevel 1 goto usepy
goto usepython

:custom
"%CTW_PYTHON%" -m change_to_words %*
exit /b

:usepy
py -m change_to_words %*
exit /b

:usepython
python -m change_to_words %*
exit /b

:missing
echo Error: local dependencies not found: %ROOT%.deps
echo Run: powershell -ExecutionPolicy Bypass -File "%ROOT%setup_local.ps1"
exit /b 1
