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
    """Switch the LIVE grid strategy to MNQ x10 in NinjaTrader's own database.

    Hard-won map of where this actually lives (2026-08-16, three failed attempts deep):
      * the workspace XML copies of EdgeLogNOISE are Strategy-Analyzer TEMPLATES (inert);
      * the Strategy2Instrument row is a DERIVED index -- editing it alone gets
        overwritten at boot (observed 19:13);
      * the MASTER record is Strategies.Userdata: UTF-16LE text holding entity-escaped
        strategy XML. It provably carries tonight's crowned params (Lookback 44 etc.),
        which is how we know it is the live one. NT deserializes THIS at boot and
        re-syncs everything else from it.
    So: edit Userdata (instrument, Qty, DaysToLoad), and repoint Strategy2Instrument to
    match so the two stores never disagree."""
    import sqlite3
    c = sqlite3.connect(NT_DB)
    c.text_factory = bytes
    try:
        row = c.execute("SELECT Userdata FROM Strategies WHERE Id=?",
                        (NOISE_STRATEGY_ID,)).fetchone()
        if row is None or not row[0]:
            raise SystemExit(f"strategy {NOISE_STRATEGY_ID} has no Userdata - refusing")
        s = row[0].decode("utf-16-le")
        subs = [
            ("&lt;InstrumentOrInstrumentList&gt;NQ 09-26",
             "&lt;InstrumentOrInstrumentList&gt;MNQ 09-26"),
            ("&lt;Qty&gt;1&lt;/Qty&gt;", "&lt;Qty&gt;10&lt;/Qty&gt;"),
            ("&lt;DaysToLoad&gt;5&lt;/DaysToLoad&gt;", "&lt;DaysToLoad&gt;90&lt;/DaysToLoad&gt;"),
        ]
        done = []
        for a, b in subs:
            n = s.count(a)
            if n > 1:
                raise SystemExit(f"ambiguous ({n}x): {a[:50]} - refusing")
            if n == 1:
                if not dry:
                    s = s.replace(a, b, 1)
                done.append(a[4:40])
        # sanity: the record must carry the crowned params, or it is not the live row
        if "&lt;Lookback&gt;44" not in s:
            raise SystemExit("Userdata does not carry Lookback 44 - wrong record, refusing")
        if dry:
            log(f"DRY RUN: would edit Userdata fields: {done}")
            return
        c.execute("UPDATE Strategies SET Userdata=? WHERE Id=?",
                  (s.encode("utf-16-le"), NOISE_STRATEGY_ID))
        c.execute("UPDATE Strategy2Instrument SET Instrument=? WHERE Strategy=? AND Instrument=?",
                  (MNQ_0926_ID, NOISE_STRATEGY_ID, NQ_0926_ID))
        c.commit()
        log(f"db: Userdata edited ({done}) + instrument index repointed to MNQ 09-26")
    finally:
        c.close()


def edit_recycle_rails(dry):
    """Make room for RECYCLE sizing WITHOUT weakening the dollar guardrail.

    Owner 2026-08-16: "make sure the guardrails dont mess this up". Working the numbers
    through is what picked this shape, and it reversed the obvious approach.

    Recycle multiplies position size by 3.85 on the live NOISE leg. The naive move is to
    keep base Qty at 10 micros and scale every rail to fit -- but that means ~38 micros a
    trade ($77/point), at which the $1,500 daily-loss breaker fires after only 20 adverse
    points. NQ covers 20 points in an hour, so the breaker would flatten AND DISABLE every
    strategy on an ordinary day, killing the forward test silently. Raising the dollar rail
    to compensate would have meant loosening the one guardrail denominated in real money.

    Dropping BASE Qty to 3 instead gets the same experiment for a third of the exposure:
    recycle's scaling is a ratio, so the equity curve shape -- and therefore everything the
    test is trying to learn -- is identical either way. At Qty 3 the leg averages ~11.5
    micros (~1.2 NQ, close to where it has been all along) and the untouched $1,500 breaker
    trips at ~65 adverse points, essentially the 75 points it originally meant.

    So the ONLY rail that moves is the contract count, 30 -> 40, because the worst case
    (3x per-trade cap x 3.85 recycle x 3 base) is 35 contracts. max_daily_loss_usd is
    deliberately NOT in this list.

    DEMO account throughout; the live account is refused in compiled bridge code regardless.
    Everything here is reversible in C:\\EdgeLog\\bridge.json -- re-read within 10s.
    """
    s = open(BRIDGE_JSON, encoding="utf-8", newline="").read()
    changed = []
    for a, b, note in [
        ('"max_qty": 30', '"max_qty": 40', "max_qty 30->40"),
        ('"max_position_contracts": 30', '"max_position_contracts": 40', "position 30->40"),
    ]:
        if b in s:
            continue
        if a not in s:
            raise SystemExit(f"bridge.json: expected {a} - refusing to guess")
        if not dry:
            s = s.replace(a, b, 1)
        changed.append(note)
    if not changed:
        log("bridge.json: rails already scaled for recycle")
        return
    if dry:
        log(f"DRY RUN: would change {changed}")
        return
    open(BRIDGE_JSON, "w", encoding="utf-8", newline="").write(s)
    log(f"bridge.json: {changed} (live-reloads within 10s)")


