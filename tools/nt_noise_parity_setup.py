"""NOISE crown parity — offline NinjaTrader surgery (2026-08-24).

Sets up the engine-vs-NT parity backtest of the run-#243 NOISE crown
(lookback 44 / bands 0.75 & 1.5 / vwap exit / bandwidth stop k1.75 +
daytype_mode='skip_bot_short' (0.20) + vol_skip_pct=90), by writing
NinjaTrader's own persistence while NinjaTrader is STOPPED — the same
owner-granted capability as tools/nt_reconfig.py --add-orb230.

WHAT IT DOES (all backed up first, every replace asserted to hit exactly once):
  1. Patches the LIVE demo EdgeLogNOISE row (id 386606468): its saved XML predates
     the four filter knobs, and a missing element deserializes to the CLR default
     (0.0 / false), which for DaytypeLo (Range 0.05-0.5) and VolSkipPct (Range
     50-100) is OUT OF RANGE -> the silent [Range]-finalize trap documented in
     tools/nt/NT_RUNBOOK.md. Injects explicit in-range values that keep the leg's
     behaviour EXACTLY as it runs today: SkipBotShort=false, DaytypeLo=0.2,
     VolSkipOn=false, VolSkipPct=90, HistFills=false.
  2. Inserts a NEW row `EdgeLogNOISEPAR` (class EdgeLogNOISE, id 386606476) on
     account Sim101 / MNQ 09-26, hosted on the live NOISE chart (525 days of
     5m bars, session template EDGELOG RTH 0930-1600): the pure crown config —
     Qty=10 (10 micros = $20/pt = the engine's NQ multiplier), SkipBotShort=true,
     VolSkipOn=true, GateEnabled=false, HistFills=true. It is NOT enabled and is
     NOT in nt_recover.ps1's roster; enabling/disabling it via the bridge runs the
     historical backtest and dumps the blotter to C:\\EdgeLog\\nt_backtest.
  3. Copies the freshly built NinjaTrader.Custom.dll (bin\\Custom\\bin\\Debug) over
     the one NinjaTrader loads (bin\\Custom) — the 08-21/08-23 "compiled" filter
     knobs never actually landed in that DLL (verified absent 2026-08-24).

Run:  python tools/nt_noise_parity_setup.py [--dry-run]
Then: powershell -ExecutionPolicy Bypass -File C:\\EdgeLog\\nt_recover.ps1
"""
import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime

WORKSPACE = r"C:\Users\xride\Documents\NinjaTrader 8\workspaces\Untitled 2.xml"
NT_DB = r"C:\Users\xride\Documents\NinjaTrader 8\db\NinjaTrader.sqlite"
CUSTOM = os.path.expanduser(r"~\Documents\NinjaTrader 8\bin\Custom")

NOISE_ID = 386606468
PARITY_ID = 386606476
PARITY_NAME = "EdgeLogNOISEPAR"
ACCT_SIM101 = 2
MNQ_0926_ID = 699839150767964

CRLF = "\r\n  "
# Escaped-XML element blocks, in the .cs property DECLARATION order (XmlSerializer
# writes/reads elements in that order): ...Qty, SkipBotShort, DaytypeLo, VolSkipOn,
# VolSkipPct, HistFills, GateEnabled...
DEMO_ANCHOR = "&lt;Qty&gt;3&lt;/Qty&gt;\r\n  &lt;GateEnabled&gt;"
DEMO_INJECT = ("&lt;Qty&gt;3&lt;/Qty&gt;" + CRLF
               + "&lt;SkipBotShort&gt;false&lt;/SkipBotShort&gt;" + CRLF
               + "&lt;DaytypeLo&gt;0.2&lt;/DaytypeLo&gt;" + CRLF
               + "&lt;VolSkipOn&gt;false&lt;/VolSkipOn&gt;" + CRLF
               + "&lt;VolSkipPct&gt;90&lt;/VolSkipPct&gt;" + CRLF
               + "&lt;HistFills&gt;false&lt;/HistFills&gt;" + CRLF
               + "&lt;GateEnabled&gt;")

PARITY_EDITS = [  # (old, new) — each must hit exactly once in the (patched) clone
    ("&lt;Name&gt;EdgeLogNOISE&lt;/Name&gt;",
     "&lt;Name&gt;EdgeLogNOISEPAR&lt;/Name&gt;"),
    ("&lt;Qty&gt;3&lt;/Qty&gt;", "&lt;Qty&gt;10&lt;/Qty&gt;"),
    ("&lt;SkipBotShort&gt;false&lt;/SkipBotShort&gt;",
     "&lt;SkipBotShort&gt;true&lt;/SkipBotShort&gt;"),
    ("&lt;VolSkipOn&gt;false&lt;/VolSkipOn&gt;",
     "&lt;VolSkipOn&gt;true&lt;/VolSkipOn&gt;"),
    ("&lt;HistFills&gt;false&lt;/HistFills&gt;",
     "&lt;HistFills&gt;true&lt;/HistFills&gt;"),
    ("&lt;GateEnabled&gt;true&lt;/GateEnabled&gt;",
     "&lt;GateEnabled&gt;false&lt;/GateEnabled&gt;"),
]

