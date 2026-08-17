"""Reconfigure a NinjaTrader grid strategy's instrument/quantity -- owner-directed.

WHY THIS TOOL EXISTS (2026-08-16). Moving EdgeLogNOISE from 1 full NQ contract to 10
micro contracts (MNQ) is what makes the ML gate's size dial real: hybrid sizes of
0.9x-1.5x round to nothing at one contract but become 9-15 micros at ten. The bridge
cannot change a strategy's instrument (NinjaScript fixes it at configure time), so the
change is made where NinjaTrader actually reads it: the workspace file, edited while
NinjaTrader is STOPPED, then relaunched through the same auto-recover used all night.

Owner authorization, verbatim, 2026-08-16: "yeah idc. you should have the abilty to do
650. build it in the mcp or brainstorm how else" -- after being told explicitly that
this raises the breaker's position limit and 10x-es the traded quantity (in micros;
notional stays ~1 NQ at baseline).

SAFETY POSTURE, unchanged by this tool:
  * The REAL account (1810769) is hard-locked in the bridge's compiled code; nothing
    here touches accounts at all.
  * The breaker limit change (5 -> 30 contracts) is expressed in MICROS: 30 micros =
    3 full NQ contracts, which is the engine's own 3x size cap. The dollar-loss
    breaker (max_daily_loss_usd) is untouched.
  * Everything is backed up first, logged loudly, and verified live afterwards.

Usage:
  python tools/nt_reconfig.py --noise-micros      # the one owner-approved recipe
  python tools/nt_reconfig.py --noise-micros --dry-run
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

WORKSPACE = r"C:\Users\xride\Documents\NinjaTrader 8\workspaces\Untitled 2.xml"
NT_DB = r"C:\Users\xride\Documents\NinjaTrader 8\db\NinjaTrader.sqlite"
BRIDGE_JSON = r"C:\EdgeLog\bridge.json"

# The live EdgeLogNOISE grid row and the contracts involved, resolved by hand 2026-08-16.
# The strategy id matches what NinjaTrader itself logs ("EdgeLogNOISE/386606468"), and the
# MNQ instrument row carries the IDENTICAL expiry ticks as the NQ 09-26 it replaces --
# same contract month, micro size. The first attempt at this switch edited the workspace
# XML and did nothing: every EdgeLogNOISE block in that file is a saved Strategy-Analyzer
# TEMPLATE. The grid's real store is the Strategies/Strategy2Instrument tables in
# NinjaTrader.sqlite.
NOISE_STRATEGY_ID = 386606468
NQ_0926_ID = 699839150764672
MNQ_0926_ID = 699839150767964          # same Expiry ticks (639238176000000000) as the NQ row
RECOVER = r"C:\EdgeLog\nt_recover.ps1"
BRIDGE = "http://127.0.0.1:8391"
PY = sys.executable
NT_CLI = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools\nt_bridge.py"


def log(m):
    print(f"{datetime.now().strftime('%H:%M:%S')}  {m}", flush=True)


def backup(path):
    dst = f"{path}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, dst)
    log(f"backup: {dst}")
    return dst


def stop_nt():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Stop-Process -Name NinjaTrader -Force -ErrorAction SilentlyContinue"],
                   capture_output=True)
    time.sleep(6)
    log("NinjaTrader stopped")


def get(path, timeout=8):
    with urllib.request.urlopen(BRIDGE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def edit_db_noise_micros(dry):
    """Repoint the LIVE grid strategy's instrument NQ 09-26 -> MNQ 09-26 in NinjaTrader's
    own database. One integer, NT stopped, db backed up by the caller. The strategy's
    parameters are not stored here (they come from the DLL's SetDefaults, which already
    carry the crowned config) -- quantity is set through the bridge after relaunch."""
    import sqlite3
    c = sqlite3.connect(NT_DB)
    try:
        row = c.execute("SELECT Instrument FROM Strategy2Instrument WHERE Strategy=?",
                        (NOISE_STRATEGY_ID,)).fetchone()
        if row is None:
            raise SystemExit(f"strategy {NOISE_STRATEGY_ID} not found in Strategy2Instrument - refusing")
        cur = int(row[0])
        if cur == MNQ_0926_ID:
            log("db: NOISE already mapped to MNQ 09-26")
            return
        if cur != NQ_0926_ID:
            raise SystemExit(f"NOISE maps to unexpected instrument {cur} - refusing to guess")
        if dry:
            log("DRY RUN: would repoint NOISE instrument NQ 09-26 -> MNQ 09-26")
            return
        c.execute("UPDATE Strategy2Instrument SET Instrument=? WHERE Strategy=?",
                  (MNQ_0926_ID, NOISE_STRATEGY_ID))
        c.commit()
        log("db: NOISE instrument repointed NQ 09-26 -> MNQ 09-26 (same expiry, micro size)")
    finally:
        c.close()


def set_qty_via_bridge(qty):
    """Qty is a live NinjaScript property (comes from SetDefaults=1 each boot), so it is
    set through the bridge's own sanctioned setparam path: disable -> write -> enable."""
    subprocess.run([PY, NT_CLI, "strategy", "disable", "--name", "EdgeLogNOISE", "--yes"],
                   capture_output=True, timeout=120)
    time.sleep(4)
    req = urllib.request.Request(
        BRIDGE + f"/strategy/setparam?name=EdgeLogNOISE&param=Qty&value={qty}",
        method="POST", data=b"")
    with urllib.request.urlopen(req, timeout=10) as r:
        log(f"setparam Qty={qty}: {r.read().decode()[:120]}")
    subprocess.run([PY, NT_CLI, "strategy", "enable", "--name", "EdgeLogNOISE", "--yes"],
                   capture_output=True, timeout=120)
    time.sleep(8)


