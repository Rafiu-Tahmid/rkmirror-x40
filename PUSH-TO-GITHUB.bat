@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo RK Mirror X40 - upload cloud build kit to GitHub
echo --------------------------------------------------
echo This only uploads the build files. Android builds run on GitHub, not this PC.
echo.

where git >nul 2>nul || (
  echo ERROR: Git was not found in PATH.
  echo Close this window, restart Windows, then run this file again.
  pause
  exit /b 1
)

if not exist ".github\workflows\build.yml" (
  echo ERROR: .github\workflows\build.yml is missing.
  echo Make sure you extracted the ZIP fully before running this file.
  pause
  exit /b 1
)
if not exist "apply_patch.py" (
  echo ERROR: apply_patch.py is missing.
  echo Make sure you extracted the ZIP fully before running this file.
  pause
  exit /b 1
)
if not exist "patches\rkx40.go" (
  echo ERROR: patches\rkx40.go is missing.
  echo Make sure you extracted the ZIP fully before running this file.
  pause
  exit /b 1
)

set /p REPOURL=Paste the HTTPS URL of a NEW EMPTY GitHub repository: 
if "%REPOURL%"=="" (
  echo ERROR: No repository URL entered.
  pause
  exit /b 1
)

echo "%REPOURL%" | findstr /R /I "^\"https://github.com/.*/.*\.git\"$" >nul
if errorlevel 1 (
  echo.
  echo WARNING: That does not look like the usual GitHub HTTPS .git URL.
  echo The expected format is: https://github.com/USERNAME/REPOSITORY.git
  echo.
)

if exist .git (
  echo Removing previous local Git metadata from an earlier attempt...
  rmdir /s /q .git
  if exist .git (
    echo ERROR: Could not remove the old .git folder. Close any Git tools using this folder and retry.
    pause
    exit /b 1
  )
)

echo Initializing local repository...
git init -b main >nul 2>&1
if errorlevel 1 (
  git init || goto :fail
  git branch -M main || goto :fail
)

REM Repository-local identity only. This does NOT change the user's global Git identity.
git config --local user.name "RK Mirror Builder" || goto :fail
git config --local user.email "rkmirror-builder@users.noreply.github.com" || goto :fail

REM Preserve the workflow's LF line endings and avoid harmless CRLF warnings.
git config --local core.autocrlf false || goto :fail
git config --local core.safecrlf false || goto :fail

echo Staging cloud-build files...
git add --all || goto :fail

git diff --cached --quiet
if not errorlevel 1 (
  echo ERROR: Git found no files to commit. Re-extract the kit into a normal folder and retry.
  pause
  exit /b 1
)

echo Creating local commit...
git commit -m "RK Mirror X40 cloud build" || goto :fail

echo Connecting to GitHub...
git remote add origin "%REPOURL%" || goto :fail

echo Uploading to GitHub...
echo If Git Credential Manager opens a browser, sign in and authorize it.
git push -u origin main || goto :pushfail

echo.
echo ==================================================
echo SUCCESS - the cloud-build kit is now on GitHub.
echo ==================================================
echo Open the repository in your browser, then:
echo   Actions ^> Build RK Mirror APKs ^> Run workflow ^> Run workflow
echo.
pause
exit /b 0

:pushfail
echo.
echo ERROR: GitHub push failed.
echo If a browser/login window appeared, finish the GitHub sign-in and run this file again.
echo If GitHub says the remote contains work, recreate the repository as EMPTY and retry.
pause
exit /b 1

:fail
echo.
echo ERROR: A local Git step failed. Copy the last error shown above and send it to ChatGPT.
pause
exit /b 1
