@echo off
setlocal
set PYTHONIOENCODING=utf-8
set "PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
chcp 65001 >nul
cd /d "%~dp0"
echo Collecting news and preserving evidence...
"%PYTHON%" -m tonghoptin.cli collect %*
set collection_result=%errorlevel%
if not "%collection_result%"=="0" goto backup
"%PYTHON%" scripts/build_editorial.py --publish
set collection_result=%errorlevel%

:backup

:: Back up evidence even when collection fails. Never force-push or discard history.
if not exist archive\.git (
    echo Private archive checkout missing. Run: git clone https://github.com/muahong/TongHopTin-archive.git archive
    exit /b 1
)
"%PYTHON%" -m tonghoptin.cli backup
if errorlevel 1 exit /b 1
git -C archive add packs/ manifests/ index/ index.json README.md
if errorlevel 1 exit /b 1
git -C archive diff --cached --quiet
if errorlevel 1 (
    git -C archive commit -m "Preserve crawl history"
    if errorlevel 1 exit /b 1
)
git -C archive push
if errorlevel 1 (
    echo Archive push failed. Local packs are safe; reconcile the remote before retrying.
    exit /b 1
)
if not "%collection_result%"=="0" exit /b %collection_result%
git add docs/ editorial/
if errorlevel 1 exit /b 1
git diff --cached --quiet -- docs/ editorial/
if errorlevel 1 (
    git commit --only docs/ editorial/ -m "Update daily news reader"
    if errorlevel 1 exit /b 1
)
git push
if errorlevel 1 (
    echo Website push failed. No history was rewritten. Reconcile the remote before retrying.
    exit /b 1
)
echo Crawl history backed up; website update pushed to GitHub.