ENGUQ_STRATEGY_ID = 386606474          # verified against NinjaTrader.sqlite Strategies
RTH_TEMPLATE = "EDGELOG RTH 0930-1600"
ETH_TEMPLATE = "CME US Index Futures ETH"   # already present on disk and used elsewhere
# Run #226's clock-scaled lookbacks. Only the three TIME lookbacks change: the 24h tape has
# ~3.54x as many bars per session, so a 390-bar EMA on RTH is a 1380-bar EMA on ETH. Every
# other knob is dimensionless (ATR multiples, R multiples) and is identical in both.
ENGUQ_ETH_PARAMS = {"EmaLen": 1380, "TlLen": 170, "AtrLen": 106}


def edit_enguq_eth(dry):
    """Move the ENGU-Q chart to the 24-hour session (workspace) -- the half that cannot be
    done through the bridge.

    WHY (owner 2026-08-17: "ENGUQ is suppose to be ETH right?"). The NinjaTrader port runs
    the RTH config on an RTH chart, but this project certified the ETH variant (#226) as the
    primary deployment candidate and recorded that the RTH champion gives back $178,340 once
    a real overnight stop is priced in. Two things therefore have to move together:

      * the CHART's session template, here -- lookbacks scaled for a 24h tape are meaningless
        on day-session bars, and vice versa; and
      * the three time lookbacks, set through the bridge (see main()).

    Changing only one of the two is worse than changing neither, so this recipe does both or
    reports what it could not do.
    """
    s = open(WORKSPACE, encoding="utf-8", newline="").read()
    i = s.find(">" + str(ENGUQ_STRATEGY_ID) + "<")
    if i < 0:
        raise SystemExit(f"ENGU-Q strategy {ENGUQ_STRATEGY_ID} not found in the workspace")
    a = max(0, i - 9000)
    seg = s[a:i]
    tag = f"<TradingHoursSerializable>{RTH_TEMPLATE}</TradingHoursSerializable>"
    if f"<TradingHoursSerializable>{ETH_TEMPLATE}</TradingHoursSerializable>" in seg and tag not in seg:
        log("workspace: ENGU-Q chart already on the 24h session")
        return
    if seg.count(tag) != 1:
        raise SystemExit(f"expected exactly one session tag on the ENGU-Q chart "
                         f"(found {seg.count(tag)}) - refusing to guess")
    if dry:
        log(f"DRY RUN: would move ENGU-Q chart {RTH_TEMPLATE} -> {ETH_TEMPLATE}")
        return
    seg2 = seg.replace(tag, f"<TradingHoursSerializable>{ETH_TEMPLATE}</TradingHoursSerializable>", 1)
    open(WORKSPACE, "w", encoding="utf-8", newline="").write(s[:a] + seg2 + s[i:])
    log(f"workspace: ENGU-Q chart -> {ETH_TEMPLATE}")


