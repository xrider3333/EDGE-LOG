r"""Quarterly futures ROLL for the NinjaTrader paper strategies -- unattended.

WHY THIS EXISTS (2026-09-15). NinjaTrader asked the owner "rolling over futures will update
the expiry instrument list and windows using the open workspaces". Clicking Yes moved the
charts it had open, and with them EdgeLogNOISE (restarted live on MNQ 12-26 at 06:18), but
EdgeLogENGUQ1m stayed on NQ 09-26 -- a contract that expires that Friday, with most of the
volume already gone to December. Nothing on this box noticed. Owner: "roll the strategies
after close. make that automatic so it dont happen again".

WHAT A ROLL IS HERE. A strategy's contract lives in three places, and all three have to
move together (the map is from tools/nt_reconfig.py, learned the hard way on 2026-08-16):
  * the WORKSPACE chart series each strategy is hosted on (<Instrument>/<Label>) -- at boot
    the chart recreates the strategy on the chart's instrument, so this is the real lever;
  * Strategies.Userdata in NinjaTrader.sqlite (<InstrumentOrInstrumentList>) -- the master
    record NinjaTrader deserializes;
  * Strategy2Instrument -- a derived index, repointed so the two stores never disagree.
Every other chart in the workspace on an old contract moves too, the same thing
NinjaTrader's own roll dialog does.

WHEN IT ACTS -- all of these, or it changes nothing:
  1. a roll is DUE: something references a quarterly NQ/MNQ/ES/MES contract older than the
     front month, where the front month flips 8 days before the 3rd-Friday expiry (the CME
     equity roll date, and the same rule the OHLC capture add-on already uses);
  2. the market is SHUT: inside the 17:00-18:00 ET daily halt (Mon-Thu), or from Friday's
     17:00 ET close to Sunday 17:30 ET -- ENGU-Q trades the 24h tape, so "after the 16:00
     cash close" is not flat time for it;
  3. nothing is OPEN: no position and no working order on any of those roots, in any account.
     A roll that finds a position DEFERS and pages; it never closes anything.

HOW. Pause the recover watchdog (C:\EdgeLog\nt_recover.PAUSE) so it cannot relaunch
NinjaTrader mid-edit -> ask NinjaTrader for a CLEAN exit through the bridge (that saves the
workspace, so a roll made by hand in the UI earlier is kept) -> back up the workspace and the
database -> edit -> un-pause -> run nt_recover.ps1 (log in, connect, enable the roster) ->
verify every running strategy is Realtime on the new contract -> page the result.

Run:  python tools/nt_rollover.py                # report only: what is due, would it act
      python tools/nt_rollover.py --apply        # act (the scheduled task runs this)
      python tools/nt_rollover.py --apply --ignore-window   # owner-directed, market shut
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOTS = ("NQ", "MNQ", "ES", "MES")
QUARTERS = (3, 6, 9, 12)
NT_HOME = os.path.join(os.path.expanduser("~"), "Documents", "NinjaTrader 8")
WORKSPACES = os.path.join(NT_HOME, "workspaces")
NT_DB = os.path.join(NT_HOME, "db", "NinjaTrader.sqlite")
BRIDGE = "http://127.0.0.1:8391"
EDGELOG = r"C:\EdgeLog"
PAUSE_FILE = os.path.join(EDGELOG, "nt_recover.PAUSE")
RECOVER = os.path.join(EDGELOG, "nt_recover.ps1")
LOG_PATH = os.path.join(EDGELOG, "nt_rollover.log")
BACKUP_ROOT = os.path.join(EDGELOG, "_ntbackup")
TICKS_EPOCH = dt.datetime(1, 1, 1)
CONTRACT_RE = re.compile(r"\b(" + "|".join(ROOTS) + r") (\d{2})-(\d{2})\b")


# ── contract calendar ──────────────────────────────────────────────────────────────
def third_friday(year, month):
    d = dt.date(year, month, 15)                     # the 15th..21st holds the 3rd Friday
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def roll_date(year, month):
    """First day the NEXT quarterly contract is the front month."""
    return third_friday(year, month) - dt.timedelta(days=8)


def front_month(today):
    """(year, month) of the contract to trade on `today` (a date, New York)."""
    y = today.year
    for _ in range(3):
        for m in QUARTERS:
            if today < roll_date(y, m):
                return (y, m)
        y += 1
    raise AssertionError("unreachable")


def label(root, ym):
    return f"{root} {ym[1]:02d}-{ym[0] % 100:02d}"


def parse_contract(text):
    """'NQ 09-26' -> ('NQ', (2026, 9)); None for anything that is not a quarterly contract."""
    m = CONTRACT_RE.search(text or "")
    if not m or int(m.group(2)) not in QUARTERS:
        return None
    return m.group(1), (2000 + int(m.group(3)), int(m.group(2)))


def stale_contracts(text, target):
    """Every distinct old quarterly contract in `text` that should become `target`.
    Never rolls BACKWARD: a contract already at or beyond the front month is left alone."""
    out = set()
    for m in CONTRACT_RE.finditer(text or ""):
        c = parse_contract(m.group(0))
        if c and c[1] < target:
            out.add(m.group(0))
    return sorted(out)


# ── when it is safe ────────────────────────────────────────────────────────────────
def market_shut(now_et):
    """Inside the CME equity-index halt, or the weekend. Minutes are kept clear of both
    edges: the watchdog needs time to bring strategies back before the 18:00 reopen."""
    wd, t = now_et.weekday(), now_et.time()
    halt = dt.time(17, 1) <= t <= dt.time(17, 40)
    if wd <= 3:                                        # Mon-Thu: the daily halt only
        return halt
    if wd == 4:                                        # Friday: from the weekly close
        return t >= dt.time(17, 1)
    if wd == 5:
        return True
    return t <= dt.time(17, 30)                        # Sunday, before the 18:00 open


# ── plumbing ───────────────────────────────────────────────────────────────────────
def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def page(title, msg):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log(f"(no NTFY_TOPIC, push skipped) {title}: {msg}")
        return
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
                                     headers={"Title": title, "Priority": "high"})
        urllib.request.urlopen(req, timeout=8).read()
    except Exception as e:
        log(f"push failed: {type(e).__name__}: {e}")


def bridge(path, post=False, timeout=8):
    req = urllib.request.Request(BRIDGE + path, data=b"" if post else None,
                                 method="POST" if post else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def bridge_up():
    try:
        bridge("/health", timeout=4)
        return True
    except Exception:
        return False


def nt_running():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "@(Get-Process NinjaTrader -ErrorAction SilentlyContinue).Count"],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    return out not in ("", "0")


def workspace_files():
    return [p for p in glob.glob(os.path.join(WORKSPACES, "*.xml"))
            if os.path.basename(p) != "_Workspaces.xml"]


def read_db_copy():
    """Read NinjaTrader's database from a COPY: it is open (and locked) while NT runs."""
    tmp = os.path.join(tempfile.gettempdir(), "nt_rollover_db.sqlite")
    shutil.copy2(NT_DB, tmp)
    return tmp


