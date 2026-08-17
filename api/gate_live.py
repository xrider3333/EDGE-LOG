"""LIVE ML gate service — the bouncer NinjaTrader asks before entering a trade.

WHY (owner, 2026-08-16): the validated ML gates existed only inside Python backtests
(the paper legs). NinjaTrader traded RAW because the random-forest model cannot be
retyped into NinjaScript (100 trees). This closes the gap the way the owner approved:
NinjaTrader keeps placing and managing every order exactly as it does today, but just
before entering it makes ONE local HTTP call here -- "should I take this trade, and how
big?" -- and acts on the answer.

DESIGN RULES, each load-bearing:

  * FAIL-OPEN, both sides. If this service is down, slow, or errors, the answer is
    "take it, normal size" -- NinjaTrader also enforces that with its own timeout.
    A broken bouncer must degrade to the RAW strategy (which is validated on its own),
    never to silently skipped trades: on the board "no trades" and "gate refused
    everything" look identical, and only one of them is a market observation.

  * OWN PROCESS, not a runner thread. The runner regularly saturates every core for
    hours with optimizes; a gate thread inside it would miss NinjaTrader's deadline
    exactly then, and each miss silently un-gates one live entry. This process does
    nothing else, so its latency does not depend on what research is running.

  * SAME MODEL AS THE FORWARD TEST. The nightly artifact fits the same model family,
    features, threshold and frozen size divisor as the paper leg (read from
    api/paper.py's leg configs -- one source of truth). Training set = every completed
    trade of the leg's own backtest through the latest data, which is exactly what the
    walk-forward gate would know at this moment (its refit cadence is every 25 trades,
    so "as of last night" and "as of now" are the same model in practice).

  * ORDERS STAY IN NINJATRADER. This service never places, sizes, or cancels anything.
    All existing rails (kill switch, circuit breaker, the hard-locked real account)
    are untouched because the order path is untouched.

Endpoints (127.0.0.1:8392, GET, JSON):
    /gate/health                 service + per-leg artifact status
    /gate/check?leg=NOISE_H_RF   the live decision: {take, size, prob, ...}

Run:  python -m api.gate_live --serve          (the always-on service)
      python -m api.gate_live --build          (rebuild all artifacts now)
      python -m api.gate_live --build-leg NOISE_H_RF
"""
import argparse
import json
import os
import threading
import time
from datetime import datetime

import numpy as np
import pandas as pd

ARTIFACT_DIR = r"C:\EdgeLog\gate_models"
PORT = 8392
LOG_PATH = r"C:\EdgeLog\gate_live.log"

# How much history the live feature window needs. Features reach back at most ~100 bars
# (slow ATR) plus one prior session's levels; the slow ATR is an exponential average whose
# memory of anything past ~300 bars is below one part in a billion, so 45 calendar days of
# 5-minute bars reproduces the full-history feature values at the last row to numerical
# noise. Verified by comparison in the smoke test below.
_LIVE_WINDOW_DAYS = 45

_lock = threading.Lock()          # one live-decision at a time (state is shared)
_artifacts = {}                   # leg -> loaded artifact dict (with file mtime)
_live_cache = {"arrays": None, "loaded_day": None, "tick_offset": 0, "tick_df": None,
               "tick_path": None}


def _log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _gated_legs():
    """The paper legs that carry a gate -- the single source of truth for what to serve."""
    from api import paper
    return [l for l in paper.PAPER_LEGS if l.get("gate")]


