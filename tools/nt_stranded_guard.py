"""tools/nt_stranded_guard.py -- a demo position no running strategy owns: phone within a minute, then protect it.

Owner GO 11-10 after the 11-04 loss: NinjaTrader lost its Simulation connection at 12:31 MST, disabled both
strategies, and their open trades sat with no strategy and no stop - ENGU-Q 1 NQ (-6,915) and NOISE 11 MNQ
(-38,978) took the demo from 51,038 to 790. nt_recover.ps1 correctly refused to enable a strategy over a
position it does not own ('HELD BACK for a person'), but nobody was told and nothing protected the trade.

Each pass (tools/nt_conn_poll.ps1 runs it every 20 s):
  stranded   a DEMO7240108 position whose leg's strategy is not Realtime, or is Realtime but says Flat
             (MNQ -> EdgeLogNOISE, NQ -> EdgeLogENGUQ1m)
  push       once it has been stranded STRANDED_SEC (40 s): one high-priority phone note + PAPER-NT8 inbox post
  protect    price from the NT 10s capture (NQ_10s.csv, <= 3 min old) is PROTECT_PTS against the entry
             -> flatten the demo account
  close      13:55-14:00 MST on a weekday (5 min before the close) -> flatten the demo account
The bridge can only flatten a whole account (POST /flatten), so protect/close fire only when EVERY open demo
position is stranded - a leg its strategy still manages is never closed under it; then the push says so.

Never any account but DEMO7240108 (1810769 is refused at the bridge too). Never restarts NinjaTrader, never
enables or disables a strategy. --whatif prints what it would do.

  python tools/nt_stranded_guard.py --once [--whatif]
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BRIDGE = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")
DEMO = "DEMO7240108"
LEG_OF_ROOT = {"MNQ": "EdgeLogNOISE", "NQ": "EdgeLogENGUQ1m"}
STRANDED_SEC = 40
PROTECT_PTS = 100.0               # disaster stop in NQ points (ENGU-Q's own stop ladder starts ~92 pts away)
PRICE_MAX_AGE_SEC = 180
CLOSE_WINDOW_MST = ((13, 55), (14, 0))
PHX = ZoneInfo("America/Phoenix")
STATE = os.environ.get("EDGELOG_STRANDED_STATE", r"C:\EdgeLog\nt_stranded_state.json")
PRICE_CSV = os.environ.get("EDGELOG_NQ_10S", r"C:\EdgeLog\ohlc\NQ_10s.csv")


def _get(path):
    with urllib.request.urlopen(BRIDGE + path, timeout=6) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(path):
    req = urllib.request.Request(BRIDGE + path, data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def root_of(instrument):
    return (str(instrument or "").split() or [""])[0]


def find_stranded(positions, strategies):
    """-> (stranded, managed): demo positions no Realtime strategy owns, and the ones a strategy does."""
    live = {s.get("name"): s for s in strategies or [] if s.get("account") == DEMO and s.get("state") == "Realtime"}
    stranded, managed = [], []
    for p in positions or []:
        if p.get("account") != DEMO or not p.get("qty"):
            continue
        leg = LEG_OF_ROOT.get(root_of(p.get("instrument")))
        s = live.get(leg)
        owned = s is not None and not str(s.get("position") or "").lower().startswith("flat")
        (managed if owned else stranded).append(dict(p, leg=leg))
    return stranded, managed


def key_of(p):
    return f"{p.get('instrument')}|{p.get('side')}|{p.get('qty')}|{p.get('avg_price')}"


def adverse_pts(p, price):
    """Points the position is against its entry (positive = losing)."""
    entry = float(p.get("avg_price") or 0)
    return (entry - price) if str(p.get("side")).lower() == "long" else (price - entry)


def last_price(path=PRICE_CSV, now=None):
    """(close, age_sec) of the newest NQ 10s bar, or (None, None)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            row = f.read().decode("utf-8", "ignore").strip().splitlines()[-1].split(",")
        ts, close = float(row[0]), float(row[4])
        return close, (now or time.time()) - ts
    except Exception:
        return None, None


