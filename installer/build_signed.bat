@echo off
REM End-to-end signed build:
REM   1) PyInstaller  -> dist\FMS_UPDATE_MANAGER\FMS_UPDATE_MANAGER.exe
REM   2) signtool     -> sign the .exe (Authenticode helps SmartScreen rep-build)
REM   3) WiX          -> installer\FMS_UPDATE_MANAGER_<ver>.msi
REM   4) signtool     -> sign the .msi
REM
REM Required env:
REM   FMS_SIGN_PFX         absolute path to your code-signing .pfx
REM   FMS_SIGN_PWD         password for the .pfx
REM Optional env:
REM   FMS_SIGN_TSA         RFC3161 TSA (default http://timestamp.digicert.com)
REM   FMS_SIGNTOOL         absolute path to signtool.exe (else must be on PATH)
REM   FMS_WIX_BIN          absolute path to WiX v4 'wix' binary (else must be on PATH)
REM   FMS_APP_VERSION      version stamped into MSI (default: read from main_flet APP_VERSION env or 1.0.5)
REM   FMS_SKIP_SIGN_EXE    set to 1 to skip exe signing
REM   FMS_SKIP_SIGN_MSI    set to 1 to skip msi signing (e.g. CI dry runs)
REM
REM Usage:
REM   build_signed.bat           (uses FMS_UPDATE_MANAGER.spec)
REM   build_signed.bat beta      (uses FMS_UPDATE_MANAGER_beta.spec)

setlocal ENABLEDELAYEDEXPANSION

if "%FMS_APP_VERSION%"=="" set "FMS_APP_VERSION=1.0.9"

if "%FMS_SKIP_SIGN_EXE%"=="1" if "%FMS_SKIP_SIGN_MSI%"=="1" goto :skip_pfx_check
if "%FMS_SIGN_PFX%"=="" (
  echo [build] FMS_SIGN_PFX not set
  exit /b 1
)
if "%FMS_SIGN_PWD%"=="" (
  echo [build] FMS_SIGN_PWD not set
  exit /b 1
)
if not exist "%FMS_SIGN_PFX%" (
  echo [build] cert not found: %FMS_SIGN_PFX%
  exit /b 1
)
:skip_pfx_check

set "VARIANT=%~1"
if "%VARIANT%"=="" (
  set "SPEC=FMS_UPDATE_MANAGER.spec"
  set "WXS=installer\FMS_UPDATE_MANAGER.wxs"
  set "EXE_NAME=FMS_UPDATE_MANAGER.exe"
  set "DIST_DIR=dist\FMS_UPDATE_MANAGER"
  set "MSI_NAME=FMS Update Manager %FMS_APP_VERSION%.msi"
) else (
  set "SPEC=FMS_UPDATE_MANAGER_beta.spec"
  set "WXS=installer\FMS_UPDATE_MANAGER_beta.wxs"
  set "EXE_NAME=FMS_UPDATE_MANAGER.exe"
  set "DIST_DIR=dist\FMS_UPDATE_MANAGER"
  set "MSI_NAME=FMS Update Manager %FMS_APP_VERSION%.msi"
)

if "%FMS_APP_VERSION%"=="" set "FMS_APP_VERSION=1.0.9"

echo [build] variant=%VARIANT% version=%FMS_APP_VERSION%
echo [build] spec=%SPEC%

REM --- 1) PyInstaller -------------------------------------------------------
echo [build] running PyInstaller...
python -m PyInstaller --noconfirm --clean "%SPEC%"
if errorlevel 1 (
  echo [build] PyInstaller failed.
  exit /b 2
)
if not exist "%DIST_DIR%\%EXE_NAME%" (
  echo [build] expected exe not found: %DIST_DIR%\%EXE_NAME%
  exit /b 2
)

REM --- 2) Sign the EXE ------------------------------------------------------
if not "%FMS_SKIP_SIGN_EXE%"=="1" (
  echo [build] signing exe: %DIST_DIR%\%EXE_NAME%
  call "%~dp0sign_msi.bat" "%DIST_DIR%\%EXE_NAME%"
  if errorlevel 1 (
    echo [build] exe signing failed.
    exit /b 3
  )
) else (
  echo [build] skipping exe signing (FMS_SKIP_SIGN_EXE=1^)
)

