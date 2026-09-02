"""QQQ paper — publish tools/qqq_paper.py's signal-engine state to Firestore so the
web app can monitor it without anyone running anything by hand.

Nothing here places an order or touches a broker or real money — same guarantee as
tools/qqq_paper.py itself (see that module's docstring). This is a read-only
publisher on top of a pure signal engine.

Cadence (called from the runner's --watch loop, api/runner.py):
  * Mon-Fri 09:28-16:05 ET: re-sync roughly every ~2 minutes.
  * one FINAL run just after close (16:05-16:20 ET), once per trading day, so the
    day's last bar/trade is captured even if the intraday cadence's last tick landed
    a little before 16:00.
  * outside those windows: no-op, well under 1ms per check.

Mechanics per run:
  1. `python tools/qqq_paper.py --sync` as a SUBPROCESS (not an in-process import) —
     that engine pulls yfinance data and replays three strategy plugins; isolating it
     in its own process means a yfinance hiccup, a pandas exception, or even a hang
     (bounded by SYNC_TIMEOUT_S) can never take down the runner's watch loop, only
     this one job.
  2. Read back C:\\EdgeLog\\qqq_paper\\state.json + blotter.csv (written by that
     subprocess regardless of whether THIS run's own sync partially failed, so a
     transient yfinance error still lets us publish the prior sync's last-good state
     rather than going dark).
  3. Build ONE Firestore doc: generated_at, legs (state.json's own `legs` block,
     verbatim), the last MAX_BLOTTER_ROWS blotter rows (newest first), and a
     cumulative-P&L series per leg bucketed to one point per trading DAY (not per
     trade) — keeps the doc small regardless of how many trades pile up over time,
     well under Firestore's 1 MiB document cap.
  4. Write users/{uid}/meta/qqq_paper for every allow-listed uid, using the SAME
     Firestore client the runner already holds (q.db) — no separate credential path.

Every stage is wrapped so a bad sync, a missing file, or a Firestore hiccup is
logged and swallowed, never raised into the runner's main loop.
"""
import json
import os
import subprocess
import sys
import time
import datetime as _dt

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = r"C:\EdgeLog\qqq_paper\state.json"
BLOTTER_PATH = r"C:\EdgeLog\qqq_paper\blotter.csv"

MAX_BLOTTER_ROWS = 200
SYNC_TIMEOUT_S = 600            # subprocess hard timeout

_MARKET_OPEN = (9, 28)          # ET, inclusive
_MARKET_CLOSE = (16, 5)         # ET, inclusive — intraday cadence window ends here
_FINAL_WINDOW_END = (16, 20)    # ET — one last post-close run fires inside (16:05, 16:20]
_INTRADAY_INTERVAL_S = 110.0    # ~2 minutes, with a little slack so the outer 20s
                                 # throttle never causes a tick to be dropped entirely

_CHECK_FLOOR_S = 20.0           # cheapest possible no-op check, called every runner tick
_last_check_ts = 0.0
_last_sync_ts = 0.0
_last_final_date = None         # ET date string the post-close final run last fired for


def _log(msg):
    print(f"[qqq_paper] {msg}", flush=True)


def _et_now():
    try:
        from zoneinfo import ZoneInfo
        return pd.Timestamp.now(tz=ZoneInfo("America/New_York"))
    except Exception:
        return pd.Timestamp.now(tz="US/Eastern")


# ── subprocess sync ─────────────────────────────────────────────────────────────
def _run_sync():
    """Invoke `python tools/qqq_paper.py --sync` as a subprocess. Returns True on a
    clean exit; False (logged) on any failure — never raises."""
    script = os.path.join(ROOT, "tools", "qqq_paper.py")
    try:
        r = subprocess.run([sys.executable, script, "--sync"], cwd=ROOT,
                           capture_output=True, text=True, timeout=SYNC_TIMEOUT_S)
        tail = "\n".join((r.stdout or "").strip().splitlines()[-6:])
        if tail:
            _log(f"--sync output (tail): {tail}")
        if r.returncode != 0:
            err_tail = "\n".join((r.stderr or "").strip().splitlines()[-6:])
            _log(f"--sync exited {r.returncode}: {err_tail}")
            return False
        return True
    except subprocess.TimeoutExpired:
        _log(f"--sync timed out after {SYNC_TIMEOUT_S:g}s")
        return False
    except Exception as e:
        _log(f"--sync failed: {type(e).__name__}: {e}")
        return False