def edit_workspace_noise_micros(dry):
    s = open(WORKSPACE, encoding="utf-8", newline="").read()
    occ = list(re.finditer(
        r"<InstrumentOrInstrumentList>NQ 09-26</InstrumentOrInstrumentList>", s))
    # the LAST such tag belongs to the EdgeLogNOISE grid block (verified by proximity
    # scan 2026-08-16: nearest preceding strategy ref is EdgeLogNOISE)
    if len(occ) != 2:
        raise SystemExit(f"expected 2 'NQ 09-26' strategy-instrument tags, found {len(occ)} - "
                         "workspace layout changed, refusing to guess")
    qtys = re.findall(r"<Qty>(\d+)</Qty>", s)
    if qtys.count("1") != 1:
        raise SystemExit(f"expected exactly one <Qty>1</Qty> (the NOISE block), found {qtys} - refusing")
    if dry:
        log("DRY RUN: would set NOISE -> MNQ 09-26, Qty 10")
        return
    i = occ[1].start()
    s = s[:i] + s[i:].replace(
        "<InstrumentOrInstrumentList>NQ 09-26</InstrumentOrInstrumentList>",
        "<InstrumentOrInstrumentList>MNQ 09-26</InstrumentOrInstrumentList>", 1)
    s = s.replace("<Qty>1</Qty>", "<Qty>10</Qty>", 1)
    open(WORKSPACE, "w", encoding="utf-8", newline="").write(s)
    log("workspace: EdgeLogNOISE -> MNQ 09-26, Qty 10")


def edit_bridge_limit(dry):
    s = open(BRIDGE_JSON, encoding="utf-8", newline="").read()
    if '"max_position_contracts": 30' in s:
        log("bridge.json: position limit already 30")
        return
    a = '"max_position_contracts": 5'
    if a not in s:
        raise SystemExit("bridge.json: expected max_position_contracts 5 - layout changed, refusing")
    if dry:
        log("DRY RUN: would raise max_position_contracts 5 -> 30 (micros; = 3 full NQ)")
        return
    s = s.replace(a, '"max_position_contracts": 30', 1)
    s = s.replace('"_margin_comment"',
                  '"_position_comment": "Raised 5 -> 30 on 2026-08-16 (owner-directed) when '
                  'NOISE moved to MICRO contracts: the gate sizes 9-15 micros per trade, and 30 '
                  'micros = 3 full NQ = the engine\'s own 3x size cap. Dollar-loss breaker '
                  'unchanged.",\n  "_margin_comment"', 1)
    open(BRIDGE_JSON, "w", encoding="utf-8", newline="").write(s)
    log("bridge.json: max_position_contracts 5 -> 30 (live-reloads within 10s)")


def relaunch_and_verify():
    log("relaunching via nt_recover.ps1 ...")
    r = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", RECOVER],
                       capture_output=True, text=True, timeout=420)
    tail = (r.stdout or "").strip().splitlines()[-1:]
    log(f"recover: {' / '.join(tail)} (exit {r.returncode})")
    subprocess.run([PY, NT_CLI, "strategy", "enable", "--name", "EdgeLogENGUQ1m", "--yes"],
                   capture_output=True, timeout=120)
    time.sleep(12)

    ok = True
    strats = {x.get("name"): x for x in get("/strategies").get("strategies", [])}
    nz = strats.get("EdgeLogNOISE") or {}
    log(f"EdgeLogNOISE: state={nz.get('state')} instrument={nz.get('instrument')}")
    if "MNQ" not in str(nz.get("instrument", "")):
        ok = False
    if ok:
        set_qty_via_bridge(10)
        strats = {x.get("name"): x for x in get("/strategies").get("strategies", [])}
        nz = strats.get("EdgeLogNOISE") or {}
        log(f"EdgeLogNOISE after Qty set: state={nz.get('state')} instrument={nz.get('instrument')}")
        if nz.get("state") != "Realtime":
            ok = False
    p = {x["name"]: x["value"] for x in get("/strategy/params?name=EdgeLogNOISE").get("params", [])}
    log(f"params: Qty={p.get('Qty')} Lookback={p.get('Lookback')} gate={p.get('GateEnabled')}")
    if p.get("Qty") != "10" or p.get("Lookback") != "44":
        ok = False
    eq = strats.get("EdgeLogENGUQ1m") or {}
    log(f"EdgeLogENGUQ1m: state={eq.get('state')} position={eq.get('position')}")
    try:
        lim = get("/risk").get("limits", {}).get("max_position_contracts")
        log(f"breaker position limit now: {lim}")
        if int(lim or 0) < 30:
            ok = False
    except Exception as e:
        log(f"risk read: {e}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--noise-micros", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.noise_micros:
        ap.error("nothing to do - pass --noise-micros")

    if not a.dry_run:
        backup(NT_DB)
        backup(BRIDGE_JSON)
        stop_nt()
    edit_db_noise_micros(a.dry_run)
    edit_bridge_limit(a.dry_run)
    if a.dry_run:
        log("dry run complete - nothing changed")
        return 0
    ok = relaunch_and_verify()
    log("RESULT: " + ("PASS - NOISE is on 10 micros with the gate live" if ok
                      else "INCOMPLETE - read the lines above"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
