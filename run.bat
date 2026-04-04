@echo off
chcp 65001 >nul
echo ========================================
echo   TongHopTin - Vietnamese News Digest
echo ========================================
echo.

cd /d "%~dp0"

echo Collecting articles from all configured sites...
echo.

python -m tonghoptin.cli collect %*

echo.
echo ========================================

:: Open the latest HTML file in default browser
for /f "delims=" %%f in ('dir /b /o-d output\tonghoptin_*.html 2^>nul') do (
    echo Opening output\%%f in browser...
    start "" "output\%%f"
    goto :done
)
echo No output file generated.

:done
echo.
pause