def edit_chart_series(dry):
    """THE ACTUAL LEVER (found 2026-08-16 after the db-only edit reverted at boot):
    EdgeLogNOISE is not a standalone grid strategy -- it is ATTACHED TO A CHART
    (workspace: <Strategies><Strategy0>386606468</Strategy0> inside a DataSeries block,
    chart id bf857ca7...). At boot the chart recreates the strategy bound to the CHART'S
    instrument and NT re-persists everything else from that, which is why editing
    Userdata/Strategy2Instrument alone kept reverting. Changing the chart's series to
    MNQ is what the owner would do in the UI (chart -> Data Series -> Instrument)."""
    s = open(WORKSPACE, encoding="utf-8", newline="").read()
    i = s.find("386606468")
    if i < 0:
        raise SystemExit("strategy id not found in workspace - layout changed, refusing")
    # the hosting chart's series block sits just before the Strategy0 tag
    a = max(0, i - 9000)
    seg = s[a:i]
    lab = "<Label>NQ 09-26</Label>"
    ins = "<Instrument>NQ 09-26</Instrument>"
    nl, ni = seg.count(lab), seg.count(ins)
    if "MNQ 09-26" in seg and (nl + ni) == 0:
        log("workspace chart: already MNQ")
        return
    if nl != 1 or ni != 1:
        raise SystemExit(f"expected exactly one Label/Instrument pair near the strategy "
                         f"(got {nl}/{ni}) - refusing to guess")
    if dry:
        log("DRY RUN: would switch the hosting chart's series NQ 09-26 -> MNQ 09-26")
        return
    seg2 = seg.replace(lab, "<Label>MNQ 09-26</Label>", 1)
    seg2 = seg2.replace(ins, "<Instrument>MNQ 09-26</Instrument>", 1)
    open(WORKSPACE, "w", encoding="utf-8", newline="").write(s[:a] + seg2 + s[i:])
    log("workspace chart: NOISE's hosting chart series -> MNQ 09-26")


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
    """Re-express BOTH contract-count rails in MICRO terms (owner-directed 2026-08-16).
    30 micros = 3 full NQ = the engine's own 3x size cap; the DOLLAR-loss breaker is
    deliberately untouched -- dollars are unit-blind and stay the real guardrail.
      max_position_contracts  5 -> 30   (the breaker's account-level position check)
      max_qty                 3 -> 30   (the enable-path per-order size gate -- it
                                         correctly refused Qty 10 at the old value,
                                         which is how this line earned its edit)"""
    s = open(BRIDGE_JSON, encoding="utf-8", newline="").read()
    changed = []
    for a, b, note in [
        ('"max_position_contracts": 5', '"max_position_contracts": 30', "position 5->30"),
        ('"max_qty": 3', '"max_qty": 30', "max_qty 3->30"),
    ]:
        if b in s:
            continue
        if a not in s:
            raise SystemExit(f"bridge.json: expected {a} - layout changed, refusing")
        if not dry:
            s = s.replace(a, b, 1)
        changed.append(note)
    if not changed:
        log("bridge.json: limits already in micro terms")
        return
    if dry:
        log(f"DRY RUN: would change {changed}")
        return
    if '"_position_comment"' not in s:
        s = s.replace('"_margin_comment"',
                      '"_position_comment": "Contract-count rails re-expressed in MICROS on '
                      '2026-08-16 (owner-directed) when NOISE moved to MNQ: the gate sizes 9-15 '
                      'micros per trade; 30 micros = 3 full NQ = the engine\'s 3x size cap. The '
                      'dollar-loss breaker is unchanged and remains the real guardrail.",\n  '
                      '"_margin_comment"', 1)
    open(BRIDGE_JSON, "w", encoding="utf-8", newline="").write(s)
    log(f"bridge.json: {changed} (live-reloads within 10s)")


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
    p = {x["name"]: x["value"] for x in get("/strategy/params?name=EdgeLogNOISE").get("params", [])}
    if ok and p.get("Qty") != "10":
        log("Qty did not come through Userdata - setting via the bridge")
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
    ap.add_argument("--enguq-eth", action="store_true",
                    help="move ENGU-Q to the 24h session + run #226's clock-scaled lookbacks")
    ap.add_argument("--recycle-rails", action="store_true",
                    help="re-scale the risk rails for recycle sizing (no NT restart)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.enguq_eth:
        # Chart session (workspace, needs NT stopped) + the three lookbacks (bridge).
        # Both or neither: ETH-scaled lookbacks on RTH bars are worse than leaving it alone.
        if a.dry_run:
            edit_enguq_eth(True)
            log("DRY RUN: would then set " + json.dumps(ENGUQ_ETH_PARAMS) + " via the bridge")
            return 0
        backup(WORKSPACE)
        stop_nt()
        edit_enguq_eth(False)
        log("relaunching via nt_recover.ps1 ...")
        r = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", RECOVER],
                           capture_output=True, text=True, timeout=420)
        log("recover: " + " / ".join((r.stdout or "").strip().splitlines()[-1:]))
        # ENGU-Q is not in nt_recover's roster (it self-terminates outside market hours),
        # so it is enabled here explicitly -- disabled first so the params actually take.
        subprocess.run([PY, NT_CLI, "strategy", "disable", "--name", "EdgeLogENGUQ1m", "--yes"],
                       capture_output=True, timeout=120)
        time.sleep(4)
        for k, v in ENGUQ_ETH_PARAMS.items():
            req = urllib.request.Request(
                BRIDGE + f"/strategy/setparam?name=EdgeLogENGUQ1m&param={k}&value={v}",
                method="POST", data=b"")
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    log(f"setparam {k}={v}: {resp.read().decode()[:90]}")
            except Exception as e:
                log(f"setparam {k} FAILED: {e}")
        subprocess.run([PY, NT_CLI, "strategy", "enable", "--name", "EdgeLogENGUQ1m", "--yes"],
                       capture_output=True, timeout=120)
        time.sleep(10)
        p = {x["name"]: x["value"] for x in
             get("/strategy/params?name=EdgeLogENGUQ1m").get("params", [])}
        st = {x.get("name"): x for x in get("/strategies").get("strategies", [])}
        eq = st.get("EdgeLogENGUQ1m") or {}
        log(f"EdgeLogENGUQ1m: state={eq.get('state')} instrument={eq.get('instrument')} "
            f"EmaLen={p.get('EmaLen')} TlLen={p.get('TlLen')} AtrLen={p.get('AtrLen')}")
        nz = st.get("EdgeLogNOISE") or {}
        log(f"EdgeLogNOISE (must still be live): state={nz.get('state')} "
            f"instrument={nz.get('instrument')}")
        ok = (str(p.get("EmaLen")) == "1380" and str(p.get("TlLen")) == "170"
              and str(p.get("AtrLen")) == "106" and eq.get("state") == "Realtime"
              and nz.get("state") == "Realtime")
        log("RESULT: " + ("PASS - ENGU-Q on the 24h session with #226 lookbacks"
                          if ok else "INCOMPLETE - read the lines above"))
        return 0 if ok else 1

    if a.recycle_rails and not a.noise_micros:
        if not a.dry_run:
            backup(BRIDGE_JSON)
        edit_recycle_rails(a.dry_run)
        # Base Qty 10 -> 3 so recycle lands near one-contract exposure (see the docstring
        # above: same experiment, a third of the dollars, dollar guardrail untouched).
        if a.dry_run:
            log("DRY RUN: would set EdgeLogNOISE Qty 10 -> 3 via the bridge")
            return 0
        set_qty_via_bridge(3)
        p = {x["name"]: x["value"] for x in
             get("/strategy/params?name=EdgeLogNOISE").get("params", [])}
        st = {x.get("name"): x for x in get("/strategies").get("strategies", [])}
        nz = st.get("EdgeLogNOISE") or {}
        log(f"EdgeLogNOISE: Qty={p.get('Qty')} state={nz.get('state')} "
            f"instrument={nz.get('instrument')}")
        try:
            lim = get("/risk").get("limits", {})
            log(f"rails now: position={lim.get('max_position_contracts')} "
                f"qty={lim.get('max_qty')} daily_loss=${lim.get('max_daily_loss_usd')}")
        except Exception as e:
            log(f"risk read: {e}")
        ok = (p.get("Qty") == "3" and nz.get("state") == "Realtime"
              and "MNQ" in str(nz.get("instrument", "")))
        log("RESULT: " + ("PASS - live leg on recycle sizing at base 3 micros" if ok
                          else "INCOMPLETE - read the lines above"))
        return 0 if ok else 1
    if not a.noise_micros:
        ap.error("nothing to do - pass --noise-micros, --recycle-rails or --enguq-eth")

    if not a.dry_run:
        backup(NT_DB)
        backup(WORKSPACE)
        backup(BRIDGE_JSON)
        stop_nt()
    edit_chart_series(a.dry_run)     # the real lever -- the chart recreates the strategy
    edit_db_noise_micros(a.dry_run)  # kept consistent so no store disagrees at boot
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