# ── build the Firestore doc from what's on disk ─────────────────────────────────
def _build_doc():
    """Read state.json + blotter.csv and build the Firestore doc. Returns None if
    state.json doesn't exist / isn't readable yet (no sync has ever succeeded)."""
    if not os.path.exists(STATE_PATH):
        return None
    try:
        with open(STATE_PATH) as f:
            state = json.load(f)
    except Exception as e:
        _log(f"state.json unreadable: {type(e).__name__}: {e}")
        return None

    legs = state.get("legs", {}) or {}

    blotter_rows = []
    cum_series = {}
    if os.path.exists(BLOTTER_PATH):
        try:
            df = pd.read_csv(BLOTTER_PATH)
            if len(df):
                df = df.sort_values(["entry_time", "leg"])
                df["_date"] = df["entry_time"].astype(str).str.slice(0, 10)
                for leg, g in df.groupby("leg"):
                    g = g.sort_values("entry_time")
                    daily = g.groupby("_date", as_index=False)["pnl_usd"].sum()
                    daily["cum_pnl"] = daily["pnl_usd"].cumsum()
                    cum_series[str(leg)] = [
                        {"date": str(r["_date"]), "cum_pnl": round(float(r["cum_pnl"]), 2)}
                        for _, r in daily.iterrows()
                    ]
                tail = df.tail(MAX_BLOTTER_ROWS).sort_values("entry_time", ascending=False)

                def _num(v):
                    try:
                        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v) == "":
                            return None
                        return float(v)
                    except Exception:
                        return None

                for _, r in tail.iterrows():
                    blotter_rows.append({
                        "leg": r.get("leg"),
                        "entry_time": r.get("entry_time"),
                        "exit_time": r.get("exit_time"),
                        "side": r.get("side"),
                        "shares": (int(r["shares"]) if pd.notna(r.get("shares")) else None),
                        "entry_px": _num(r.get("entry_px")),
                        "exit_px": _num(r.get("exit_px")),
                        "pnl_usd": _num(r.get("pnl_usd")),
                        "gate_prob": _num(r.get("gate_prob")),
                        "still_open_at_data_end": bool(r.get("still_open_at_data_end")),
                    })
        except Exception as e:
            _log(f"blotter read failed: {type(e).__name__}: {e}")

    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "state_generated_at": state.get("generated_at"),
        "notional_per_leg": state.get("notional_per_leg"),
        "slippage_per_share": state.get("slippage_per_share"),
        "legs": legs,
        "blotter": blotter_rows,
        "cum_pnl": cum_series,
    }


def _write_doc(db, uid, doc):
    from .util import json_safe
    safe = json_safe(doc)
    db.collection("users").document(uid).collection("meta").document("qqq_paper").set(safe)


# ── scheduling hook for the runner's watch loop ─────────────────────────────────
def maybe_run(q, *, force=False):
    """Cheap, throttled, exception-proof hook for the runner's watch loop — call this
    every tick. Actually runs the sync only inside market hours (~every 2 min) or once
    just after close; otherwise returns None in well under 1ms."""
    global _last_check_ts
    now_wall = time.time()
    if not force and (now_wall - _last_check_ts) < _CHECK_FLOOR_S:
        return None
    _last_check_ts = now_wall
    try:
        return _maybe_run_inner(q, force=force)
    except Exception as e:
        _log(f"maybe_run error: {type(e).__name__}: {e}")
        return None


def _maybe_run_inner(q, *, force=False):
    global _last_sync_ts, _last_final_date
    et_now = _et_now()
    reason = None
    if force:
        reason = "forced"
    elif et_now.weekday() < 5:
        hm = (et_now.hour, et_now.minute)
        if _MARKET_OPEN <= hm <= _MARKET_CLOSE:
            if (time.time() - _last_sync_ts) >= _INTRADAY_INTERVAL_S:
                reason = "intraday"
        elif _MARKET_CLOSE < hm <= _FINAL_WINDOW_END:
            today = et_now.date().isoformat()
            if _last_final_date != today:
                reason = "post-close final"

    if reason is None:
        return None

    _log(f"sync starting ({reason}, {et_now.strftime('%Y-%m-%d %H:%M')} ET)")
    ok = _run_sync()
    doc = _build_doc()
    if doc is None:
        _log("no state.json on disk — nothing to publish yet")
        # still advance the cadence clocks so a broken sync doesn't spin every tick
        _last_sync_ts = time.time()
        if reason == "post-close final":
            _last_final_date = et_now.date().isoformat()
        return {"ok": False, "reason": reason, "published": 0}

    n_pub = 0
    for uid in list(getattr(q, "allow", None) or []):
        try:
            _write_doc(q.db, uid, doc)
            n_pub += 1
        except Exception as e:
            _log(f"Firestore publish failed for uid: {type(e).__name__}: {e}")

    _last_sync_ts = time.time()
    if reason == "post-close final":
        _last_final_date = et_now.date().isoformat()

    _log(f"sync {'ok' if ok else 'ok(stale state — sync failed, republished last-good)'}, "
        f"published to {n_pub} uid(s), {len(doc.get('blotter', []))} blotter row(s), "
        f"legs: {', '.join(sorted(doc.get('legs', {}).keys())) or '(none)'}")
    return {"ok": ok, "reason": reason, "published": n_pub}


# ── manual driver: run once regardless of market hours (verification / smoke test) ──
def run_once_cli():
    """`python -m api.qqq_paper_publish --once --cred <sa.json> --allow-uid <uid>`
    Forces one sync + publish immediately, bypassing the market-hours gate — for
    verification without waiting for the window."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cred", required=True)
    ap.add_argument("--allow-uid", action="append", required=True)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = credentials.Certificate(a.cred)
    try:
        firebase_admin.initialize_app(cred)
    except ValueError:
        pass  # already initialized
    db = firestore.client()

    class _Q:
        pass
    q = _Q()
    q.db = db
    q.allow = a.allow_uid

    result = maybe_run(q, force=True)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    run_once_cli()
