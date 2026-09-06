@echo off
call "%~dp0run.bat" --trigger startup %*
exit /b %errorlevel%
