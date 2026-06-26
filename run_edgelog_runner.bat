@echo off
REM ============================================================================
REM  AUGUR runner — watches your EDGELOG Firestore for queued backtests and runs
REM  them on THIS PC, writing results back. Leave this window open while trading.
REM  Fill in the two values below ONCE (see docs/EDGELOG_GOLIVE.md).
REM ============================================================================
cd /d "%~dp0"

REM Your Firebase user id (Firebase console -> Authentication -> Users -> UID):
set AUGUR_UID=IO0K35JpLIcH9YK4C0pMNYUzZOM2

REM Path to your service-account key JSON (downloaded from the Firebase console):
set AUGUR_CRED=serviceAccount.json

if not exist "%~dp0%AUGUR_CRED%" (
  echo.
  echo ============================================================================
  echo  ERROR: service-account key not found:
  echo     %~dp0%AUGUR_CRED%
  echo.
  echo  The runner cannot connect to Firestore without it, so nothing will sync
  echo  ^(this is why your strategies/model numbers did not carry over^).
  echo.
  echo  To fix:
  echo   1. Firebase console -^> Project settings -^> Service accounts
  echo   2. Click "Generate new private key" -^> download the .json
  echo   3. Save it in this folder as  serviceAccount.json
  echo      ^(it is gitignored, so it will not be committed^)
  echo  See docs\EDGELOG_GOLIVE.md for the full walkthrough.
  echo ============================================================================
  echo.
  pause
  exit /b 1
)

echo Starting AUGUR runner (Firestore watch) for uid %AUGUR_UID% ...
python -m api.runner --firestore --cred "%AUGUR_CRED%" --allow-uid %AUGUR_UID% --watch
pause
