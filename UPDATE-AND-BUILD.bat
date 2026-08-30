@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
echo RK Mirror X40 - update GitHub and start cloud build
echo ---------------------------------------------------
echo Nothing Android-related is built on this PC.
echo.
set "DEFAULT_REPO=https://github.com/Rafiu-Tahmid/rkmirror-x40.git"
set /p "REPO=Repository URL [%DEFAULT_REPO%]: "
if "%REPO%"=="" set "REPO=%DEFAULT_REPO%"

where git >nul 2>&1 || (
  echo ERROR: Git is not available in PATH.
  pause
  exit /b 1
)

set "WORK=%TEMP%\rkmirror-cloud-v14-update"
if exist "%WORK%" rmdir /s /q "%WORK%"

echo Cloning existing repository...
git clone "%REPO%" "%WORK%" || goto :fail
cd /d "%WORK%"
git config user.name "RK Mirror Builder"
git config user.email "rkmirror-build@users.noreply.github.com"
git config core.autocrlf false

rem Remove obsolete kit files so stale v1.3 source cannot affect the build.
if exist ".github" rmdir /s /q ".github"
if exist "tools" rmdir /s /q "tools"
if exist "patches" rmdir /s /q "patches"
del /q apply_patch.py generate_rkx40.py CLOUD-KIT-VERSION.txt .gitattributes 2>nul

mkdir ".github\workflows" >nul 2>&1
mkdir "tools" >nul 2>&1
copy /y "%~dp0.github\workflows\build.yml" ".github\workflows\build.yml" >nul || goto :fail
copy /y "%~dp0apply_patch.py" "apply_patch.py" >nul || goto :fail
copy /y "%~dp0generate_rkx40.py" "generate_rkx40.py" >nul || goto :fail
copy /y "%~dp0CLOUD-KIT-VERSION.txt" "CLOUD-KIT-VERSION.txt" >nul || goto :fail
copy /y "%~dp0.gitattributes" ".gitattributes" >nul || goto :fail
copy /y "%~dp0tools\manual_prepare.py" "tools\manual_prepare.py" >nul || goto :fail
copy /y "%~dp0tools\manual_build_airplay.sh" "tools\manual_build_airplay.sh" >nul || goto :fail

rem Keep the updater itself in the repository for reproducibility.
copy /y "%~dp0UPDATE-AND-BUILD.bat" "UPDATE-AND-BUILD.bat" >nul
copy /y "%~dp0README-FIRST.md" "README-FIRST.md" >nul

git add -A || goto :fail
git commit --allow-empty -m "RK Mirror X40 v1.4 adaptive cloud builder" || goto :fail

echo.
echo Pushing v1.4. The push itself automatically starts GitHub Actions...
git push origin HEAD:main || goto :fail

echo.
echo ==================================================
echo SUCCESS - v1.4 pushed and cloud build triggered.
echo ==================================================
echo You do NOT need to click Run workflow.
echo The Actions page will open now. Wait for Profile 1/2/3.
start "" "https://github.com/Rafiu-Tahmid/rkmirror-x40/actions"
pause
exit /b 0

:fail
echo.
echo UPDATE FAILED before the cloud build could start.
echo No Android SDK/NDK changes were made to this PC.
pause
exit /b 1