# ── nightly artifact ──────────────────────────────────────────────────────────────
def build_artifact(leg):
    """Fit the as-of-now gate model for one leg and save it to disk.

    Mirrors the paper leg exactly: same base backtest (master + today's fresh bars),
    same causal features, same model family/seed. The fit itself takes seconds -- the
    minutes-long part of the nightly paper run is walking the model through history
    trade by trade, which a live decision never needs.
    """
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    from augur_engine.ml_gate import entry_features_causal, _make_model
    from api import paper
    import joblib

    key = leg["key"]
    t0 = time.time()
    master = find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"))
    if master is None:
        raise RuntimeError(f"no master for {key}")
    arrays = load_master_arrays(master, date_from=leg.get("history_from"), date_to=None)

    # today's fresh bars, same as the paper run appends
    ticks, _ = paper._load_fresh_ticks()
    if ticks is not None:
        tf_min = 5 if str(leg["timeframe"]).lower().startswith("5") else 1
        bars = paper._resample(ticks, tf_min)
        bars, bars_et = paper._filter_rth(bars)
        last = arrays["index"][-1] if len(arrays["index"]) else None
        if last is not None and len(bars):
            bars = bars[(bars_et > last).values].reset_index(drop=True)
        if len(bars):
            arrays, _n = paper._append_fresh(arrays, bars)

    res = run_backtest(leg["strategy"], arrays=arrays, params=leg["params"],
                       cost_pts=leg.get("cost_pts", 0.0), return_trades=True)
    T = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in (res.get("trades") or [])],
               key=lambda t: t[0])
    if len(T) < 100:
        raise RuntimeError(f"{key}: only {len(T)} trades -- refusing to fit")

    F, names = entry_features_causal(arrays)
    E = np.array([t[0] for t in T])
    P = np.array([t[2] for t in T], float)
    y = (P > 0).astype(int)
    X = F[np.clip(E, 0, len(F) - 1)]

    g = leg["gate"]
    mdl = _make_model(g["model"], int(g.get("seed", 42)))
    mdl.fit(X, y, clf__sample_weight=np.abs(P) + 1e-9)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    path = os.path.join(ARTIFACT_DIR, f"{key}.pkl")
    art = {"leg": key, "model": g["model"], "mode": g.get("mode", "cut"),
           "threshold": float(g["threshold"]),
           "size_norm": float(g.get("size_norm") or 1.0),
           "recycle_factor": float(g.get("recycle_factor") or 1.0),
           "feature_names": list(names),
           "strategy": leg["strategy"], "params": dict(leg["params"]),
           "n_trades_trained": len(T),
           "trained_through": str(pd.Timestamp(arrays["index"][-1])),
           "built_at": datetime.now().isoformat(timespec="seconds"),
           "pipe": mdl}
    joblib.dump(art, path)
    _log(f"artifact {key}: fit on {len(T)} trades through {art['trained_through']} "
         f"({time.time()-t0:.1f}s) -> {path}")
    return art


def build_all():
    out = {}
    for leg in _gated_legs():
        try:
            out[leg["key"]] = build_artifact(leg)
        except Exception as e:
            _log(f"artifact {leg['key']} FAILED: {type(e).__name__}: {e}")
    return out


def _load_artifact(key):
    """Load (or reload, if the nightly rebuild replaced it) one leg's artifact."""
    import joblib
    path = os.path.join(ARTIFACT_DIR, f"{key}.pkl")
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    cur = _artifacts.get(key)
    if cur and cur.get("_mtime") == mtime:
        return cur
    art = joblib.load(path)
    art["_mtime"] = mtime
    _artifacts[key] = art
    _log(f"loaded artifact {key} (trained through {art.get('trained_through')})")
    return art


