@echo off
REM Sign the FMS Update Manager MSI (and optionally the EXE) using signtool.
REM
REM Required environment variables:
REM   FMS_SIGN_PFX  - absolute path to the .pfx code signing certificate
REM   FMS_SIGN_PWD  - password for the .pfx file
REM
REM Optional environment variables:
REM   FMS_SIGN_TSA  - RFC3161 timestamp server URL
REM                   (default: http://timestamp.digicert.com)
REM   FMS_SIGNTOOL  - explicit path to signtool.exe; if unset, signtool must be on PATH.
REM
REM Usage:
REM   sign_msi.bat <path-to-file-to-sign>
REM   sign_msi.bat dist\FMS_UPDATE_MANAGER_Installer.msi
REM
REM Exit codes:
REM   0  success
REM   1  missing args / env
REM   2  signtool failure

setlocal

if "%~1"=="" (
  echo [sign_msi] usage: sign_msi.bat ^<file-to-sign^>
  exit /b 1
)

if "%FMS_SIGN_PFX%"=="" (
  echo [sign_msi] FMS_SIGN_PFX is not set. Point it at the .pfx file path.
  exit /b 1
)
if "%FMS_SIGN_PWD%"=="" (
  echo [sign_msi] FMS_SIGN_PWD is not set.
  exit /b 1
)
if not exist "%FMS_SIGN_PFX%" (
  echo [sign_msi] certificate not found: %FMS_SIGN_PFX%
  exit /b 1
)

set "TARGET=%~1"
if not exist "%TARGET%" (
  echo [sign_msi] file to sign not found: %TARGET%
  exit /b 1
)

if "%FMS_SIGN_TSA%"=="" (
  set "FMS_SIGN_TSA=http://timestamp.digicert.com"
)

set "SIGNTOOL=%FMS_SIGNTOOL%"
if "%SIGNTOOL%"=="" (
  set "SIGNTOOL=signtool.exe"
)

echo [sign_msi] signing %TARGET%
echo [sign_msi]   pfx : %FMS_SIGN_PFX%
echo [sign_msi]   tsa : %FMS_SIGN_TSA%

"%SIGNTOOL%" sign /fd SHA256 /td SHA256 /tr "%FMS_SIGN_TSA%" /f "%FMS_SIGN_PFX%" /p "%FMS_SIGN_PWD%" /d "FMS Update Manager" "%TARGET%"
if errorlevel 1 (
  echo [sign_msi] signtool failed.
  exit /b 2
)

echo [sign_msi] verifying signature
"%SIGNTOOL%" verify /pa /v "%TARGET%"
if errorlevel 1 (
  echo [sign_msi] verify failed.
  exit /b 2
)

echo [sign_msi] OK
endlocal
exit /b 0
