@echo off
chcp 65001 >nul
echo ========================================
echo   TongHopTin - Vietnamese News Digest
echo ========================================
echo.

cd /d "%~dp0"

:: Record start time
set start_time=%time%
for /f "tokens=1-4 delims=:." %%a in ("%start_time%") do (
    set /a start_s=%%a*3600+%%b*60+%%c
)

echo [1/3] Collecting articles from all configured sites...
echo.

python -m tonghoptin.cli collect %*

if errorlevel 1 (
    echo.
    echo Collection failed. Check tonghoptin.log for details.
    pause
    exit /b 1
)

:: Calculate crawl duration
set end_crawl=%time%
for /f "tokens=1-4 delims=:." %%a in ("%end_crawl%") do (
    set /a end_crawl_s=%%a*3600+%%b*60+%%c
)
set /a crawl_dur=end_crawl_s-start_s

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

:: Calculate total duration
set end_time=%time%
for /f "tokens=1-4 delims=:." %%a in ("%end_time%") do (
    set /a end_s=%%a*3600+%%b*60+%%c
)
set /a total_dur=end_s-start_s
set /a crawl_min=crawl_dur/60
set /a crawl_sec=crawl_dur%%60
set /a total_min=total_dur/60
set /a total_sec=total_dur%%60

echo.
echo ========================================
echo   Done! Live at https://chuyenhay.com
echo   Crawl + Generate: %crawl_min%m %crawl_sec%s
echo   Total (+ push):   %total_min%m %total_sec%s
echo ========================================
echo.

:: Log duration to file
echo [%date% %time%] Crawl: %crawl_min%m %crawl_sec%s, Total: %total_min%m %total_sec%s >> tonghoptin_runs.log

:: Open the live site
start "" "https://chuyenhay.com"

pause
