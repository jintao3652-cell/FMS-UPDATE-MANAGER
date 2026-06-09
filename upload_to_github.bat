@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION
chcp 65001 >nul 2>&1

REM ==========================================================================
REM  upload_to_github.bat
REM    Init git repo and push to GitHub. After push, the Actions workflow
REM    .github\workflows\build.yml auto-builds the MSI + portable ZIP.
REM
REM  Usage:
REM    upload_to_github.bat
REM        - uses GitHub CLI (gh) to create a private repo and push
REM    upload_to_github.bat https://github.com/USER/REPO.git
REM        - sets that URL as origin and pushes
REM
REM  Optional env vars:
REM    GH_REPO_NAME   repo name (default: current folder name, spaces -> '-')
REM    GH_VISIBILITY  gh visibility: private (default) / public
REM    GIT_BRANCH     main branch name (default: main)
REM ==========================================================================

cd /d "%~dp0"

set "REMOTE_URL=%~1"
if not defined GIT_BRANCH set "GIT_BRANCH=main"
if not defined GH_VISIBILITY set "GH_VISIBILITY=private"

REM default repo name = current folder name, spaces -> hyphen
set "DIR_NAME=%~nx0"
for %%I in (.) do set "DIR_NAME=%%~nxI"
set "DIR_NAME=%DIR_NAME: =-%"
if not defined GH_REPO_NAME set "GH_REPO_NAME=%DIR_NAME%"

where git >nul 2>&1
if errorlevel 1 (
  echo [upload] git not found. Please install Git for Windows.
  goto :fail
)

if exist ".git" goto :have_repo
echo [upload] git init...
git init -q
git symbolic-ref HEAD "refs/heads/%GIT_BRANCH%"
goto :ensure_identity

:have_repo
echo [upload] already a git repo, skip init.

:ensure_identity
git config user.email >nul 2>&1
if not errorlevel 1 goto :do_commit
echo [upload] no git user.email, setting a local default.
git config user.email "ci@example.com"
git config user.name "FMS Release Bot"

:do_commit
echo [upload] staging and committing...
git add -A
git diff --cached --quiet
if not errorlevel 1 goto :resolve_remote
git commit -q -m "Set up CI: auto-build MSI/ZIP, auto-increment version, drop legacy artifacts"
if errorlevel 1 (
  echo [upload] commit failed.
  goto :fail
)
echo [upload] commit created.

:resolve_remote
git remote get-url origin >nul 2>&1
if not errorlevel 1 (
  echo [upload] origin already set.
  goto :do_push
)
if defined REMOTE_URL goto :add_remote

where gh >nul 2>&1
if errorlevel 1 goto :no_remote
echo [upload] creating repo via gh: %GH_REPO_NAME% (%GH_VISIBILITY%)
gh repo create "%GH_REPO_NAME%" --%GH_VISIBILITY% --source=. --remote=origin --push
if errorlevel 1 (
  echo [upload] gh create/push failed. Run "gh auth login" first.
  goto :fail
)
echo [upload] Done. Repo created and pushed.
echo [upload] Open the repo's Actions page to watch the build.
goto :done

:add_remote
echo [upload] adding origin: %REMOTE_URL%
git remote add origin "%REMOTE_URL%"
goto :do_push

:no_remote
echo [upload] No remote URL given and gh not installed.
echo [upload] Re-run as:  upload_to_github.bat https://github.com/USER/REPO.git
echo [upload] or install GitHub CLI and run "gh auth login".
goto :fail

:do_push
echo [upload] pushing to origin/%GIT_BRANCH% ...
git push -u origin "%GIT_BRANCH%"
if errorlevel 1 (
  echo [upload] push failed. Check remote URL and permissions.
  goto :fail
)
echo [upload] Done. Open the repo's Actions page to watch the MSI/ZIP build.

:done
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1