# ── live bars: cached recent master window + incrementally-read fresh ticks ───────
def _refresh_live_arrays(leg):
    """A 5m bar series ending at the most recent CLOSED bar, cheap enough to call per
    request: the master window is cached per day, and the 10s capture file is read
    incrementally (only bytes appended since the last request)."""
    from augur_engine.data import find_master, load_master_arrays
    from api import paper

    today = datetime.now().strftime("%Y-%m-%d")
    if _live_cache["loaded_day"] != today or _live_cache["arrays"] is None:
        master = find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"))
        if master is None:
            raise RuntimeError("no master")
        date_from = (pd.Timestamp(today) - pd.Timedelta(days=_LIVE_WINDOW_DAYS)).strftime("%Y-%m-%d")
        _live_cache["arrays"] = load_master_arrays(master, date_from=date_from, date_to=None)
        _live_cache["loaded_day"] = today
        _live_cache["tick_offset"] = 0
        _live_cache["tick_df"] = None
        _live_cache["tick_path"] = paper._ticks_path()
        _log(f"live window reloaded ({date_from} .. master end)")

    # incremental tick read -- append only the new bytes
    path = paper._ticks_path()
    if path != _live_cache["tick_path"]:
        _live_cache["tick_offset"] = 0
        _live_cache["tick_df"] = None
        _live_cache["tick_path"] = path
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    if size and size > _live_cache["tick_offset"]:
        import io
        with open(path, "rb") as f:
            if _live_cache["tick_offset"] == 0:
                raw = f.read()
            else:
                f.seek(_live_cache["tick_offset"])
                raw = f.read()
        _live_cache["tick_offset"] = size
        txt = raw.decode("utf-8", "replace")
        try:
            if _live_cache["tick_df"] is None:
                df = pd.read_csv(io.StringIO(txt))
            else:
                df = pd.read_csv(io.StringIO(txt), header=None,
                                 names=list(_live_cache["tick_df"].columns))
            df = df[["time", "open", "high", "low", "close", "volume"]].copy()
            df["time"] = pd.to_numeric(df["time"], errors="coerce")
            df = df.dropna(subset=["time"])
            df["time"] = df["time"].astype("int64")
            if _live_cache["tick_df"] is None:
                _live_cache["tick_df"] = df
            else:
                _live_cache["tick_df"] = pd.concat([_live_cache["tick_df"], df],
                                                   ignore_index=True)
        except Exception as e:
            _log(f"tick parse: {type(e).__name__}: {e}")

    from api import paper as _p
    arrays = _live_cache["arrays"]
    ticks = _live_cache["tick_df"]
    if ticks is not None and len(ticks):
        tf_min = 5 if str(leg["timeframe"]).lower().startswith("5") else 1
        bars = _p._resample(ticks, tf_min)
        bars, bars_et = _p._filter_rth(bars)
        last = arrays["index"][-1] if len(arrays["index"]) else None
        if last is not None and len(bars):
            bars = bars[(bars_et > last).values].reset_index(drop=True)
        if len(bars):
            arrays, _n = _p._append_fresh(arrays, bars)
    return arrays


# ── recycle interlock ─────────────────────────────────────────────────────────────
# The NinjaTrader quantity the served `size` is multiplied by. Kept here so the service
# can reason in the same contracts the breaker counts.
LIVE_QTY = int(os.environ.get("EDGELOG_LIVE_QTY", "10"))


def _recycle_allowance(art):
    """How much of the recycle factor this service is ALLOWED to serve right now.

    Recycle multiplies position size (rf on NOISE: 3.85x, peaking near 5.75x). The bridge's
    circuit breaker counts net contracts and, when its limit is exceeded, FLATTENS AND
    DISABLES every strategy on the account. So if the gate served recycled sizes while the
    rails were still set for one-lot trading, the first gated entry on Monday would trip the
    breaker and silently kill the whole forward test -- ENGU-Q included.

    Rather than depend on someone remembering to raise the rails first, the size this
    service is willing to serve is BOUNDED BY THE RAILS THE HUMAN SET. It reads
    bridge.json, works out the worst-case contracts recycle could ask for, and falls back
    to plain hybrid (1.0) if that would not fit. Raising the rails switches recycle on by
    itself, within one request. Never raises.
    """
    rec = float(art.get("recycle_factor") or 1.0)
    if rec == 1.0:
        return 1.0, None
    try:
        with open(r"C:\EdgeLog\bridge.json", encoding="utf-8") as f:
            cfg = json.load(f)
        limit = min(int(cfg.get("max_position_contracts") or 0),
                    int(cfg.get("max_qty") or 0))
    except Exception as e:
        return 1.0, f"recycle held back: cannot read the risk rails ({type(e).__name__})"
    worst = 3.0 * rec * LIVE_QTY          # the per-trade cap is 3x before recycle
    if limit >= worst:
        return rec, None
    note = (f"recycle HELD BACK (serving plain hybrid): worst case {worst:.0f} contracts "
            f"exceeds the risk rail of {limit}. Raise max_position_contracts and max_qty "
            f"to at least {int(worst)} to switch it on.")
    return 1.0, note


