"""Strategy 23 live signal (MISC_EODREV_1_2, engine RUN #511 PASS) - NO BROKER CODE.

Two jobs, one file:
  refresh  - nightly: rebuild the LIVE side panel from Alpaca SIP history (10-minute bars
             + daily closes, split-adjusted), same arrays and the same rules as the pinned
             research panel (C:/EdgeLog/_anatomy_cache/opus_hunt1109/s30_panel_u100.py).
             It writes a SEPARATE file; the engine's pinned panel (SHA-pinned in
             augur_strategies/MISC_EODREV_1_2.py) is never touched.
  signal   - each session at 15:21 ET: read the live panel (ends the previous session),
             take each name's 15:20 price from Alpaca's real-time IEX feed (the free plan
             serves SIP only 15+ minutes late), score exactly as the plugin does and write
             the hand-off file the Webull executor (PAPER-WB lane) reads at 15:29:
             signal_YYYY-MM-DD.json  (format agreed with PAPER-WB 2026-11-14).

THE RULE (plugin docstring): score = rank(REVERSAL) + period_wt x rank(HABIT) over the
year's point-in-time top-100 names with yesterday's raw close >= min_price;
  REVERSAL = -[(15:20 price / prior 15:50-bar close - 1) - beta x SPY's same move]
  HABIT    = mean over the prior period_len sessions of (15:30 open -> official close
             return - that day's member mean).
Buy the k best, short the k worst at 15:30, exit at the official closing print (MOC).
A session is skipped when fewer than 4 x k names have a score (plugin rule).

PARAMS are the RUN #511 engine pick (k 3, habit 60 sessions at weight 1.5, beta 180
sessions, $60 floor), not the plugin file's defaults.

score_day() reuses the plugin's own formulas line for line on a panel truncated at the
signal day, with every field that is only known after 15:20 blanked - tests/
test_eodrev_live.py checks the picks against the plugin's on the pinned panel.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UNIVERSE_JSON = os.path.join(ROOT, "tools", "data", "eodrev_universe_pit100.json")
EXCHANGES_JSON = os.path.join(ROOT, "tools", "data", "eodrev_exchanges.json")
DEFAULT_PANEL = os.environ.get("EODREV_LIVE_PANEL",
                               r"C:/EdgeLog/alpaca_cache/eodrev_panel/eodrev_u100_panel_live.npz")
DEFAULT_OUT = os.environ.get("EODREV_SIGNAL_DIR", r"C:/EdgeLog/eodrev_live")

STRATEGY = "MISC_EODREV_1_2"
RUN = 511
PARAMS = {"k": 3, "period_len": 60, "period_wt": 1.5, "beta_len": 180, "min_price": 60,
          "beta_adjust": True}
NY = "America/New_York"
BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"


# ------------------------------------------------------------------ scoring (pure)
def _frames(z):
    days = pd.Index(np.asarray(z["dates"]).astype("int64"))
    nm = [str(x) for x in z["names"]]
    f = lambda key: pd.DataFrame(np.asarray(z[key], float), index=days, columns=nm)
    mem = pd.DataFrame(np.asarray(z["member"], bool), index=days, columns=nm)
    return days, nm, f("ps"), f("pe"), f("c10"), f("dc"), f("raw"), mem


def score_day(z, day, ps_today=None, member_today=None, params=PARAMS):
    """Scores for session `day` (int yyyymmdd) -> (score Series over names, n scored).

    Rows after `day` are dropped. Live: the panel ends the session before and `ps_today`
    ({symbol: 15:20 price}, SPY included) becomes row `day`. Replay: the panel already
    holds row `day`; its 15:20 prices are used and every later field (15:30 open, 15:50
    close, daily closes) is blanked so nothing after 15:20 can leak in."""
    days, nm, ps, pe, c10, dc, raw, mem = _frames(z)
    names = nm[:-1]
    if nm[-1] != "SPY":
        raise ValueError("panel's last column must be SPY")
    keep = days <= int(day)
    ps, pe, c10, dc, raw, mem = [x.loc[keep].copy() for x in (ps, pe, c10, dc, raw, mem)]
    if int(day) not in ps.index:
        if ps_today is None:
            raise ValueError("day %s is not in the panel and no live prices were given" % day)
        for x in (ps, pe, c10, dc, raw):
            x.loc[int(day)] = np.nan
        mem.loc[int(day)] = False
        if member_today is None:
            member_today = universe_for(int(str(day)[:4]))
        mem.loc[int(day), [s for s in member_today if s in mem.columns]] = True
    if ps_today is not None:
        ps.loc[int(day)] = [float(ps_today[s]) if ps_today.get(s) is not None else np.nan for s in nm]
    for x in (pe, c10, dc, raw):            # known only after 15:20
        x.loc[int(day)] = np.nan

    # --- the plugin's formulas (augur_strategies/MISC_EODREV_1_2.py _panel/_beta/_habit/_daily_pnl)
    pc = c10.shift(1)
    s0 = ps / pc - 1.0
    ret = dc[names] / pe[names] - 1.0
    rp = raw[names].shift(1)
    dr = c10 / pc - 1.0
    member = mem[names].astype(bool)
    k, L, wt = int(params["k"]), int(params["period_len"]), float(params["period_wt"])
    w, mn = int(params["beta_len"]), float(params["min_price"])
    m = dr["SPY"]; mp = max(20, int(w * 2 / 3))
    cov = (dr[names].mul(m, axis=0).rolling(w, min_periods=mp).mean()
           - dr[names].rolling(w, min_periods=mp).mean().mul(m.rolling(w, min_periods=mp).mean(), axis=0))
    beta = cov.div(m.rolling(w, min_periods=mp).var(), axis=0).shift(1).clip(0.3, 2.5).fillna(1.0)
    ok = member & (rp >= mn)
    xa = ret.sub(ret.where(ok).mean(axis=1), axis=0)
    habit = xa.rolling(L, min_periods=int(L * 0.75)).mean().shift(1)
    spy = s0["SPY"]
    rev = -(s0[names] - beta.mul(spy, axis=0)) if params.get("beta_adjust", True) else -(s0[names].sub(spy, axis=0))
    score = (rev.where(ok).rank(axis=1, pct=True) + wt * habit.where(ok).rank(axis=1, pct=True)).where(ok)
    row = score.loc[int(day)]
    return row, int(row.notna().sum())


def picks(row, k):
    """k best (long) and k worst (short) scores, plugin order: rank(ascending=False)."""
    s = row.dropna()
    r = s.rank(ascending=False)
    n = len(s)
    longs = s[r <= k].sort_values(ascending=False)
    shorts = s[r > n - k].sort_values()
    return longs, shorts


# ------------------------------------------------------------------ universe / files
def universe_for(year):
    U = json.load(open(UNIVERSE_JSON, encoding="utf-8"))
    y = str(year) if str(year) in U else max(U)          # a new year falls back to the newest list
    return list(U[y][:100])


def _exchanges():
    try:
        return json.load(open(EXCHANGES_JSON, encoding="utf-8"))
    except Exception:
        return {}


def _write_atomic(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    os.replace(tmp, path)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build_signal(z, day, ps_today=None, panel_sha="", status_reason=None, params=PARAMS, written_et=None):
    """The hand-off dict (format agreed with PAPER-WB 2026-11-14)."""
    d = dt.datetime.strptime(str(day), "%Y%m%d").date()
    days = np.asarray(z["dates"]).astype("int64")
    prior = days[days < int(day)]
    out = {"date": d.isoformat(), "asof_et": "15:20:00",
           "written_et": written_et or dt.datetime.now(dt.timezone.utc).astimezone(_ny()).strftime("%H:%M:%S"),
           "strategy": STRATEGY, "run": RUN, "status": "SKIP", "reason": "", "k": int(params["k"]),
           "long": [], "short": [], "universe_n": len(universe_for(d.year)), "scored_n": 0,
           "panel_date": (dt.datetime.strptime(str(prior.max()), "%Y%m%d").date().isoformat() if len(prior) else None),
           "panel_sha": panel_sha, "params": {k: v for k, v in params.items() if k != "beta_adjust"}}
    if status_reason:
        out["reason"] = status_reason
        return out
    if ps_today is not None:
        # A split on the signal day: the panel's prior close is not re-adjusted until tonight, so the
        # move would read as a crash and rank the name. Drop any name more than 25 pct off its last close.
        last = dict(zip([str(x) for x in z["names"]], np.asarray(z["c10"], float)[-1]))
        bad = [s for s, v in ps_today.items() if np.isfinite(last.get(s, np.nan)) and abs(v / last[s] - 1) > 0.25]
        if bad:
            out["dropped"] = bad
            ps_today = {s: v for s, v in ps_today.items() if s not in bad}
    row, n = score_day(z, day, ps_today=ps_today, params=params)
    out["scored_n"] = n
    k = int(params["k"])
    if n < 4 * k:
        out["reason"] = "only %d names scored (needs %d)" % (n, 4 * k)
        return out
    px_src = ps_today if ps_today is not None else dict(zip([str(x) for x in z["names"]],
                                                            _frames(z)[2].loc[int(day)].tolist()))
    ex = _exchanges()
    longs, shorts = picks(row, k)
    leg = lambda s, v: {"sym": s, "px": round(float(px_src.get(s)), 4), "score": round(float(v), 6),
                        "exch": ex.get(s)}
    out["long"] = [leg(s, v) for s, v in longs.items()]
    out["short"] = [leg(s, v) for s, v in shorts.items()]
    out["status"] = "OK"
    return out


def _ny():
    from zoneinfo import ZoneInfo
    return ZoneInfo(NY)


# ------------------------------------------------------------------ Alpaca (data only)
def _keys():
    sys.path.insert(0, ROOT)
    from augur_engine import alpaca_keys
    k, s = alpaca_keys.load_keys()
    if not k:
        raise RuntimeError("no Alpaca key found (%s)" % alpaca_keys.describe())
    return k, s


def fetch_bars(symbols, timeframe, start, end, feed="sip", adjustment="split", keys=None, chunk=25):
    """{symbol: DataFrame(t, o, h, l, c, v)} via the multi-symbol bars endpoint, paged."""
    import time
    import requests
    k, s = keys or _keys()
    heads = {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}
    out = {}
    step = chunk
    for i in range(0, len(symbols), step):
        chunk = symbols[i:i + step]
        token = None
        while True:
            q = {"symbols": ",".join(chunk), "timeframe": timeframe, "start": start, "end": end,
                 "limit": 10000, "adjustment": adjustment, "feed": feed, "sort": "asc"}
            if token:
                q["page_token"] = token
            for attempt in range(6):
                r = requests.get(BARS_URL, headers=heads, params=q, timeout=60, allow_redirects=False)
                if r.status_code == 429:
                    time.sleep(20); continue
                break
            if r.status_code != 200:
                raise RuntimeError("Alpaca bars HTTP %s: %s" % (r.status_code, r.text[:200]))
            js = r.json()
            for sym, rows in (js.get("bars") or {}).items():
                out.setdefault(sym, []).extend(rows)
            token = js.get("next_page_token")
            time.sleep(0.31)                                   # ~195 requests a minute, house pace
            if not token:
                break
    return {sym: pd.DataFrame(rows) for sym, rows in out.items()}


_SPLITS = sorted({r for n in (2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50) for r in (n, 1.0 / n)} | {1.5, 2 / 3.0})


def fix_missed_splits(ps, pe, c10, dc, names, log=print):
    """Alpaca's split-adjusted feed sometimes misses a split (GE 1-for-8 2021-08-02; KLAC 10-for-1
    2026-06-12, seen 2026-11-14). A megacap never moves 40 pct close to close, so a jump that size
    near a standard split ratio is a split: every earlier row of that name is rescaled by it.
    Fields: the split-adjusted ones (ps, pe, c10, dc). The raw close is left raw (it is the floor)."""
    ps, pe, c10, dc = ps.copy(), pe.copy(), c10.copy(), dc.copy()
    for s in names:
        x = dc[s].dropna()
        r = (x / x.shift(1)).dropna()
        for day, v in r[(r < 0.6) | (r > 1.67)].items():
            f = min(_SPLITS, key=lambda q: abs(np.log(v / q)))
            if abs(np.log(v / f)) > np.log(1.25):
                log("refresh: %s %s jump x%.3f is not a split ratio - left alone" % (s, day, v)); continue
            before = ps.index < day
            for fr in (ps, pe, c10, dc):
                fr.loc[before, s] = fr.loc[before, s] * f
            log("refresh: %s split x%g on %s rescaled (Alpaca feed missed it)" % (s, f, day))
    return ps, pe, c10, dc


def window_bars(symbols, days, keys=None, log=print, threads=3):
    """10-minute SIP bars 15:10-16:00 ET only, one request per session (a full-day pull returns the
    extended-hours bars too and pages at ~1,200 bars: ~50 min a rebuild; this is ~3 min)."""
    from concurrent.futures import ThreadPoolExecutor
    tz = _ny()
    def one(d):
        dd = dt.datetime.strptime(str(d), "%Y%m%d")
        a = dd.replace(hour=15, minute=10, tzinfo=tz).astimezone(dt.timezone.utc)
        b = dd.replace(hour=16, minute=0, tzinfo=tz).astimezone(dt.timezone.utc)
        f = lambda x: x.isoformat().replace("+00:00", "Z")
        return fetch_bars(symbols, "10Min", f(a), f(b), keys=keys, chunk=150)
    out = {}
    with ThreadPoolExecutor(threads) as ex:
        for i, res in enumerate(ex.map(one, days)):
            for sym, df in res.items():
                out.setdefault(sym, []).append(df)
            if i % 50 == 0:
                log("refresh: %d / %d sessions" % (i, len(days)))
    return {sym: pd.concat(v, ignore_index=True) for sym, v in out.items()}


def live_prices_1520(symbols, day, keys=None):
    """Each symbol's last IEX trade-bar close in 15:10-15:19 ET (= the 15:20 price)."""
    d = dt.datetime.strptime(str(day), "%Y%m%d")
    tz = _ny()
    a = d.replace(hour=15, minute=10, tzinfo=tz).astimezone(dt.timezone.utc)
    b = d.replace(hour=15, minute=20, tzinfo=tz).astimezone(dt.timezone.utc)
    bars = fetch_bars(symbols, "1Min", a.isoformat().replace("+00:00", "Z"),
                      b.isoformat().replace("+00:00", "Z"), feed="iex", adjustment="raw", keys=keys)
    px = {}
    for sym, df in bars.items():
        if len(df):
            t = pd.to_datetime(df["t"], utc=True)
            df = df[t < pd.Timestamp(b)]
            if len(df):
                px[sym] = float(df["c"].iloc[-1])
    return px