def master_ids(con, root):
    """ALL master-instrument ids named `root`: NinjaTrader's database carries duplicates
    (two MNQ masters on this box), and only one of them holds the contract rows."""
    return [r[0] for r in con.execute("SELECT Id FROM MasterInstruments WHERE Name=?", (root,))]


def instrument_id(con, root, ym):
    """Instruments.Id for a contract. Expiry is .NET ticks of the 1st of the contract month."""
    mids = master_ids(con, root)
    ticks = int((dt.datetime(ym[0], ym[1], 1) - TICKS_EPOCH).total_seconds()) * 10_000_000
    for mid in mids:
        row = con.execute("SELECT Id FROM Instruments WHERE MasterInstrument=? AND Expiry=?",
                          (mid, ticks)).fetchone()
        if row:
            return row[0]
    return None


def db_strategies(path):
    """[(id, name, userdata_text)] for the live (non-terminal) strategy records."""
    con = sqlite3.connect(path)
    con.text_factory = bytes
    try:
        rows = con.execute("SELECT Id, Name, Userdata FROM Strategies WHERE IsTerminal=0").fetchall()
        return [(r[0], r[1].decode(errors="replace"), (r[2] or b"").decode("utf-16-le", errors="replace"))
                for r in rows]
    finally:
        con.close()


# ── what is due ────────────────────────────────────────────────────────────────────
def survey(target_ym):
    """Every stale contract this box still references, by where it lives."""
    found = {"workspace": {}, "db": {}, "live": {}}
    for ws in workspace_files():
        s = open(ws, encoding="utf-8", newline="").read()
        tags = "".join(re.findall(r"<(?:Instrument|Label)>[^<]*</(?:Instrument|Label)>", s))
        st = stale_contracts(tags, target_ym)
        if st:
            found["workspace"][os.path.basename(ws)] = st
    for sid, name, ud in db_strategies(read_db_copy()):
        insts = re.findall(r"&lt;InstrumentOrInstrumentList&gt;([^&]*)", ud)
        st = stale_contracts(" ".join(insts), target_ym)
        if st:
            found["db"][name] = st
    if bridge_up():
        for x in bridge("/strategies").get("strategies", []):
            st = stale_contracts(x.get("instrument", ""), target_ym)
            if st:
                found["live"][x.get("name")] = st
    return found