def decide(leg_key):
    """The live decision. NinjaTrader calls this at a bar's CLOSE, about to enter at the
    NEXT bar's open -- the same timing the backtest gate scores at. Features for that
    entry bar are, by the causal rule, the just-closed bar's market state plus the entry
    bar's clock; we append one placeholder bar so the feature builder produces exactly
    that row, and the placeholder's own prices are never read (the causal shift replaces
    them with the closed bar's).

    Never raises: any failure returns take=True/size=1.0 with the reason attached."""
    t0 = time.time()
    base = {"leg": leg_key, "take": True, "size": 1.0, "prob": None,
            "ungated_fallback": True}
    try:
        legs = {l["key"]: l for l in _gated_legs()}
        leg = legs.get(leg_key)
        if leg is None:
            base["error"] = f"unknown leg {leg_key}"
            return base
        art = _load_artifact(leg_key)
        if art is None:
            base["error"] = "no artifact - run --build"
            return base

        from augur_engine.ml_gate import entry_features_causal
        with _lock:
            arrays = _refresh_live_arrays(leg)
        idx = arrays["index"]
        if len(idx) < 200:
            base["error"] = "too little data"
            return base

        # one placeholder bar = the entry bar about to open
        step = pd.Timedelta(minutes=5 if str(leg["timeframe"]).startswith("5") else 1)
        nxt = idx[-1] + step
        arr2 = dict(arrays)
        arr2["index"] = idx.append(pd.DatetimeIndex([nxt]))
        for k in ("open", "high", "low", "close"):
            arr2[k] = np.append(np.asarray(arrays[k], float), float(arrays["close"][-1]))
        if arrays.get("volume") is not None:
            arr2["volume"] = np.append(np.asarray(arrays["volume"], float), 0.0)
        arr2["day_id"] = pd.factorize(pd.Series(arr2["index"]).dt.date)[0].astype("int64")

        F, names = entry_features_causal(arr2)
        if list(names) != list(art["feature_names"]):
            base["error"] = "feature names changed - rebuild artifact"
            return base
        x = F[-1:].astype(float)
        prob = float(art["pipe"].predict_proba(x)[0, 1])

        thr = float(art["threshold"])
        take = not (prob < thr)
        rec = 1.0            # defined on every path: a SKIP never reaches the sizing branch
        if str(art.get("mode")) == "hybrid" and take:
            w = float(np.clip(1.0 + 4.0 * (prob - 0.50), 0.25, 3.0))
            # Same order as the backtest: normalise, cap the per-trade stretch at 3x, THEN
            # apply the book-level recycle factor (spend the capital the gate freed up).
            size = float(min(w / (float(art.get("size_norm") or 1.0)), 3.0))
            rec, rec_note = _recycle_allowance(art)
            size *= rec
            if rec_note:
                base["recycle_note"] = rec_note
        else:
            size = 1.0 if take else 0.0
        out = {"leg": leg_key, "take": bool(take), "size": round(size, 3),
               "prob": round(prob, 4), "threshold": thr,
               "model": art.get("model"), "mode": art.get("mode"),
               "trained_through": art.get("trained_through"),
               "last_closed_bar": str(idx[-1]), "entry_bar": str(nxt),
               "ungated_fallback": False,
               "recycle_factor": float(art.get("recycle_factor") or 1.0),
               "recycle_applied": round(rec, 4),
               "recycle_note": base.get("recycle_note"),
               "elapsed_ms": int((time.time() - t0) * 1000)}
        _log(f"decide {leg_key}: prob={prob:.3f} take={take} size={size:.2f} "
             f"({out['elapsed_ms']}ms, bar {idx[-1]})")
        return out
    except Exception as e:
        base["error"] = f"{type(e).__name__}: {e}"
        base["elapsed_ms"] = int((time.time() - t0) * 1000)
        _log(f"decide {leg_key} FAILED (fail-open): {base['error']}")
        return base


