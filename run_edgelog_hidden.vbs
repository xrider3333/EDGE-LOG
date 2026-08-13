' EdgeLog runner launcher — starts the NinjaTrader -> Firestore trade sync in the
' background with NO console window. Used by the "EdgeLogRunner" Startup-folder entry
' (runs at logon) and can also be double-clicked to start the sync manually.
'   --refresh-min 240  : skip the AUGUR Yahoo master-refresh (AUGUR does its own on open).
'   --interval 30    : poll the backtest/command queue every 30s (not 3s) to stay well
'                      inside the Firestore free-tier read quota.
'   --trades-sec 20  : sync NinjaTrader fills every 20s (local read; heartbeat write is
'                      throttled to on-change / ~5 min in nt_sync).
' Output is appended to C:\EdgeLog\runner.log for troubleshooting.
Set sh = CreateObject("WScript.Shell")
sh.Run "cmd /c cd /d ""C:\Users\xride\OneDrive\Desktop\EDGE-LOG"" && set AUGUR_TRIAL_CACHE=1 && python -u -m api.runner --firestore --cred serviceAccount.json --allow-uid IO0K35JpLIcH9YK4C0pMNYUzZOM2 --watch --refresh-min 240 --interval 30 --trades-sec 20 >> ""C:\EdgeLog\runner.log"" 2>&1", 0, False