WS_ANCHOR = f'<Strategy0 BarsIndex="0">{NOISE_ID}</Strategy0>'
WS_INSERT = (WS_ANCHOR
             + f'\r\n            <Strategy1 BarsIndex="0">{PARITY_ID}</Strategy1>')


def log(m):
    print(f"{datetime.now().strftime('%H:%M:%S')}  {m}", flush=True)


def backup(path):
    dst = f"{path}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, dst)
    log(f"backup: {dst}")


def nt_running():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-Process NinjaTrader -ErrorAction SilentlyContinue) -ne $null"],
                         capture_output=True, text=True).stdout.strip()
    return out == "True"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not a.dry_run and nt_running():
        sys.exit("NinjaTrader is RUNNING - stop it first (it rewrites both stores on exit).")

    con = sqlite3.connect(f"file:{NT_DB}?mode=ro", uri=True)
    con.text_factory = bytes
    try:
        row = con.execute("SELECT Category, Classname, IsReplay, IsResetOnNewTradingDay, "
                          "IsTerminal, ServerId, Template, Userdata, Workspace "
                          "FROM Strategies WHERE Id=?", (NOISE_ID,)).fetchone()
        exists = con.execute("SELECT COUNT(*) FROM Strategies WHERE Id=? OR Name=?",
                             (PARITY_ID, PARITY_NAME.encode())).fetchone()[0]
    finally:
        con.close()
    if row is None:
        sys.exit("live NOISE row not found - aborting")
    ud = row[7].decode("utf-16-le")

    already_patched = "&lt;SkipBotShort&gt;" in ud
    if not already_patched and ud.count(DEMO_ANCHOR) != 1:
        sys.exit("demo row param-block anchor not found exactly once - refusing")

    demo_ud = ud if already_patched else ud.replace(DEMO_ANCHOR, DEMO_INJECT, 1)

    par_ud = demo_ud
    for old, new in PARITY_EDITS:
        if par_ud.count(old) != 1:
            sys.exit(f"parity clone: token not found exactly once: {old}")
        par_ud = par_ud.replace(old, new, 1)

    w = open(WORKSPACE, encoding="utf-8", newline="").read()
    ws_done = f'>{PARITY_ID}</Strategy1>' in w
    if not ws_done and w.count(WS_ANCHOR) != 1:
        sys.exit("workspace NOISE chart anchor not found exactly once - refusing")

    src_dll = os.path.join(CUSTOM, "bin", "Debug", "NinjaTrader.Custom.dll")
    dst_dll = os.path.join(CUSTOM, "NinjaTrader.Custom.dll")
    if not os.path.exists(src_dll):
        sys.exit("fresh Debug DLL not found - run the safe headless build first")

    if a.dry_run:
        log(f"DRY RUN: demo row patch={'already done' if already_patched else 'inject 5 knobs'}; "
            f"parity row {'EXISTS' if exists else f'insert id {PARITY_ID}'}; "
            f"workspace {'already hosts parity' if ws_done else 'insert Strategy1 ref'}; "
            f"copy DLL {src_dll} -> {dst_dll}")
        return

    backup(NT_DB)
    backup(WORKSPACE)
    backup(dst_dll)

    con = sqlite3.connect(NT_DB)
    con.text_factory = bytes
    try:
        if not already_patched:
            con.execute("UPDATE Strategies SET Userdata=? WHERE Id=?",
                        (demo_ud.encode("utf-16-le"), NOISE_ID))
            log("db: demo NOISE row patched with explicit in-range knob values (behaviour unchanged)")
        if not exists:
            con.execute("INSERT INTO Strategies (Id, Category, Classname, IsReplay, "
                        "IsResetOnNewTradingDay, IsTerminal, Name, ServerId, Template, Userdata, Workspace) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (PARITY_ID, row[0], row[1], row[2], row[3], row[4],
                         PARITY_NAME.encode(), row[5], row[6],
                         par_ud.encode("utf-16-le"), row[8]))
            con.execute("INSERT INTO Strategy2Account (Account, Strategy, Nr) VALUES (?,?,0)",
                        (ACCT_SIM101, PARITY_ID))
            con.execute("INSERT INTO Strategy2Instrument (Instrument, Strategy, Nr) VALUES (?,?,0)",
                        (MNQ_0926_ID, PARITY_ID))
            log(f"db: {PARITY_NAME} inserted as id {PARITY_ID} (Sim101, MNQ 09-26, crown config, "
                "gate OFF, HistFills ON, disabled)")
        con.commit()
    finally:
        con.close()

    if not ws_done:
        open(WORKSPACE, "w", encoding="utf-8", newline="").write(
            w.replace(WS_ANCHOR, WS_INSERT, 1))
        log("workspace: parity row hosted on the live NOISE chart (525-day MNQ 5m, EDGELOG RTH)")

    shutil.copy2(src_dll, dst_dll)
    log("dll: fresh build (with the 4 filter knobs + HistFills) copied into place")
    log("done - relaunch via C:\\EdgeLog\\nt_recover.ps1")


if __name__ == "__main__":
    main()