def in_close_window(now_mst):
    if now_mst.weekday() >= 5:
        return False
    (h0, m0), (h1, m1) = CLOSE_WINDOW_MST
    return (h0, m0) <= (now_mst.hour, now_mst.minute) < (h1, m1)


def decide(stranded, managed, state, now, price=None, price_age=None, now_mst=None):
    """Pure: -> (actions, new_state). actions = list of ("push", title, text) / ("flatten", reason)."""
    acts, seen = [], {}
    for p in stranded:
        k = key_of(p)
        rec = dict(state.get(k) or {"first": now, "pushed": False})
        seen[k] = rec
        age = now - rec["first"]
        what = f"{str(p.get('side')).lower()} {p.get('qty')} {root_of(p.get('instrument'))} @ {p.get('avg_price')}"
        if age >= STRANDED_SEC and not rec["pushed"]:
            rec["pushed"] = True
            acts.append(("push", f"NT demo 7240108: STRANDED {what}",
                         f"No running strategy manages this trade ({p.get('leg') or 'no leg'} is not running it) "
                         f"for {int(age)} s. The guard closes it if it moves {PROTECT_PTS:g} pts against the entry "
                         f"or at 13:55 MST."))
    reason = None
    if stranded and price is not None and price_age is not None and price_age <= PRICE_MAX_AGE_SEC:
        worst = max(stranded, key=lambda p: adverse_pts(p, price))
        if adverse_pts(worst, price) >= PROTECT_PTS:
            reason = f"protective stop: {adverse_pts(worst, price):.0f} pts against {key_of(worst)} (NQ {price:g})"
    if stranded and reason is None and now_mst is not None and in_close_window(now_mst):
        reason = "flat at the close (13:55 MST) - stranded position"
    if reason:
        if managed:
            k = "blocked|" + reason[:20]
            if not (state.get(k) or {}).get("pushed"):
                seen[k] = {"first": now, "pushed": True}
                acts.append(("push", "NT demo 7240108: STRANDED - cannot close",
                             f"{reason}, but another leg's strategy holds a position and the bridge can only "
                             f"flatten the whole account. Close the stranded trade by hand."))
            else:
                seen[k] = state[k]
        else:
            acts.append(("flatten", reason))
    return acts, seen


def _load():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    try:
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception as e:
        print(f"state save failed: {e}")


def run_once(whatif=False):
    try:
        positions = _get("/positions").get("positions") or []
        strategies = _get("/strategies").get("strategies") or []
    except Exception as e:
        print(f"bridge not answering ({type(e).__name__}) - nothing to do")
        return 0
    stranded, managed = find_stranded(positions, strategies)
    price, age = last_price()
    now = time.time()
    acts, new = decide(stranded, managed, _load(), now, price, age, dt.datetime.now(PHX))
    for a in acts:
        if a[0] == "push":
            print(f"PUSH {a[1]} - {a[2]}")
            if not whatif:
                try:
                    from api import ntfy_push
                    ntfy_push.push(a[2], title=a[1], priority="high")
                except Exception as e:
                    print(f"push failed: {e}")
                os.system(f'"{sys.executable}" "{os.path.join(ROOT, "tools", "chat_inbox.py")}" post '
                          f'--from NT-CONNPOLL PAPER-NT8 "{a[1]}: {a[2]}"')
        else:
            print(f"FLATTEN {DEMO} - {a[1]}")
            if not whatif:
                try:
                    res = _post(f"/flatten?account={DEMO}")
                except Exception as e:
                    res = {"error": str(e)}
                print(f"  -> {res}")
                try:
                    from api import ntfy_push
                    ntfy_push.push(f"{a[1]}. Bridge said: {res}", title="NT demo 7240108: stranded trade CLOSED",
                                   priority="high")
                except Exception:
                    pass
    if not whatif:
        _save(new)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--whatif", action="store_true")
    a = ap.parse_args(argv)
    return run_once(a.whatif)


if __name__ == "__main__":
    sys.exit(main())