REM --- 3) WiX -> MSI --------------------------------------------------------
set "WIX=%FMS_WIX_BIN%"
if "%WIX%"=="" set "WIX=wix"

echo [build] building MSI from %WXS%
"%WIX%" build -arch x64 -ext WixToolset.Util.wixext -ext WixToolset.UI.wixext -d "SourceDir=%CD%\%DIST_DIR%" -d "ProjectDir=%CD%" -d "ProductVersion=%FMS_APP_VERSION%" -d "WixUILicenseRtf=%CD%\installer\license.rtf" -o "installer\%MSI_NAME%" "%WXS%"
if errorlevel 1 (
  echo [build] WiX build failed.
  exit /b 4
)
if not exist "installer\%MSI_NAME%" (
  echo [build] MSI not produced: installer\%MSI_NAME%
  exit /b 4
)

REM --- 4) Sign the MSI ------------------------------------------------------
if not "%FMS_SKIP_SIGN_MSI%"=="1" (
  echo [build] signing msi: installer\%MSI_NAME%
  call "%~dp0sign_msi.bat" "installer\%MSI_NAME%"
  if errorlevel 1 (
    echo [build] msi signing failed.
    exit /b 5
  )
) else (
  echo [build] skipping msi signing (FMS_SKIP_SIGN_MSI=1^)
)

echo.
echo [build] DONE
echo [build]   exe : %DIST_DIR%\%EXE_NAME%
echo [build]   msi : installer\%MSI_NAME%

REM --- 5) Portable ZIP ------------------------------------------------------
if "%FMS_SKIP_PORTABLE%"=="1" goto :portable_done
set "PORTABLE_NAME=FMS Update Manager %FMS_APP_VERSION% ±ãÐ¯°æ.zip"
set "PORTABLE_PATH=installer\%PORTABLE_NAME%"
echo [build] creating portable zip: %PORTABLE_PATH%
if exist "%PORTABLE_PATH%" del /q "%PORTABLE_PATH%"
type nul > "%DIST_DIR%\portable.flag"
where 7z >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Compress-Archive -Path '%DIST_DIR%\*' -DestinationPath '%PORTABLE_PATH%' -Force"
) else (
  7z a -tzip "%PORTABLE_PATH%" "%DIST_DIR%\*" >nul
)
del /q "%DIST_DIR%\portable.flag" 2>nul
if exist "%PORTABLE_PATH%" (
  echo [build]   zip : %PORTABLE_PATH%
) else (
  echo [build] portable zip creation failed
)
:portable_done

REM --- 6) Incremental update artifacts (manifest + release.zip) -------------
if "%FMS_SKIP_INCREMENTAL%"=="1" goto :incremental_done
if "%FMS_MANIFEST_PRIVKEY%"=="" (
  echo [build] FMS_MANIFEST_PRIVKEY not set; skipping manifest generation.
  echo [build]   set FMS_MANIFEST_PRIVKEY=path\to\manifest_priv.pem to enable.
  goto :incremental_done
)
if not exist "%FMS_MANIFEST_PRIVKEY%" (
  echo [build] manifest private key not found: %FMS_MANIFEST_PRIVKEY%
  exit /b 6
)

set "PY=%FMS_PYTHON%"
if "%PY%"=="" set "PY=python"

echo [build] generating manifest.json (version %FMS_APP_VERSION%) ...
"%PY%" tools\build_manifest.py "%DIST_DIR%" "%FMS_APP_VERSION%" --privkey "%FMS_MANIFEST_PRIVKEY%" --out-dir installer
if errorlevel 1 (
  echo [build] manifest generation failed
  exit /b 6
)

set "RELEASE_ZIP=installer\release.zip"
echo [build] creating release.zip: %RELEASE_ZIP%
if exist "%RELEASE_ZIP%" del /q "%RELEASE_ZIP%"
where 7z >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Compress-Archive -Path '%DIST_DIR%\*' -DestinationPath '%RELEASE_ZIP%' -Force"
) else (
  7z a -tzip "%RELEASE_ZIP%" "%DIST_DIR%\*" -xr!portable.flag >nul
)
if not exist "%RELEASE_ZIP%" (
  echo [build] release.zip creation failed
  exit /b 6
)
echo [build]   manifest : installer\manifest.json
echo [build]   sig      : installer\manifest.json.sig
echo [build]   zip      : %RELEASE_ZIP%
:incremental_done

endlocal
exit /b 0