def open_exposure():
    """Positions or working orders on any rolled root, in any account. None = could not tell."""
    if not bridge_up():
        return None
    bad = []
    for p in bridge("/positions").get("positions", []):
        if (parse_contract(p.get("instrument", "")) or ("",))[0] in ROOTS:
            bad.append(f"position {p.get('account')} {p.get('instrument')} {p.get('side')} {p.get('qty')}")
    for o in bridge("/orders").get("orders", []):
        if (parse_contract(o.get("instrument", "")) or ("",))[0] in ROOTS:
            bad.append(f"working order {o.get('account')} {o.get('instrument')} {o.get('name')} {o.get('state')}")
    for x in bridge("/strategies").get("strategies", []):
        if not str(x.get("position", "Flat")).startswith("Flat"):
            bad.append(f"strategy {x.get('name')} holds {x.get('position')}")
    return bad


# ── the edit ───────────────────────────────────────────────────────────────────────
def roll_text_tags(s, target_ym):
    """Replace old contracts inside <Instrument>/<Label> elements only. Returns (new, n)."""
    n = 0

    def fix(m):
        nonlocal n
        inner = m.group(2)
        c = parse_contract(inner)
        if not c or c[1] >= target_ym:
            return m.group(0)
        old = label(c[0], c[1])
        n += 1
        return m.group(1) + inner.replace(old, label(c[0], target_ym)) + m.group(3)

    out = re.sub(r"(<(?:Instrument|Label)>)([^<]*)(</(?:Instrument|Label)>)", fix, s)
    return out, n


def roll_userdata(ud, target_ym):
    n = 0

    def fix(m):
        nonlocal n
        c = parse_contract(m.group(2))
        if not c or c[1] >= target_ym:
            return m.group(0)
        n += 1
        return m.group(1) + m.group(2).replace(label(c[0], c[1]), label(c[0], target_ym))

    out = re.sub(r"(&lt;InstrumentOrInstrumentList&gt;)([^&]*)", fix, ud)
    return out, n


def apply_edits(target_ym, backup_dir):
    for ws in workspace_files():
        s = open(ws, encoding="utf-8", newline="").read()
        s2, n = roll_text_tags(s, target_ym)
        if n:
            shutil.copy2(ws, os.path.join(backup_dir, os.path.basename(ws)))
            open(ws, "w", encoding="utf-8", newline="").write(s2)
            log(f"workspace {os.path.basename(ws)}: {n} chart/instrument tag(s) rolled")
    shutil.copy2(NT_DB, os.path.join(backup_dir, "NinjaTrader.sqlite"))
    con = sqlite3.connect(NT_DB)
    try:
        con.text_factory = bytes
        rows = con.execute("SELECT Id, Name, Userdata FROM Strategies WHERE IsTerminal=0").fetchall()
        con.text_factory = str
        for sid, name, raw in rows:
            ud = (raw or b"").decode("utf-16-le", errors="strict") if raw else ""
            ud2, n = roll_userdata(ud, target_ym)
            if not n:
                continue
            insts = [parse_contract(x) for x in re.findall(r"&lt;InstrumentOrInstrumentList&gt;([^&]*)", ud)]
            con.execute("UPDATE Strategies SET Userdata=? WHERE Id=?", (ud2.encode("utf-16-le"), sid))
            for c in {c for c in insts if c and c[1] < target_ym}:
                old_id, new_id = instrument_id(con, c[0], c[1]), instrument_id(con, c[0], target_ym)
                if not (old_id and new_id):
                    raise SystemExit(f"no instrument row for {label(c[0], c[1])} or "
                                     f"{label(c[0], target_ym)} - refusing a half roll")
                con.execute("UPDATE Strategy2Instrument SET Instrument=? WHERE Strategy=? AND Instrument=?",
                            (new_id, sid, old_id))
            log(f"db: {name.decode(errors='replace') if isinstance(name, bytes) else name} -> {n} instrument field(s) rolled")
        con.commit()
    finally:
        con.close()


