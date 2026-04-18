@echo off
chcp 65001 >nul
echo ========================================
echo   TongHopTin - Vietnamese News Digest
echo ========================================
echo.

cd /d "%~dp0"

:: Record start time. Strip leading space and force base-10 on HH/MM/SS so
:: 08/09 aren't mis-parsed as invalid octal (which silently evaluates to 0).
set start_time=%time: =0%
for /f "tokens=1-4 delims=:." %%a in ("%start_time%") do (
    set /a start_s=(1%%a-100)*3600+(1%%b-100)*60+(1%%c-100)
)

echo [1/3] Collecting articles from all configured sites...
echo.

python -m tonghoptin.cli collect %*

if errorlevel 1 (
    echo.
    echo [%date% %time%] Collection failed. >> tonghoptin_runs.log
    echo Collection failed. Check tonghoptin.log for details.
    exit /b 1
)

:: Calculate crawl duration (base-10 trick to avoid octal parsing of 08/09)
set end_crawl=%time: =0%
for /f "tokens=1-4 delims=:." %%a in ("%end_crawl%") do (
    set /a end_crawl_s=(1%%a-100)*3600+(1%%b-100)*60+(1%%c-100)
)
set /a crawl_dur=end_crawl_s-start_s
if %crawl_dur% LSS 0 set /a crawl_dur+=86400

echo.
echo [2/3] Publishing to chuyenhay.com...

git add docs/
git commit -m "Update digest %date:~0,4%-%date:~5,2%-%date:~8,2% %time:~0,2%:%time:~3,2%"

echo.
echo [3/3] Pushing to GitHub...

git push

if errorlevel 1 (
    echo.
    echo Push failed. Remote has diverged - merging with local docs/ as winner...
    git fetch origin main
    git merge origin/main --no-edit -X ours -m "Merge remote digest (keep local docs/)"
    if errorlevel 1 (
        echo.
        echo Merge failed. Aborting and force-pushing local digest...
        git merge --abort
        git push --force-with-lease origin main
    ) else (
        git push
        if errorlevel 1 (
            echo Push still failing after merge. Force-pushing local digest...
            git push --force-with-lease origin main
        )
    )
)

:: Calculate total duration (base-10 trick to avoid octal parsing of 08/09)
set end_time=%time: =0%
for /f "tokens=1-4 delims=:." %%a in ("%end_time%") do (
    set /a end_s=(1%%a-100)*3600+(1%%b-100)*60+(1%%c-100)
)
set /a total_dur=end_s-start_s
if %total_dur% LSS 0 set /a total_dur+=86400
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

:: Log duration to file
echo [%date% %time%] Crawl: %crawl_min%m %crawl_sec%s, Total: %total_min%m %total_sec%s >> tonghoptin_runs.log
