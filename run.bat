@echo off
chcp 65001 >nul
echo ========================================
echo   TongHopTin - Vietnamese News Digest
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] Collecting articles from all configured sites...
echo.

python -m tonghoptin.cli collect %*

if errorlevel 1 (
    echo.
    echo Collection failed. Check tonghoptin.log for details.
    pause
    exit /b 1
)

echo.
echo [2/3] Publishing to chuyenhay.com...

git add docs/
git commit -m "Update digest %date:~0,4%-%date:~5,2%-%date:~8,2% %time:~0,2%:%time:~3,2%"

echo.
echo [3/3] Pushing to GitHub...

git push

if errorlevel 1 (
    echo.
    echo Push failed. You may need to run: git pull --rebase origin main ^&^& git push
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Done! Live at https://chuyenhay.com
echo ========================================
echo.

:: Open the live site
start "" "https://chuyenhay.com"

pause