def stop_nt_cleanly():
    try:
        bridge("/shutdown", post=True, timeout=8)
        log("asked NinjaTrader for a clean exit (saves the workspace)")
    except Exception as e:
        log(f"clean exit request failed ({type(e).__name__}) -- will force")
    for _ in range(45):
        if not nt_running():
            log("NinjaTrader exited")
            return
        time.sleep(2)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Stop-Process -Name NinjaTrader -Force -ErrorAction SilentlyContinue"],
                   capture_output=True, timeout=60)
    time.sleep(6)
    log("NinjaTrader did not exit in 90s -- force-stopped (workspace NOT saved by NT)")


def relaunch_and_verify(target_ym):
    r = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", RECOVER],
                       capture_output=True, text=True, timeout=900)
    tail = (r.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
    log(f"nt_recover exit {r.returncode}: {tail[0]}")
    deadline = time.time() + 300
    last = []
    while time.time() < deadline:
        try:
            last = bridge("/strategies").get("strategies", [])
            if last and all(x.get("state") == "Realtime" for x in last):
                break
        except Exception:
            pass
        time.sleep(15)
    bad = []
    for x in last:
        c = parse_contract(x.get("instrument", ""))
        if x.get("state") != "Realtime":
            bad.append(f"{x.get('name')} is {x.get('state')}")
        if c and c[1] != target_ym:
            bad.append(f"{x.get('name')} still on {x.get('instrument')}")
    if not last:
        bad.append("no strategies reported by the bridge")
    return bad, last


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="act; without it, report only")
    ap.add_argument("--ignore-window", action="store_true",
                    help="skip the market-shut check (owner-directed; the flat check still applies)")
    a = ap.parse_args()

    now = dt.datetime.now(ET)
    target = front_month(now.date())
    found = survey(target)
    stale = {k: v for k, v in found.items() if v}
    if not stale:
        print(f"{now:%Y-%m-%d %H:%M} ET  front month {target[1]:02d}-{target[0] % 100:02d}: nothing to roll")
        return 0
    log(f"=== roll due -> {target[1]:02d}-{target[0] % 100:02d}: {json.dumps(stale)}")
    if not a.apply:
        log("report only (no --apply)")
        return 0
    if not (a.ignore_window or market_shut(now)):
        log("market open -- waiting for the halt/weekend window")
        return 0

    exposure = open_exposure()
    if exposure is None:
        log("bridge down -- cannot prove nothing is open; not rolling")
        page("NT roll deferred", "A futures roll is due but the NinjaTrader bridge is down, so "
             "flat could not be checked. Will retry at the next window.")
        return 3
    if exposure:
        log("NOT FLAT -- deferring: " + "; ".join(exposure))
        page("NT roll deferred", "A futures roll is due but something is open: "
             + "; ".join(exposure) + ". Nothing was changed; retrying at the next window.")
        return 3

    probe = sqlite3.connect(read_db_copy())
    try:
        roots = sorted({parse_contract(c)[0] for v in stale.values() for cs in v.values() for c in cs})
        missing = [label(r, target) for r in roots if instrument_id(probe, r, target) is None]
    finally:
        probe.close()
    if missing:
        log(f"target contract rows missing in NinjaTrader's database: {missing} -- not rolling")
        page("NT roll blocked", f"NinjaTrader has no instrument row for {missing}. Open "
             "NinjaTrader's Instruments window once so it downloads them.")
        return 4

    backup_dir = os.path.join(BACKUP_ROOT, f"rollover-{dt.datetime.now():%Y%m%d-%H%M%S}")
    os.makedirs(backup_dir, exist_ok=True)
    open(PAUSE_FILE, "w", encoding="utf-8").write(f"nt_rollover {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n")
    try:
        stop_nt_cleanly()
        apply_edits(target, backup_dir)
        log(f"backups in {backup_dir}")
    finally:
        try:
            os.remove(PAUSE_FILE)
        except FileNotFoundError:
            pass
    bad, live = relaunch_and_verify(target)
    summary = ", ".join(f"{x.get('name')} {x.get('state')} {x.get('instrument')}" for x in live)
    if bad:
        log("ROLL NEEDS ATTENTION: " + "; ".join(bad))
        page("NT roll needs attention", "; ".join(bad) + f". Backups: {backup_dir}")
        return 1
    log(f"ROLLED: {summary}")
    page("NT futures rolled", f"Now on {target[1]:02d}-{target[0] % 100:02d}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
