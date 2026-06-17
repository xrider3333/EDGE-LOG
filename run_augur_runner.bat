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

echo Starting AUGUR runner (Firestore watch) for uid %AUGUR_UID% ...
python -m api.runner --firestore --cred "%AUGUR_CRED%" --allow-uid %AUGUR_UID% --watch
pause