# ------------------------------------------------------------------ nightly panel refresh
def refresh_panel(out_path=DEFAULT_PANEL, days_back=420, today=None, keys=None, log=print):
    """Rebuild the live panel from scratch (Alpaca re-adjusts splits; never patch, re-pull).
    Ends at the last COMPLETED session before `today` (ET)."""
    tz = _ny()
    today = today or dt.datetime.now(tz).date()
    end = dt.datetime.combine(today, dt.time(0, 0), tzinfo=tz).astimezone(dt.timezone.utc)
    start = end - dt.timedelta(days=days_back)
    iso = lambda x: x.isoformat().replace("+00:00", "Z")
    U = json.load(open(UNIVERSE_JSON, encoding="utf-8"))
    years = sorted({str(today.year), str(today.year - 1), str((today - dt.timedelta(days=days_back)).year)})
    names = sorted({s for y in years if y in U for s in U[y][:100]})
    syms = names + ["SPY"]
    log("refresh: %d names, %s .. %s" % (len(names), start.date(), today))

    def daily(dd, sym):
        df = dd.get(sym)
        if df is None or not len(df):
            return pd.Series(dtype=float)
        t = pd.to_datetime(df["t"], utc=True).dt.tz_convert(NY).dt.strftime("%Y%m%d").astype("int64")
        return pd.Series(df["c"].values, index=t.values).groupby(level=0).first()

    def at(df, minute, col):
        if df is None or not len(df):
            return pd.Series(dtype=float)
        t = pd.to_datetime(df["t"], utc=True).dt.tz_convert(NY)
        mm = t.dt.hour * 60 + t.dt.minute
        x = df[(mm == minute).values]
        idx = t[(mm == minute).values].dt.strftime("%Y%m%d").astype("int64")
        return pd.Series(x[col].values, index=idx.values).groupby(level=0).first()

    dsp = fetch_bars(syms, "1Day", iso(start), iso(end), adjustment="split", keys=keys)
    b10 = window_bars(syms, sorted(daily(dsp, "SPY").index), keys=keys, log=log)
    draw = fetch_bars(syms, "1Day", iso(start), iso(end), adjustment="raw", keys=keys)
    PS = pd.DataFrame({s: at(b10.get(s), 910, "c") for s in syms})
    PE = pd.DataFrame({s: at(b10.get(s), 930, "o") for s in syms})
    C = pd.DataFrame({s: at(b10.get(s), 950, "c") for s in syms})
    days = PE["SPY"].dropna().index.intersection(C["SPY"].dropna().index).sort_values()  # half days drop out
    ps, pe, c10 = [v.reindex(index=days, columns=syms) for v in (PS, PE, C)]
    dc = pd.DataFrame({s: daily(dsp, s) for s in names}).reindex(index=days, columns=names)
    raw = pd.DataFrame({s: daily(draw, s) for s in names}).reindex(index=days, columns=names)
    ps, pe, c10, dc = fix_missed_splits(ps, pe, c10, dc, names, log=log)
    bad = (dc / c10[names] - 1).abs() > 0.08            # builder guard: a bad daily close
    dc = dc.where(~bad)
    dc["SPY"] = np.nan; raw["SPY"] = np.nan
    mem = pd.DataFrame(False, index=days, columns=syms)
    yr = (days // 10000).astype(int)
    for y, lst in U.items():
        r = yr == int(y)
        mem.loc[r, [s for s in lst[:100] if s in names]] = True
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp.npz"
    np.savez(tmp, dates=np.asarray(days, dtype="int64"), names=np.array(syms), ps=ps.values,
             pe=pe.values, c10=c10.values, dc=dc[syms].values, raw=raw[syms].values, member=mem.values)
    os.replace(tmp, out_path)
    log("refresh: wrote %s - %d sessions, last %s, sha %s" % (out_path, len(days), days.max(), sha256(out_path)[:12]))
    return out_path


# ------------------------------------------------------------------ CLI
def _load(path):
    return dict(np.load(path, allow_pickle=False))


def cmd_signal(a):
    tz = _ny()
    if a.wait_until and not a.replay:
        # A scheduler in another zone (the PC runs Mountain time, ET moves with DST) starts this
        # early; it sleeps to the ET clock itself.
        import time
        hh, mm = [int(x) for x in a.wait_until.split(":")]
        target = dt.datetime.now(tz).replace(hour=hh, minute=mm, second=5, microsecond=0)
        wait = (target - dt.datetime.now(tz)).total_seconds()
        if wait > 6 * 3600:
            print("more than 6 h before %s ET - wrong start time, not waiting" % a.wait_until); return 1
        if wait > 0:
            print("waiting %.0f s until %s ET" % (wait, a.wait_until), flush=True)
            time.sleep(wait)
    now = dt.datetime.now(tz)
    day = int(a.day.replace("-", "")) if a.day else int(now.strftime("%Y%m%d"))
    path = os.path.join(a.out_dir, "signal_%s-%s-%s.json" % (str(day)[:4], str(day)[4:6], str(day)[6:]))
    if os.path.exists(path) and not a.force:
        print("exists, not rewritten:", path); return 0
    z = _load(a.panel)
    sha = sha256(a.panel)
    if a.replay:
        sig = build_signal(z, day, panel_sha=sha, written_et="replay")
    else:
        reason = None
        last = int(np.asarray(z["dates"]).max())
        if last >= day:
            reason = "panel already holds today (%s); refuse to trade on a wrong panel" % last
        syms = universe_for(day // 10000) + ["SPY"]
        px = {}
        if not reason:
            px = live_prices_1520(syms, day)
            if "SPY" not in px:
                reason = "no SPY 15:10-15:19 bars: not a full session (holiday or half day)"
            elif not a.skip_stale_check:
                # stale panel: any completed session between the panel's last day and today
                st = dt.datetime.strptime(str(last), "%Y%m%d") + dt.timedelta(days=1)
                en = dt.datetime.strptime(str(day), "%Y%m%d")
                if en > st:
                    spy = fetch_bars(["SPY"], "1Day", st.strftime("%Y-%m-%dT00:00:00Z"),
                                     en.strftime("%Y-%m-%dT00:00:00Z"), adjustment="raw").get("SPY")
                    if spy is not None and len(spy):
                        reason = "stale panel: ends %s, missing %d session(s)" % (last, len(spy))
        sig = build_signal(z, day, ps_today=px or None, panel_sha=sha, status_reason=reason)
    _write_atomic(path, sig)
    print(json.dumps({"file": path, "status": sig["status"], "reason": sig["reason"],
                      "long": [x["sym"] for x in sig["long"]], "short": [x["sym"] for x in sig["short"]]}))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh", help="nightly: rebuild the live panel from Alpaca SIP")
    r.add_argument("--panel", default=DEFAULT_PANEL)
    r.add_argument("--days-back", type=int, default=420)
    s = sub.add_parser("signal", help="15:21 ET: write signal_YYYY-MM-DD.json")
    s.add_argument("--panel", default=DEFAULT_PANEL)
    s.add_argument("--out-dir", default=DEFAULT_OUT)
    s.add_argument("--day", help="YYYY-MM-DD (default: today ET)")
    s.add_argument("--replay", action="store_true", help="dry run: use the panel's own 15:20 prices for --day")
    s.add_argument("--force", action="store_true", help="rewrite an existing file (dry runs only)")
    s.add_argument("--skip-stale-check", action="store_true")
    s.add_argument("--wait-until", default="15:21", help="ET clock to sleep until before fetching (HH:MM; '' = now)")
    a = ap.parse_args(argv)
    if a.cmd == "refresh":
        refresh_panel(a.panel, a.days_back); return 0
    return cmd_signal(a)


if __name__ == "__main__":
    sys.exit(main())
