"""api/nt_account.py -- the ONE place that says which NinjaTrader account the paper legs trade.

2026-11-11 (owner via MANAGER, l19): NT8 paper moves from the broker demo DEMO7240108 (stuck at 790.83 after
the 11-04 stranded trades; its reset sits behind the NinjaTrader web sign-in) to NinjaTrader's local Sim101,
which resets inside NT8. Every reader takes the account from here instead of a literal:
  env EDGELOG_NT_ACCOUNT  >  C:\EdgeLog\nt_paper_account.txt (first line)  >  DEFAULT
The PowerShell watchdog reads the same file. The owner's REAL account is never a paper account.
"""
import os

REAL_ACCOUNT = "1810769"
DEFAULT = "Sim101"
PAPER_ACCOUNTS = ("Sim101", "DEMO7240108")      # every account the paper legs have ever traded
SWITCH_DATE = "2026-11-11"                      # DEMO7240108 history ends here; Sim101 starts
ACCOUNT_FILE = os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "nt_paper_account.txt")


def paper_account():
    acct = (os.environ.get("EDGELOG_NT_ACCOUNT") or "").strip()
    if not acct:
        try:
            with open(ACCOUNT_FILE, encoding="utf-8") as f:
                acct = (f.readline() or "").strip()
        except OSError:
            acct = ""
    if not acct or acct == REAL_ACCOUNT:
        return DEFAULT
    return acct
