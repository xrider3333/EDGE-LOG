@echo off
rem Always run from THIS bat's folder (the old hardcoded Desktop\AUGOR path was
rem stale — the cd failed silently and it only worked by accident).
cd /d "%~dp0"

rem ── Clear stale instances so a half-dead app can't hold port 8501 hostage ──
rem Kills only processes LISTENING on 8501 plus orphaned streamlit launchers;
rem other python apps are untouched.
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Get-Process streamlit -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue" >nul 2>&1

:loop
streamlit run optimizer.py
pause
goto loop