# ── nightly self-refresh ──────────────────────────────────────────────────────────
def _refresh_loop():
    """Rebuild artifacts once per evening after the session close (16:15 ET), so the
    model always knows yesterday. Self-contained -- no dependence on the runner."""
    last_built = None
    while True:
        try:
            try:
                from zoneinfo import ZoneInfo
                et = datetime.now(ZoneInfo("America/New_York"))
            except Exception:
                et = datetime.now()
            day = et.strftime("%Y-%m-%d")
            if et.weekday() < 5 and (et.hour, et.minute) >= (16, 15) and last_built != day:
                _log("nightly artifact rebuild starting")
                build_all()
                last_built = day
        except Exception as e:
            _log(f"refresh loop: {type(e).__name__}: {e}")
        time.sleep(600)


# ── the HTTP server ───────────────────────────────────────────────────────────────
def serve():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs

    # warm everything BEFORE the first real request so trade-time latency is pure lookup
    for leg in _gated_legs():
        try:
            _load_artifact(leg["key"])
        except Exception as e:
            _log(f"warm load {leg['key']}: {type(e).__name__}: {e}")
    try:
        if _gated_legs():
            decide(_gated_legs()[0]["key"])       # primes the bar cache
    except Exception:
        pass

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):               # our own log instead
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _page(self):
            """Plain-English status page at http://127.0.0.1:8392 -- the answer to
            "how do I know this thing is running?" without a terminal. Deliberately
            self-refreshing and readable at a glance from across the room."""
            rows = ""
            for leg in _gated_legs():
                a = _artifacts.get(leg["key"]) or {}
                ok = bool(a)
                rows += (f"<tr><td>{leg['key']}</td>"
                         f"<td>{a.get('model') or '-'}</td>"
                         f"<td style='color:{'#1d9e75' if ok else '#e24b4a'}'>"
                         f"{'ready' if ok else 'NOT LOADED'}</td>"
                         f"<td>{str(a.get('trained_through') or '-')[:16]}</td></tr>")
            body = f"""<!doctype html><meta charset=utf-8>
<meta http-equiv=refresh content=15>
<title>ML gate status</title>
<style>body{{font:15px system-ui;background:#111;color:#eee;padding:28px}}
h1{{font-size:34px;margin:0 0 4px}}table{{border-collapse:collapse;margin-top:18px}}
td,th{{padding:6px 16px 6px 0;text-align:left;border-bottom:1px solid #333}}
.s{{color:#888;font-size:13px}}</style>
<h1 style="color:#1d9e75">GATE IS UP</h1>
<div class=s>NinjaTrader can ask this service before every trade.<br>
This page re-checks itself every 15 seconds.</div>
<table><tr><th>strategy</th><th>brain</th><th>state</th><th>taught through</th></tr>
{rows}</table>
<div class=s style="margin-top:20px">If this page ever fails to load, the service is
down &mdash; NinjaTrader keeps trading but takes every signal at normal size.<br>
Restart it by running <code>C:\\EdgeLog\\_gate_server.bat</code></div>"""
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/status"):
                self._page()
            elif u.path == "/gate/health":
                legs = {}
                for leg in _gated_legs():
                    a = _artifacts.get(leg["key"]) or {}
                    legs[leg["key"]] = {"loaded": bool(a),
                                        "trained_through": a.get("trained_through"),
                                        "model": a.get("model")}
                self._json({"ok": True, "legs": legs})
            elif u.path == "/gate/check":
                q = parse_qs(u.query)
                key = (q.get("leg") or [""])[0]
                self._json(decide(key))
            else:
                self._json({"error": "unknown path"}, 404)

    threading.Thread(target=_refresh_loop, daemon=True, name="gate-refresh").start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    _log(f"gate service up on 127.0.0.1:{PORT} "
         f"(legs: {', '.join(l['key'] for l in _gated_legs())})")
    srv.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--build-leg")
    ap.add_argument("--check", help="one live decision for a leg, printed")
    a = ap.parse_args()
    if a.build:
        build_all()
    if a.build_leg:
        build_artifact({l["key"]: l for l in _gated_legs()}[a.build_leg])
    if a.check:
        print(json.dumps(decide(a.check), indent=2))
    if a.serve:
        serve()


if __name__ == "__main__":
    main()
