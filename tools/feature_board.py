"""
tools/feature_board.py — CROSS-FAMILY FEATURE BOARD.

For every crowned strategy leg (ORB, NOISE, ENGU-Q, NQDIP families), this scores the
same set of causal (known-before-entry) market features against per-trade PnL, then
promotes only the features that agree in sign across >= 3 DISTINCT families AND whose
sign repeats in each of those families' lockbox (last 12 months). The point is not to
find a new edge inside any one family — the strategies are already crowned — it is to
find which market conditions systematically help or hurt trades everywhere, something
no single-family study can see.

WHAT "CAUSAL" MEANS HERE: every feature is a value that a live trader could have read
BEFORE the trade filled — never anything built from the trade's own bars or its exit.
Four feature groups:
  1. bar     — augur_engine.ml_gate.entry_features_causal: momentum/vol/trend/range/
               distance-to-prior-day-levels/clock, read at the trade's OWN entry bar
               (that function already shifts market columns back one bar internally,
               so index it AT the entry bar, not entry_bar-1).
  2. daily / macro — augur_engine.context.build_internal_daily (own bars, prior-day
               shifted) + augur_engine.context.fetch_external_daily (VIX/TNX, best
               effort, never fatal). Joined on the trade's entry DATE.
  3. structure — five extra prior-day-shifted daily features this file builds itself
               (distance from 20/50/200-day SMA in 20-day-ATR units, position inside
               the prior week's high-low range, prior day's own close position).
  4. state   — hourly (60-min) compression state from tools/ttmsqz_round6_parts.py's
               `hourly_compression`, read at entry_bar-1 (a state flag, not a bar
               value — matches how round 6 already reads it for its own scan).

SCORING (per leg, per feature, PRE-LOCKBOX trades only): Spearman rho, a 95% CI from
augur_engine.context's MOVING-BLOCK bootstrap, Benjamini-Hochberg FDR across every
feature scored on that leg, and a beats-probe check against 3 shadow (shuffled)
features — the same stats primitives context.py's own context_scores() uses
(_rank/_pearson/_pvalue/_autocorr_and_persistence/_block_days_for/_block_bootstrap_ci/
_bh_fdr), just applied to a per-TRADE feature matrix instead of a per-DAY-joined one,
because the bar-level group needs per-trade (not per-day) granularity. `survives` =
q<0.10 AND the CI excludes zero AND the feature beats its shadow-probe floor. Then,
separately, the SAME rho on LOCKBOX-only trades (light peek, not a second test) checks
whether the sign repeats — `lb_agrees` (null below 30 lockbox trades).

LIFT: a second, TAIL-aware statistic alongside the rank test above (Spearman is blind to
a few big winners moving the average). Per leg/feature, on PRE-LOCKBOX trades: split
trades into HIGH (top tercile, or "on" for a binary feature) and LOW (bottom tercile, or
"off") groups, convert PnL to R (trade $ / the leg's own average PRE-LOCKBOX losing trade
in $), and take lift_r = mean R in HIGH minus mean R in LOW. lift_lo/lift_hi come from the
same moving-block-of-trading-days bootstrap as the rank CI, with group membership fixed;
lift_p is a two-sided permutation test that shuffles the feature's values at the DAY level
(bar/state features, which can vary within a day, instead shuffle per-trade within ~21-day
blocks) and lift_q is that leg's BH-FDR across features. lift_survives requires lift_q<0.10,
a CI that excludes zero, and beating the 3 shadow probes' lift. lb_lift_r/lb_lift_agrees
replay the SAME HIGH/LOW thresholds on lockbox trades as a lockbox sign check.

PROMOTION: group legs by family. A feature is PROMOTED when >= 3 distinct families each
have >= 1 leg with survives=true and the SAME sign, and every one of those families has
at least one leg where lb_agrees is true. WATCH = 2 families clearing that bar, or >= 3
families agreeing in sign with survives=true but the lockbox check missing/false in at
least one of them. Otherwise NONE. The whole rule is run TWICE — once on the rank basis
above, once on the LIFT basis (lift_survives / lift_r / lb_lift_agrees) — and a feature's
verdict keeps whichever basis reaches the stronger tier; `basis` records which one ("rank",
"lift", or "both" when they tie on tier).

Outputs: docs/feature_board.json (schema is a contract — a web page consumes it, see
the dict literal at the bottom of main() for the exact shape) and docs/FEATURE_BOARD.md
(15-30 line plain-English summary).

Usage:
  python tools/feature_board.py            # full run (~10-20 min, ENGU-Q 1m ETH is
                                            #   the slow leg; re-runs reuse the trade
                                            #   cache in tools/_featboard_cache/)
  python tools/feature_board.py --quick    # skips fetch_external_daily (no network),
                                            #   for fast local testing
"""
import os
import sys
import json
import pickle
import inspect
import argparse
import datetime
import importlib.util as _ilu
import warnings

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
UP_LOCAL = os.path.join(ROOT, "augur_uploads")
UP_SHARED = os.path.join(SHARED, "augur_uploads")
# Caches live OUTSIDE the git worktrees: on 2026-09-07 a worktree cleanup wiped two hours of
# 1-minute replays and every cached run doc. C:\EdgeLog is the machine's stable, non-git home
# (runner logs, launchers); override with EDGELOG_CACHE_DIR when needed.
_CACHE_BASE = os.environ.get("EDGELOG_CACHE_DIR") or (
    r"C:\EdgeLog\_anatomy_cache" if os.path.isdir(r"C:\EdgeLog") else os.path.join(ROOT, "tools", "_anatomy_cache"))
CACHE_DIR = os.path.join(_CACHE_BASE, "featboard")
DOC_CACHE_DIR = os.path.join(_CACHE_BASE, "docs")
DOCS_OUT = os.path.join(ROOT, "docs")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import context as ctx           # noqa: E402  (reused stats primitives)
from augur_engine import ml_gate                  # noqa: E402  (entry_features_causal)

LIFT_MIN_GROUP = max(30.0, ctx.MIN_FEATURE_TRADES / 3.0)   # min trades per HIGH/LOW group

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

COST = {"NQ": 0.533, "ES": 0.363}
MULT = {"NQ": 20.0, "ES": 50.0}

N_BOOT = 300
SEED = 42
PROMOTE_FAMILIES = 3
FDR_Q = 0.10
LOCKBOX_MIN_TRADES = 30

# ── LIFT (tail-aware second statistic, see module docstring's LIFT DEFINITION) ──
LIFT_N_PERM = 1000               # permutation draws for lift_p
LIFT_BLOCK_PERM_DAYS = 21        # ~1 trading month block for bar/state-group permutation
LB_LIFT_MIN_TRADES = 15          # min trades per lockbox group for lb_lift_agrees


# ─────────────────────────────────────────────────────────────────────────────
# module / master-bar loading — same pattern as tools/ttmsqz_round6_parts.py
# ─────────────────────────────────────────────────────────────────────────────

def _mod(path, name):
    sp = _ilu.spec_from_file_location(name, path)
    m = _ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


_TTM = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_1_0.py"), "ttm_featboard")


def load(inst, tf, session, date_from, date_to):
    """Master bars with _dt (bar open) and _end (bar close = when it becomes knowable).
    Verbatim pattern from tools/ttmsqz_round6_parts.py's `load`, parametrized on the
    window instead of module-level constants (each leg has its own window)."""
    fn = "NOADJ_%s_%s_%s.csv" % (inst, tf, session)
    path = os.path.join(UP_LOCAL, fn)
    if not os.path.exists(path):
        path = os.path.join(UP_SHARED, fn)
    df = pd.read_csv(path)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = df[(df["_dt"].dt.date >= pd.Timestamp(date_from).date())
            & (df["_dt"].dt.date <= pd.Timestamp(date_to).date())].reset_index(drop=True)
    df["_end"] = df["_dt"] + pd.Timedelta(minutes=int(tf[:-1]))
    # ETH runs 18:00 -> 17:00 next day, so the trading DAY rolls at 18:00 ET.
    d = (df["_dt"] + pd.Timedelta(hours=6)).dt.date if session == "ETH" else df["_dt"].dt.date
    df["day_id"] = pd.factorize(d)[0]
    return df


def hourly_compression(df, gate_tf_min=60, length=20, bb_mult=2.0, kc_mult=1.5):
    """Compression state of the gate_tf_min frame, mapped causally onto df's bars.
    Verbatim from tools/ttmsqz_round6_parts.py."""
    first = df.groupby("day_id")["_dt"].transform("first")
    off = ((df["_dt"] - first).dt.total_seconds() // 60).astype("int64")
    key = df["day_id"].astype(str) + "_" + (off // int(gate_tf_min)).astype(str).str.zfill(4)
    g = df.groupby(key, sort=True)
    hh, ll, cc = g["high"].max().values, g["low"].min().values, g["close"].last().values
    end = g["_end"].last().values
    order = np.argsort(end)
    hh, ll, cc, end = hh[order], ll[order], cc[order], end[order]
    sq, _, _ = _TTM.squeeze_indicators(hh, ll, cc, length, bb_mult, kc_mult)
    warm = length * 2 + 5
    j = np.searchsorted(end, df["_end"].values, side="right") - 1
    ok = j >= warm
    jj = np.clip(j, 0, len(cc) - 1)
    return np.where(ok, sq[jj], False).astype(bool)


# ─────────────────────────────────────────────────────────────────────────────
# structure daily features (this file's own extras — see module docstring)
# ─────────────────────────────────────────────────────────────────────────────

def build_structure_daily(index, opens, highs, lows, closes):
    """Five causal daily extras, built the same prior-day-shifted way as
    augur_engine.context.build_internal_daily: distance of prior close from the
    20/50/200-day SMA in 20-day-ATR units, prior close's position inside the PRIOR
    WEEK's high-low range (0..1), and the prior day's own close position inside its
    own high-low range (0..1). Returns a DataFrame indexed by datetime.date."""
    eix = pd.to_datetime(pd.Series(index))
    dts = eix.dt.date.values
    O = np.asarray(opens, float); H = np.asarray(highs, float)
    L = np.asarray(lows, float); C = np.asarray(closes, float)
    n = min(len(dts), len(O), len(H), len(L), len(C))
    df = pd.DataFrame({"d": dts[:n], "o": O[:n], "h": H[:n], "l": L[:n], "c": C[:n]})
    day = df.groupby("d", sort=True).agg(o=("o", "first"), h=("h", "max"),
                                         l=("l", "min"), c=("c", "last"))
    prior_c = day["c"].shift(1)
    tr = np.maximum(day["h"] - day["l"],
                    np.maximum((day["h"] - prior_c).abs(), (day["l"] - prior_c).abs()))
    atr20 = tr.rolling(20, min_periods=20).mean().replace(0.0, np.nan)
    sma20 = day["c"].rolling(20, min_periods=20).mean()
    sma50 = day["c"].rolling(50, min_periods=50).mean()
    sma200 = day["c"].rolling(200, min_periods=200).mean()
    dist_sma20d_atr = (day["c"] - sma20) / atr20
    dist_sma50d_atr = (day["c"] - sma50) / atr20
    dist_sma200d_atr = (day["c"] - sma200) / atr20
    close_pos_own = (day["c"] - day["l"]) / (day["h"] - day["l"]).replace(0.0, np.nan)

    diso = pd.to_datetime(day.index)
    iso = diso.isocalendar()
    wk = iso["year"].astype(str).to_numpy() + "-" + iso["week"].astype(str).str.zfill(2).to_numpy()
    wtab = pd.DataFrame({"h": day["h"].to_numpy(), "l": day["l"].to_numpy(), "wk": wk})
    wagg = wtab.groupby("wk", sort=True).agg(wh=("h", "max"), wl=("l", "min"))
    wagg_prior = wagg.shift(1)                       # the week BEFORE each week
    prior_wk_for_day = wagg_prior.reindex(wk)
    prior_wk_for_day.index = day.index
    pos_prev_week = ((day["c"] - prior_wk_for_day["wl"])
                     / (prior_wk_for_day["wh"] - prior_wk_for_day["wl"]).replace(0.0, np.nan))

    raw = pd.DataFrame({"dist_sma20d_atr": dist_sma20d_atr, "dist_sma50d_atr": dist_sma50d_atr,
                        "dist_sma200d_atr": dist_sma200d_atr, "prev_day_close_pos": close_pos_own,
                        "pos_prev_week": pos_prev_week})
    return raw.shift(1)                               # causal: entry day D sees D-1's row


STRUCTURE_COLS = ["dist_sma20d_atr", "dist_sma50d_atr", "dist_sma200d_atr",
                  "pos_prev_week", "prev_day_close_pos"]

BAR_COLS = ["atr_norm", "atr_ratio", "mom_5", "mom_20", "trend_20", "range_pos",
           "dist_pdh_atr", "dist_pdl_atr", "dist_pdc_atr", "tod_sin", "tod_cos", "dow"]

STATE_COLS = ["compressed_60m"]


# ─────────────────────────────────────────────────────────────────────────────
# Firestore (ONE .get() per doc, then a local JSON cache so repeat runs of this
# script never touch Firestore again — the plan has a 50k reads/day cap)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_doc(doc_id):
    os.makedirs(DOC_CACHE_DIR, exist_ok=True)
    cache_fp = os.path.join(DOC_CACHE_DIR, f"{doc_id}.json")
    if os.path.exists(cache_fp):
        with open(cache_fp, encoding="utf-8") as f:
            return json.load(f)
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred_path = "serviceAccount.json"
    if not os.path.exists(cred_path):
        cred_path = os.path.join(SHARED, "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    db = firestore.client()
    snap = db.collection("users").document(UID).collection("backtests").document(doc_id).get()
    if not snap.exists:
        raise RuntimeError(f"doc {doc_id} does not exist")
    d = snap.to_dict()

    def _default(o):
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        return str(o)

    with open(cache_fp, "w", encoding="utf-8") as f:
        json.dump(d, f, default=_default, indent=1)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# leg definitions
# ─────────────────────────────────────────────────────────────────────────────

LEGS = [
    dict(key="ORB_314", family="ORB", label="ORB #314 (crown)", file="ORB_3_6_R6.py",
        run=314, doc="2VCld7X1YRqQlQa25AM5"),
    dict(key="ORB_234", family="ORB", label="ORB #234 (control, pinned card)", file="ORB_3_6_C2.py",
        run=234, doc=None,
        fallback=dict(instrument="NQ", timeframe="5m", session="RTH",
                      cost_pts=COST["NQ"], mult=MULT["NQ"], date_from="2010-06-07",
                      date_to="2026-06-30", lockbox_months=12)),
    dict(key="NOISE_243", family="NOISE", label="NOISE #243 (paper leg, pinned)",
        file="NOISE_1_1_SBS_V90.py", run=243, doc="9cr6rtZPZng2HIiLxH3K"),
    dict(key="NOISE_316", family="NOISE", label="NOISE #316", file="NOISE_1_1_LB51.py",
        run=316, doc="8ktC5qWGwXgVfeN5d92w"),
    dict(key="ENGUQ_309", family="ENGUQ", label="ENGU-Q #309 (crown, NQ 1m ETH)",
        file="ENGUQ_1M_ETH_ER_1_0.py", run=309, doc="KPbrQdTZBP32CFjwF1Ns"),
    dict(key="NQDIP_307", family="NQDIP", label="NQDIP #307", file="NQDIP_1_0.py",
        run=307, doc="8zkU44lPUNRtKR5IMWR2"),
]

FEATURES = [
    dict(name="mom_5", label="5-bar momentum (in ATR units)", group="bar",
        desc="How far price has moved over the last 5 bars, scaled by recent volatility."),
    dict(name="mom_20", label="20-bar momentum (in ATR units)", group="bar",
        desc="How far price has moved over the last 20 bars, scaled by recent volatility."),
    dict(name="atr_norm", label="Volatility level (ATR / price)", group="bar",
        desc="Recent average bar range as a fraction of price — how choppy the tape is right now."),
    dict(name="atr_ratio", label="Volatility expansion (fast ATR / slow ATR)", group="bar",
        desc="Whether short-term volatility is running hot or cold compared to its own slow baseline."),
    dict(name="trend_20", label="20-bar trend strength", group="bar",
        desc="How straight-line the last 20 bars have been (near 1 or -1 = trending, near 0 = choppy)."),
    dict(name="range_pos", label="Position in the 20-bar range", group="bar",
        desc="Where the current price sits inside its own recent 20-bar high-low range, 0=low to 1=high."),
    dict(name="dist_pdh_atr", label="Distance from yesterday's high (ATR units)", group="bar",
        desc="How far the current price sits above or below the PRIOR session's high."),
    dict(name="dist_pdl_atr", label="Distance from yesterday's low (ATR units)", group="bar",
        desc="How far the current price sits above or below the PRIOR session's low."),
    dict(name="dist_pdc_atr", label="Distance from yesterday's close (ATR units)", group="bar",
        desc="How far the current price sits above or below the PRIOR session's closing price."),
    dict(name="tod_sin", label="Time of day (clock, sine component)", group="bar",
        desc="Where in the trading day this bar falls, encoded as a smooth clock position."),
    dict(name="tod_cos", label="Time of day (clock, cosine component)", group="bar",
        desc="Where in the trading day this bar falls, the other half of the clock encoding."),
    dict(name="dow", label="Day of week", group="bar",
        desc="Which weekday the trade entered on (Monday=0 .. Friday=4)."),
    dict(name="rsi14", label="Daily RSI(14), prior day", group="daily",
        desc="Yesterday's 14-day Relative Strength Index — how overbought or oversold the daily chart was."),
    dict(name="macd_hist", label="Daily MACD histogram, prior day", group="daily",
        desc="Yesterday's MACD momentum histogram, normalized by price."),
    dict(name="atr20_pctile", label="Daily volatility percentile, prior day", group="daily",
        desc="Where yesterday's 20-day average daily range ranked against the last year — a calm-vs-wild reading."),
    dict(name="er20", label="Daily efficiency ratio (20d), prior day", group="daily",
        desc="Yesterday's ratio of net move to total path length over 20 days — high means trending, low means choppy."),
    dict(name="gap_pct", label="Today's open gap vs yesterday's close", group="daily",
        desc="How far today's opening price jumped from yesterday's close, in percent."),
    dict(name="prev_ret", label="Prior day's return", group="daily",
        desc="Yesterday's close-to-close percent change."),
    dict(name="range_pctile", label="Daily range percentile, prior day", group="daily",
        desc="Where yesterday's high-low range ranked against the last year."),
    dict(name="up_streak", label="Consecutive up/down day count, prior day", group="daily",
        desc="How many days in a row closed up (positive) or down (negative) through yesterday."),
    dict(name="vix", label="VIX level, prior close", group="macro",
        desc="Yesterday's closing VIX (stock-market fear gauge) level."),
    dict(name="vix_pctile_1y", label="VIX percentile (1yr), prior close", group="macro",
        desc="Where yesterday's VIX ranked against the last year — high means unusually fearful markets."),
    dict(name="vix_chg_5d", label="VIX 5-day change, prior close", group="macro",
        desc="How much the VIX moved over the prior 5 trading days."),
    dict(name="vix_term", label="VIX term structure (3mo - spot)", group="macro",
        desc="Whether longer-dated VIX futures expect calm or more fear than right now (negative = stress)."),
    dict(name="tnx", label="10-year Treasury yield, prior close", group="macro",
        desc="Yesterday's 10-year Treasury yield level."),
    dict(name="tnx_chg_20d", label="10-year yield 20-day change", group="macro",
        desc="How much the 10-year Treasury yield moved over the prior month."),
    dict(name="curve", label="Yield curve (10y minus 3mo)", group="macro",
        desc="The gap between long and short interest rates — negative means the curve is inverted."),
    dict(name="dist_sma20d_atr", label="Distance from the 20-day average price (ATR units)", group="structure",
        desc="How far yesterday's close sits above or below its own 20-day average, scaled by volatility."),
    dict(name="dist_sma50d_atr", label="Distance from the 50-day average price (ATR units)", group="structure",
        desc="How far yesterday's close sits above or below its own 50-day average, scaled by volatility."),
    dict(name="dist_sma200d_atr", label="Distance from the 200-day average price (ATR units)", group="structure",
        desc="How far yesterday's close sits above or below its own 200-day average, scaled by volatility."),
    dict(name="pos_prev_week", label="Position inside the week-before-last's range", group="structure",
        desc="Where yesterday's close sat inside the high-low range of the week before last, 0=low to 1=high."),
    dict(name="prev_day_close_pos", label="Yesterday's close position in its own range", group="structure",
        desc="Where yesterday closed inside its own high-low range for that day, 0=low to 1=high."),
    dict(name="compressed_60m", label="Hourly chart is coiled (squeeze on)", group="state",
        desc="Whether the 60-minute chart was in a volatility squeeze (coiled, about to move) just before entry."),
]
FEATURE_NAMES = [f["name"] for f in FEATURES]
FEATURE_GROUP = {f["name"]: f["group"] for f in FEATURES}
# LIFT permutation granularity: "day" = one value per calendar day (daily/macro/
# structure groups, already joined by date) -> permute at the DAY level. "bar" =
# can vary within a day (bar/state groups, read per-trade at the entry bar) ->
# permute per-trade values within ~21-trading-day blocks instead (see
# _lift_perm_pvalue).
GROUP_KIND = {"bar": "bar", "state": "bar", "daily": "day", "macro": "day", "structure": "day"}


# ─────────────────────────────────────────────────────────────────────────────
# resolve a leg's config (params/window/instrument) from its Firestore doc
# ─────────────────────────────────────────────────────────────────────────────

def resolve_leg_config(leg):
    if leg["doc"] is None:
        fb = leg["fallback"]
        return dict(instrument=fb["instrument"], timeframe=fb["timeframe"], session=fb["session"],
                    source="defaults", cost_pts=fb["cost_pts"], mult=fb["mult"],
                    date_from=fb["date_from"], date_to=fb["date_to"],
                    lockbox_months=fb["lockbox_months"], lockbox_from=None,
                    best_params={}, parity_source="defaults", parity_expected=None)
    d = _fetch_doc(leg["doc"])
    r = d.get("result", {}) or {}
    gv = r.get("gate_validate", {}) or {}
    best_params = r.get("best_params") or {}
    parity_expected = {}
    for blk_name, out_name in (("ungated_full", "full"), ("ungated_pre", "pre"),
                               ("ungated_lockbox", "lockbox")):
        blk = gv.get(blk_name)
        if isinstance(blk, dict) and blk:
            parity_expected[out_name] = dict(n=blk.get("num_trades"),
                                             net_pts=blk.get("total_pnl"),
                                             pf=blk.get("profit_factor"))
    return dict(instrument=d.get("instrument"), timeframe=d.get("timeframe"),
                session=str(d.get("session", "RTH")).upper(), source=d.get("source"),
                cost_pts=float(d.get("cost_pts", 0.0) or 0.0), mult=float(d.get("mult", 1.0) or 1.0),
                date_from=d.get("date_from"), date_to=d.get("date_to"),
                lockbox_months=d.get("lockbox_months"), lockbox_from=gv.get("lockbox_from"),
                best_params=best_params, parity_source="doc", parity_expected=parity_expected)


def _lockbox_from_date(cfg):
    if cfg.get("lockbox_from"):
        try:
            return pd.Timestamp(str(cfg["lockbox_from"])[:10]).date()
        except Exception:
            pass
    months = cfg.get("lockbox_months") or 12
    return (pd.Timestamp(cfg["date_to"]) - pd.DateOffset(months=int(months))).date()


# ─────────────────────────────────────────────────────────────────────────────
# run one leg's strategy locally, EXACTLY the doc's crowned params
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_kwargs(module, best_params):
    defaults = {k: v["default"] for k, v in getattr(module, "DEFAULT_PARAMS", {}).items()}
    kw = dict(defaults)
    kw.update({k: v for k, v in (best_params or {}).items()})
    return kw, defaults


def run_strategy(fn, df, best_params):
    path = os.path.join(ROOT, "augur_strategies", fn)
    if not os.path.exists(path):
        path = os.path.join(SHARED, "augur_strategies", fn)
    m = _mod(path, fn.replace(".py", "_fb"))
    kw, defaults = _resolve_kwargs(m, best_params)
    sp = inspect.signature(m.run_backtest).parameters
    hk = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    if not hk:
        kw = {k: v for k, v in kw.items() if k in sp}
    ex = {}
    if "volumes" in sp or hk:
        ex["volumes"] = df["volume"].values if "volume" in df else None
    if "day_id" in sp or hk:
        ex["day_id"] = df["day_id"].values
    if "index" in sp or hk:
        ex["index"] = df["_dt"]
    try:
        r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values,
                           df["close"].values, return_trades=True, **ex, **kw)
    except TypeError:
        # a best_params key the file's own signature does not accept (no **kw
        # catch-all) — fall back to the file's own DEFAULT_PARAMS defaults only.
        r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values,
                           df["close"].values, return_trades=True, **ex, **defaults)
    if not r or not r.get("trades"):
        return None
    return [(int(t[0]), int(t[1]), float(t[2])) for t in r["trades"]]


# ─────────────────────────────────────────────────────────────────────────────
# build one leg — trade list + causal feature matrix — CACHED to a pickle
# ─────────────────────────────────────────────────────────────────────────────

def build_leg(leg, quick=False):
    cache_fp = os.path.join(CACHE_DIR, f"{leg['key']}.pkl")
    if os.path.exists(cache_fp):
        with open(cache_fp, "rb") as f:
            data = pickle.load(f)
        # a quick-mode cache never has macro columns; a full run needs to redo the
        # (cheap) macro join on top of an existing quick cache rather than re-run
        # the whole strategy.
        if quick or data.get("ext_available") or data.get("ext_tried_full"):
            print(f"[{leg['key']}] using cached trades (n={data['n']})")
            return data
        print(f"[{leg['key']}] cached trades found but macro was never fetched — retrying macro only")
        data = _add_macro(data)
        with open(cache_fp, "wb") as f:
            pickle.dump(data, f)
        return data

    print(f"[{leg['key']}] {leg['label']} — resolving config from Firestore...")
    cfg = resolve_leg_config(leg)
    print(f"[{leg['key']}] {cfg['instrument']} {cfg['timeframe']} {cfg['session']} "
          f"{cfg['date_from']}..{cfg['date_to']}  cost_pts={cfg['cost_pts']} mult={cfg['mult']} "
          f"source={cfg['parity_source']}")
    df = load(cfg["instrument"], cfg["timeframe"], cfg["session"], cfg["date_from"], cfg["date_to"])
    print(f"[{leg['key']}] loaded {len(df)} bars, running strategy {leg['file']}...")
    trades = run_strategy(leg["file"], df, cfg["best_params"])
    if not trades:
        raise RuntimeError(f"{leg['key']}: strategy produced no trades")
    t = pd.DataFrame(trades, columns=["eb", "xb", "pnl"])
    eb = t["eb"].to_numpy(int)
    usd = (t["pnl"].to_numpy(float) - cfg["cost_pts"]) * cfg["mult"]
    entry_date = pd.DatetimeIndex(df["_dt"]).date[eb]
    lockbox_from = _lockbox_from_date(cfg)
    lb = entry_date >= lockbox_from
    n = len(usd)
    print(f"[{leg['key']}] {n} trades  net ${usd.sum():,.0f}  pre-lockbox n={int((~lb).sum())}  "
          f"lockbox n={int(lb.sum())}")

    print(f"[{leg['key']}] building causal feature matrix...")
    idx = pd.DatetimeIndex(df["_dt"])
    arrays = dict(close=df["close"].values, high=df["high"].values, low=df["low"].values,
                 open=df["open"].values, day_id=df["day_id"].values, index=idx)
    Fc, names = ml_gate.entry_features_causal(arrays)
    name_to_j = {nm: j for j, nm in enumerate(names)}

    day_date_by_id = df.groupby("day_id")["_dt"].first().dt.date

    X = {}
    daily_series = {}
    for nm in BAR_COLS:
        j = name_to_j.get(nm)
        if j is None:
            continue
        col = Fc[:, j]
        X[nm] = col[eb]                                # already causal-safe at bar i's open
        proxy = pd.Series(col, index=df["day_id"].to_numpy()).groupby(level=0).last()
        proxy.index = day_date_by_id.reindex(proxy.index).to_numpy()
        daily_series[nm] = proxy.dropna().sort_index()

    comp = hourly_compression(df)
    comp_f = comp.astype(float)
    X["compressed_60m"] = comp_f[np.clip(eb - 1, 0, len(comp_f) - 1)]
    proxy = pd.Series(comp_f, index=df["day_id"].to_numpy()).groupby(level=0).last()
    proxy.index = day_date_by_id.reindex(proxy.index).to_numpy()
    daily_series["compressed_60m"] = proxy.dropna().sort_index()

    daily_int = ctx.build_internal_daily(idx, df["open"].values, df["high"].values,
                                         df["low"].values, df["close"].values)
    for nm in daily_int.columns:
        daily_series[nm] = daily_int[nm].dropna()
        X[nm] = daily_int[nm].reindex(entry_date).to_numpy()

    struct = build_structure_daily(idx, df["open"].values, df["high"].values,
                                   df["low"].values, df["close"].values)
    for nm in struct.columns:
        daily_series[nm] = struct[nm].dropna()
        X[nm] = struct[nm].reindex(entry_date).to_numpy()

    Xdf = pd.DataFrame(X)
    data = dict(key=leg["key"], cfg=cfg, eb=eb, usd=usd, entry_date=entry_date, lb=lb,
               X=Xdf, daily_series=daily_series, ext_available=False, ext_tried_full=False,
               n=n, net_pre=float(usd[~lb].sum()), net_lb=float(usd[lb].sum()),
               n_pre=int((~lb).sum()), n_lb=int(lb.sum()))

    if not quick:
        data = _add_macro(data, entry_date_override=entry_date, idx_override=idx)

    with open(cache_fp, "wb") as f:
        pickle.dump(data, f)
    return data


def _add_macro(data, entry_date_override=None, idx_override=None):
    entry_date = entry_date_override if entry_date_override is not None else data["entry_date"]
    try:
        ext = ctx.fetch_external_daily(str(min(entry_date)), str(max(entry_date)))
    except Exception:
        ext = None
    data["ext_tried_full"] = True
    if ext is not None and len(ext):
        data["ext_available"] = True
        for nm in ext.columns:
            data["daily_series"][nm] = ext[nm].dropna()
            data["X"][nm] = ext[nm].reindex(entry_date).to_numpy()
    return data


# ─────────────────────────────────────────────────────────────────────────────
# scoring — reuses augur_engine.context's private stats primitives, applied to
# a per-TRADE feature matrix (the bar-level group needs per-trade, not per-day,
# granularity — see module docstring)
# ─────────────────────────────────────────────────────────────────────────────

def _probe_columns(Xp, seed=SEED, k=3):
    cov = sorted(Xp.columns, key=lambda c: -int(Xp[c].notna().sum()))
    if not cov:
        return {}
    src = [cov[i % len(cov)] for i in range(k)]
    out = {}
    for i, col in enumerate(src):
        rng = np.random.default_rng(int(seed) + 9973 * (i + 1))
        vals = Xp[col].to_numpy(copy=True)
        perm = rng.permutation(len(vals))
        out[f"__probe{i}__"] = vals[perm]
    return out


def _rho_vs_y(x, y):
    m = ~np.isnan(x)
    if m.sum() < ctx.MIN_FEATURE_TRADES:
        return 0.0
    xv, yv = x[m], y[m]
    if np.ptp(xv) <= 0 or np.ptp(yv) <= 0:
        return 0.0
    return float(ctx._pearson(ctx._rank(xv), ctx._rank(yv)))


def _lift_threshold_spec(x):
    """Group-membership rule fixed from OBSERVED (pre-lockbox) data: binary (exactly
    two distinct non-nan values) -> HIGH=max value, LOW=min value. Continuous ->
    HIGH = top tercile, LOW = bottom tercile via np.quantile([1/3, 2/3]) thresholds.
    Returns (kind, lo_thresh_or_val, hi_thresh_or_val); kind="degenerate" when the
    feature has <=1 distinct value (no possible split)."""
    xv = np.asarray(x, float)
    u = np.unique(xv[~np.isnan(xv)])
    if len(u) <= 1:
        return ("degenerate", 0.0, 0.0)
    if len(u) == 2:
        return ("binary", float(u.min()), float(u.max()))
    q_lo, q_hi = np.quantile(xv[~np.isnan(xv)], [1.0 / 3, 2.0 / 3])
    return ("cont", float(q_lo), float(q_hi))


def _lift_masks(xv, spec):
    kind, lo_t, hi_t = spec
    xv = np.asarray(xv, float)
    if kind == "degenerate":
        z = np.zeros(xv.shape, dtype=bool)
        return z, z
    if kind == "binary":
        return (xv == hi_t), (xv == lo_t)
    return (xv >= hi_t), (xv <= lo_t)


def _lift_r(r_vals, hi_mask, lo_mask):
    """mean R in HIGH minus mean R in LOW; None if either group is empty."""
    if not hi_mask.any() or not lo_mask.any():
        return None
    r_vals = np.asarray(r_vals, float)
    return float(np.nanmean(r_vals[hi_mask]) - np.nanmean(r_vals[lo_mask]))


def _block_lift_ci(rvals, hi_mask, lo_mask, day_code, n_days, block_days, n_boot, seed):
    """95% CI for lift_r from the SAME moving-block-of-trading-days bootstrap as
    ctx._block_bootstrap_ci (see that function's docstring), applied to the lift
    statistic (mean R in HIGH minus mean R in LOW) instead of rank correlation.
    Group membership (hi_mask/lo_mask) is FIXED from the observed data — each draw
    only reweights which trades' days are covered by the resampled blocks, per the
    module's LIFT DEFINITION ("group membership fixed per trade")."""
    rng = np.random.default_rng(int(seed))
    n_boot = int(n_boot); n_days = int(n_days)
    block_days = int(max(1, min(int(block_days), n_days)))
    n_blocks = int(np.ceil(n_days / block_days))
    starts = rng.integers(0, n_days, size=(n_boot, n_blocks))
    offsets = np.arange(block_days)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n_days       # circular wrap
    idx = idx.reshape(n_boot, n_blocks * block_days)[:, :n_days]
    mult = np.zeros((n_boot, n_days), dtype=np.int32)
    rows_ = np.repeat(np.arange(n_boot), n_days)
    np.add.at(mult, (rows_, idx.ravel()), 1)
    W = mult[:, day_code].astype(float)                     # (n_boot, n_obs)
    r = np.asarray(rvals, float)
    Wh = W * hi_mask[None, :].astype(float)
    Wl = W * lo_mask[None, :].astype(float)
    swh = Wh.sum(axis=1); swl = Wl.sum(axis=1)
    swh_safe = np.where(swh > 0, swh, 1.0)
    swl_safe = np.where(swl > 0, swl, 1.0)
    mh = (Wh * r[None, :]).sum(axis=1) / swh_safe
    ml = (Wl * r[None, :]).sum(axis=1) / swl_safe
    lift_boot = mh - ml
    lo, hi = np.percentile(lift_boot, [2.5, 97.5])
    return float(lo), float(hi)


def _lift_perm_pvalue(x, r_vals, spec, obs_lift, day_code, n_days, group_kind,
                      n_perm=LIFT_N_PERM, seed=SEED, block_perm_days=LIFT_BLOCK_PERM_DAYS):
    """Two-sided permutation p-value for lift_r, at DAY granularity — see module
    LIFT DEFINITION.

    group_kind == "day" (daily/macro/structure features -- one value per calendar
    day, already joined by date): permutes which day's feature ROW each day
    receives. Trades keep their own day, so within-day clustering is preserved.

    group_kind == "bar" (bar/state features that can vary within a day, e.g.
    momentum read at the trade's own entry bar, or the 60-min compression flag):
    a whole-day reassignment wouldn't touch the intraday variation these features
    carry, so instead this permutes per-trade feature VALUES within contiguous
    blocks of ~21 trading days (`block_perm_days`).

    Both schemes shuffle the underlying value MULTISET, not the trades' R, so the
    total HIGH/LOW group sizes are invariant across draws -- group membership is
    recomputed each draw from the fixed thresholds in `spec`, applied to the
    permuted values (unlike the CI bootstrap, which keeps membership fixed)."""
    rng = np.random.default_rng(int(seed))
    x = np.asarray(x, float)
    r_vals = np.asarray(r_vals, float)
    n_days = int(n_days)
    hits = 0
    if group_kind == "day":
        day_val = np.zeros(n_days)
        seen = np.zeros(n_days, dtype=bool)
        for i, c in enumerate(day_code):
            if not seen[c]:
                day_val[c] = x[i]
                seen[c] = True
        for _ in range(int(n_perm)):
            perm = rng.permutation(n_days)
            xb = day_val[perm][day_code]
            hb, lb = _lift_masks(xb, spec)
            lp = _lift_r(r_vals, hb, lb)
            lp = 0.0 if lp is None else lp
            if abs(lp) >= abs(obs_lift):
                hits += 1
    else:
        chunks = []
        for start in range(0, n_days, block_perm_days):
            block_ids = set(range(start, min(start + block_perm_days, n_days)))
            idx = np.where(np.isin(day_code, list(block_ids)))[0]
            if len(idx) > 1:
                chunks.append(idx)
        for _ in range(int(n_perm)):
            xb = x.copy()
            for idx in chunks:
                xb[idx] = x[idx[rng.permutation(len(idx))]]
            hb, lb = _lift_masks(xb, spec)
            lp = _lift_r(r_vals, hb, lb)
            lp = 0.0 if lp is None else lp
            if abs(lp) >= abs(obs_lift):
                hits += 1
    return (hits + 1) / (int(n_perm) + 1)


def score_leg(data):
    X, y, days, lb = data["X"], data["usd"], np.asarray(data["entry_date"]), data["lb"]
    pre = ~lb
    Xp = X.loc[pre].reset_index(drop=True)
    yp = y[pre]
    dp = days[pre]
    Xl = X.loc[lb].reset_index(drop=True)
    yl = y[lb]

    # R unit: leg's average LOSING trade in $, PRE-LOCKBOX only (module LIFT
    # DEFINITION). Fixed once per leg; used to convert both pre-lockbox and
    # lockbox dollar PnL into R for every lift computation below.
    losers = yp[yp < 0]
    r_unit = float(np.mean(np.abs(losers))) if len(losers) else 1.0
    if not np.isfinite(r_unit) or r_unit <= 0:
        r_unit = 1.0
    rp = yp / r_unit
    rl = yl / r_unit

    probes = _probe_columns(Xp)
    probe_rhos = [_rho_vs_y(v, yp) for v in probes.values()]
    probe_max_abs_rho = max((abs(r) for r in probe_rhos), default=0.0)
    probe_lifts = []
    for v in probes.values():
        pspec = _lift_threshold_spec(v)
        phi, plo = _lift_masks(v, pspec)
        plift = _lift_r(rp, phi, plo)
        if plift is not None:
            probe_lifts.append(abs(plift))
    probe_max_abs_lift = max(probe_lifts, default=0.0)

    rows, order_names, pvals = {}, [], []
    lift_rows, lift_order_names, lift_pvals = {}, [], []
    for nm in FEATURE_NAMES:
        if nm not in Xp.columns:
            rows[nm] = None
            lift_rows[nm] = None
            continue
        xv = Xp[nm].to_numpy(float)
        yv = np.asarray(yp, float)
        rv = np.asarray(rp, float)
        dv = np.asarray(dp)
        m = ~np.isnan(xv)
        xv, yv, dv, rv = xv[m], yv[m], dv[m], rv[m]
        n = len(xv)
        if n < ctx.MIN_FEATURE_TRADES or np.ptp(xv) <= 0 or np.ptp(yv) <= 0:
            rows[nm] = None
            lift_rows[nm] = None
            continue
        uniq_days, day_code = np.unique(dv, return_inverse=True)
        if len(uniq_days) < ctx.MIN_FEATURE_DAYS:
            rows[nm] = None
            lift_rows[nm] = None
            continue
        rx, ry = ctx._rank(xv), ctx._rank(yv)
        rho = ctx._pearson(rx, ry)
        p, _method = ctx._pvalue(xv, yv, rho, dv, seed=SEED)

        dser = data["daily_series"].get(nm)
        if dser is not None and len(dser) >= 30:
            autocorr, persistence = ctx._autocorr_and_persistence(dser)
        else:
            autocorr, persistence = 0.0, float(ctx.BLOCK_DAYS_MIN)
        block_days = ctx._block_days_for(persistence)
        ci_lo, ci_hi = ctx._block_bootstrap_ci(rx, ry, day_code, len(uniq_days), block_days,
                                               N_BOOT, SEED)
        beats_probe = bool(abs(rho) > probe_max_abs_rho)
        rows[nm] = dict(rho=float(rho), ci_lo=ci_lo, ci_hi=ci_hi, p=float(p), n=n,
                        beats_probe=beats_probe)
        order_names.append(nm)
        pvals.append(float(p))

        # ── LIFT (tail-aware second statistic; see module LIFT DEFINITION) ──
        spec = _lift_threshold_spec(xv)
        hi_mask, lo_mask = _lift_masks(xv, spec)
        if spec[0] == "degenerate" or hi_mask.sum() < LIFT_MIN_GROUP or lo_mask.sum() < LIFT_MIN_GROUP:
            lift_rows[nm] = None
        else:
            lift_val = _lift_r(rv, hi_mask, lo_mask)
            l_ci_lo, l_ci_hi = _block_lift_ci(rv, hi_mask, lo_mask, day_code, len(uniq_days),
                                              block_days, N_BOOT, SEED)
            gkind = GROUP_KIND.get(FEATURE_GROUP.get(nm), "day")
            l_p = _lift_perm_pvalue(xv, rv, spec, lift_val, day_code, len(uniq_days), gkind)
            lift_beats_probe = bool(abs(lift_val) > probe_max_abs_lift)
            lift_rows[nm] = dict(lift_r=lift_val, lift_lo=l_ci_lo, lift_hi=l_ci_hi, p=l_p,
                                 beats_probe=lift_beats_probe, spec=spec)
            lift_order_names.append(nm)
            lift_pvals.append(l_p)

    qmap = {}
    if order_names:
        qvals = ctx._bh_fdr(pvals)
        qmap = {nm: float(q) for nm, q in zip(order_names, qvals)}

    lift_qmap = {}
    if lift_order_names:
        lqvals = ctx._bh_fdr(lift_pvals)
        lift_qmap = {nm: float(q) for nm, q in zip(lift_order_names, lqvals)}

    out = {}
    for nm in FEATURE_NAMES:
        r = rows.get(nm)
        if r is None:
            out[nm] = None
            continue
        q = qmap.get(nm, 1.0)
        ci_excl0 = bool((r["ci_lo"] > 0 and r["ci_hi"] > 0) or (r["ci_lo"] < 0 and r["ci_hi"] < 0))
        survives = bool(q < FDR_Q and ci_excl0 and r["beats_probe"])

        lb_rho, lb_n, lb_agrees = None, 0, None
        if nm in Xl.columns:
            xl = Xl[nm].to_numpy(float)
            yl_ = np.asarray(yl, float)
            m = ~np.isnan(xl)
            xl_m, yl_m = xl[m], yl_[m]
            lb_n = int(len(xl_m))
            if lb_n >= ctx.MIN_FEATURE_TRADES and np.ptp(xl_m) > 0 and np.ptp(yl_m) > 0:
                lb_rho = float(ctx._pearson(ctx._rank(xl_m), ctx._rank(yl_m)))
            if lb_rho is not None and lb_n >= LOCKBOX_MIN_TRADES:
                lb_agrees = bool(np.sign(lb_rho) == np.sign(r["rho"]))

        cell = dict(rho=round(r["rho"], 4), ci_lo=round(r["ci_lo"], 4), ci_hi=round(r["ci_hi"], 4),
                    q=round(q, 4), n=int(r["n"]), survives=survives, beats_probe=r["beats_probe"],
                    lb_rho=(round(lb_rho, 4) if lb_rho is not None else None), lb_n=lb_n,
                    lb_agrees=lb_agrees)

        # ── merge in LIFT keys (null where not computable — see LIFT DEFINITION) ──
        lr = lift_rows.get(nm)
        if lr is None:
            cell.update(lift_r=None, lift_lo=None, lift_hi=None, lift_p=None, lift_q=None,
                       lift_beats_probe=None, lift_survives=None, lb_lift_r=None,
                       lb_lift_agrees=None)
        else:
            lq = lift_qmap.get(nm, 1.0)
            lift_ci_excl0 = bool((lr["lift_lo"] > 0 and lr["lift_hi"] > 0)
                                 or (lr["lift_lo"] < 0 and lr["lift_hi"] < 0))
            lift_survives = bool(lq < FDR_Q and lift_ci_excl0 and lr["beats_probe"])

            lb_lift_r, lb_lift_agrees = None, None
            if nm in Xl.columns:
                xl = Xl[nm].to_numpy(float)
                hi_l, lo_l = _lift_masks(xl, lr["spec"])
                n_hi_l, n_lo_l = int(hi_l.sum()), int(lo_l.sum())
                if n_hi_l > 0 and n_lo_l > 0:
                    lb_lift_r = _lift_r(np.asarray(rl, float), hi_l, lo_l)
                if (lb_lift_r is not None and n_hi_l >= LB_LIFT_MIN_TRADES
                        and n_lo_l >= LB_LIFT_MIN_TRADES):
                    lb_lift_agrees = bool(np.sign(lb_lift_r) == np.sign(lr["lift_r"]))

            cell.update(lift_r=round(lr["lift_r"], 4), lift_lo=round(lr["lift_lo"], 4),
                       lift_hi=round(lr["lift_hi"], 4), lift_p=round(lr["p"], 4),
                       lift_q=round(lq, 4), lift_beats_probe=lr["beats_probe"],
                       lift_survives=lift_survives,
                       lb_lift_r=(round(lb_lift_r, 4) if lb_lift_r is not None else None),
                       lb_lift_agrees=lb_lift_agrees)
        out[nm] = cell
    return out


# ─────────────────────────────────────────────────────────────────────────────
# promotion across legs/families
# ─────────────────────────────────────────────────────────────────────────────

_TIER_RANK = {"PROMOTED": 0, "WATCH": 1, "NONE": 2}


def _basis_verdict(per_leg, fam_of, survives_key, value_key, lb_key):
    """One basis's (rank or lift) verdict pieces for a single feature. Same rule
    as the original rank-only `promote`: group surviving legs by family + sign,
    take the sign with the most agreeing families, PROMOTED needs >=3 families
    AND lockbox agreement in every one of them, WATCH is 2 families or a lockbox
    miss, NONE otherwise. `value_key`/`lb_key` pick which cell fields to read so
    the exact same logic serves both the rank cells (rho/lb_agrees) and the lift
    cells (lift_r/lb_lift_agrees)."""
    fam_legs = {}                                       # family -> [(legkey, sign, lb_ok)]
    for legkey, c in per_leg.items():
        if not c or not c.get(survives_key):
            continue
        val = c.get(value_key)
        if val is None:
            continue
        fam = fam_of.get(legkey)
        sign = "+" if val > 0 else "-"
        fam_legs.setdefault(fam, []).append((legkey, sign, c.get(lb_key)))

    sign_fams = {"+": set(), "-": set()}
    for fam, entries in fam_legs.items():
        signs_here = {s for _, s, _ in entries}
        if len(signs_here) == 1:
            sign_fams[signs_here.pop()].add(fam)

    best_sign, best_fams = None, set()
    for s in ("+", "-"):
        if len(sign_fams[s]) > len(best_fams):
            best_sign, best_fams = s, sign_fams[s]

    any_survived = any(fam_legs.values())
    if best_sign is None or len(best_fams) < 2:
        return dict(tier="NONE", sign=("mixed" if any_survived else "n/a"),
                   families_agree=[], legs_agree=[], lb_agree_count=0)

    agree_legs = [lk for fam in best_fams for lk, s, _ in fam_legs[fam] if s == best_sign]
    fam_lb_ok = {}
    for fam in best_fams:
        entries = [e for e in fam_legs[fam] if e[1] == best_sign]
        fam_lb_ok[fam] = any(e[2] is True for e in entries)
    lb_agree_count = sum(1 for f in best_fams if fam_lb_ok[f])
    lb_ok_all = all(fam_lb_ok[f] for f in best_fams)
    fams_sorted = sorted(best_fams)

    if len(best_fams) >= PROMOTE_FAMILIES and lb_ok_all:
        tier = "PROMOTED"
    else:
        tier = "WATCH"

    return dict(tier=tier, sign=best_sign, families_agree=fams_sorted, legs_agree=agree_legs,
               lb_agree_count=lb_agree_count)


def _reason(nm, label_of, tier, basis, sign, families_agree, rv, lv):
    label = label_of.get(nm, nm)
    if tier == "NONE":
        return (f"{label} did not clear the significance bar in at least two families with the "
               "same sign, on rank order or on average dollars per trade (lift).")
    word = "helped" if sign == "+" else "hurt"
    fams_str = ", ".join(families_agree)
    metric_name = {"rank": "on rank order (Spearman)",
                  "lift": "on average dollars per trade (lift)",
                  "both": "on both rank order (Spearman) and average dollars per trade (lift)"}[basis]

    if tier == "PROMOTED":
        core = (f"{label} {word} in {fams_str} {metric_name}, and the direction repeated in each "
               "of their lockbox reads")
    elif len(families_agree) >= PROMOTE_FAMILIES:
        core = (f"{label} {word} in all of {fams_str} {metric_name}, but the lockbox direction did "
               "not repeat in at least one of them")
    else:
        core = (f"{label} {word} in {fams_str} {metric_name} — only {len(families_agree)} "
               f"famil{'y' if len(families_agree) == 1 else 'ies'}, short of the "
               f"{PROMOTE_FAMILIES}-family bar")

    if basis == "rank":
        other_ok = lv["tier"] != "NONE"
        tail = (", and also leaned the same way on average dollars per trade (lift)." if other_ok
               else ", though not on average dollars per trade (lift).")
    elif basis == "lift":
        other_ok = rv["tier"] != "NONE"
        tail = (", and also leaned the same way on rank order (Spearman)." if other_ok
               else ", though not on rank order (Spearman).")
    else:
        tail = "."
    return core + tail


def promote(cells, features_meta, legs):
    """cells: {feature_name: {legkey: cell_dict_or_None}}. legs: [{key, family, ...}].

    Runs the verdict rule twice per feature — once on the RANK basis (rho /
    survives / lb_agrees, as before) and once on the LIFT basis (lift_r /
    lift_survives / lb_lift_agrees) — and keeps whichever reaches the stronger
    tier (PROMOTED beats WATCH beats NONE). When both bases reach the SAME tier,
    `basis` is "both" and the basis with more agreeing families is reported (ties
    favor rank). Cells built without any lift_* keys (e.g. this module's own
    tests) make the lift basis evaluate to NONE for every feature, so a feature
    that only ever cleared the rank bar is untouched — its output is identical
    to the pre-LIFT `promote`."""
    fam_of = {l["key"]: l["family"] for l in legs}
    label_of = {f["name"]: f["label"] for f in features_meta}
    verdicts = []
    for nm in [f["name"] for f in features_meta]:
        per_leg = cells.get(nm, {})
        rv = _basis_verdict(per_leg, fam_of, "survives", "rho", "lb_agrees")
        lv = _basis_verdict(per_leg, fam_of, "lift_survives", "lift_r", "lb_lift_agrees")

        # The two tests must AGREE on direction before either can vouch for the other.
        # Rank says "helps" while lift says "hurts" (or vice versa) means the ordering
        # and the dollars point opposite ways - a tail-vs-bulk contradiction, not
        # evidence. Such a feature is capped at WATCH and labelled a conflict.
        conflict = (rv["tier"] != "NONE" and lv["tier"] != "NONE"
                    and rv["sign"] in ("+", "-") and lv["sign"] in ("+", "-")
                    and rv["sign"] != lv["sign"])
        if conflict:
            winner = rv if _TIER_RANK[rv["tier"]] <= _TIER_RANK[lv["tier"]] else lv
            basis = "conflict"
            tier = "WATCH"
            word = {"+": "helped", "-": "hurt"}
            fams = sorted(set(rv["families_agree"]) | set(lv["families_agree"]))
            reason = (f"{label_of.get(nm, nm)}: the two tests disagree - by rank order it "
                      f"{word[rv['sign']]} ({', '.join(rv['families_agree'])}) but by average "
                      f"dollars per trade it {word[lv['sign']]} ({', '.join(lv['families_agree'])}). "
                      f"A feature cannot be promoted until both readings point the same way.")
            verdicts.append(dict(feature=nm, tier=tier, sign="mixed", families_agree=fams,
                                 legs_agree=sorted(set(rv["legs_agree"]) | set(lv["legs_agree"])),
                                 lb_agree_count=min(rv["lb_agree_count"], lv["lb_agree_count"]),
                                 basis=basis, reason=reason))
            continue

        if _TIER_RANK[rv["tier"]] < _TIER_RANK[lv["tier"]]:
            winner, basis = rv, "rank"
        elif _TIER_RANK[lv["tier"]] < _TIER_RANK[rv["tier"]]:
            winner, basis = lv, "lift"
        else:
            winner = rv if len(rv["families_agree"]) >= len(lv["families_agree"]) else lv
            basis = "both"

        reason = _reason(nm, label_of, winner["tier"], basis, winner["sign"],
                         winner["families_agree"], rv, lv)
        verdicts.append(dict(feature=nm, tier=winner["tier"], sign=winner["sign"],
                             families_agree=winner["families_agree"], legs_agree=winner["legs_agree"],
                             lb_agree_count=winner["lb_agree_count"], basis=basis, reason=reason))

    verdicts.sort(key=lambda v: (_TIER_RANK[v["tier"]], -len(v["families_agree"])))
    return verdicts


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip fetch_external_daily (no network)")
    ap.add_argument("--verdicts-only", action="store_true",
                    help="re-run only the promotion rule on the existing docs/feature_board.json (no engine, no stats)")
    a = ap.parse_args()

    if a.verdicts_only:
        json_fp = os.path.join(DOCS_OUT, "feature_board.json")
        with open(json_fp, encoding="utf-8") as f:
            out = json.load(f)
        out["verdicts"] = promote(out["cells"], out["features"], out["legs"])
        with open(json_fp, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, default=lambda o: None)
        write_md(out)
        print(f"re-judged {json_fp}: " + ", ".join(
            f"{v['feature']} {v['tier']}/{v['basis']}" for v in out["verdicts"] if v["tier"] != "NONE"))
        return out

    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(DOCS_OUT, exist_ok=True)

    leg_data = {}
    leg_out = []
    for leg in LEGS:
        data = build_leg(leg, quick=a.quick)
        leg_data[leg["key"]] = data
        cfg = data["cfg"]
        expected = (cfg.get("parity_expected") or {}).get("full")
        got_net = float(data["usd"].sum())
        ok = None
        if expected and expected.get("net_pts") is not None:
            exp_net = float(expected["net_pts"]) * cfg["mult"]
            ok = bool(exp_net != 0 and abs(got_net - exp_net) / abs(exp_net) <= 0.02)
        parity = dict(source=cfg["parity_source"],
                     expected_net=(round(float(expected["net_pts"]) * cfg["mult"], 2)
                                  if expected and expected.get("net_pts") is not None else None),
                     got_net=round(got_net, 2), ok=ok)
        leg_out.append(dict(key=leg["key"], family=leg["family"], label=leg["label"], file=leg["file"],
                            run=leg["run"], instrument=cfg["instrument"], timeframe=cfg["timeframe"],
                            session=cfg["session"], window=[cfg["date_from"], cfg["date_to"]],
                            lockbox_from=str(_lockbox_from_date(cfg)), n_pre=data["n_pre"],
                            n_lb=data["n_lb"], net_pre=round(data["net_pre"], 2),
                            net_lb=round(data["net_lb"], 2), parity=parity))
        print(f"[{leg['key']}] PARITY  got=${got_net:,.0f}  "
              f"expected={'n/a' if parity['expected_net'] is None else '$'+format(parity['expected_net'], ',.0f')}"
              f"  ok={parity['ok']}")

    print("\nscoring features per leg...")
    cells = {f["name"]: {} for f in FEATURES}
    for leg in LEGS:
        sc = score_leg(leg_data[leg["key"]])
        for nm, c in sc.items():
            cells[nm][leg["key"]] = c

    features_out = [dict(name=f["name"], label=f["label"], group=f["group"], desc=f["desc"])
                    for f in FEATURES]

    verdicts = promote(cells, FEATURES, LEGS)

    out = dict(
        generated=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        version=1,
        rule=dict(promote_families=PROMOTE_FAMILIES, fdr_q=FDR_Q,
                 lockbox_min_trades=LOCKBOX_MIN_TRADES,
                 note=("A feature is PROMOTED only when it clears the significance bar with the "
                      "same sign in at least 3 different strategy families, and its direction "
                      "repeats in the last-12-months lockbox of every one of those families. The "
                      "rule runs on two bases, rank and lift (see lift_note) — a feature can be "
                      "PROMOTED/WATCH on either one, or on both."),
                 lift_note=("LIFT is the difference in average profit, measured in R (the leg's own "
                           "typical losing trade), between the top third and bottom third of a "
                           "feature's trades — it catches an edge that shows up mainly in a few big "
                           "winners even when the trades' RANK ORDER (Spearman) shows nothing.")),
        legs=leg_out,
        features=features_out,
        cells=cells,
        verdicts=verdicts,
    )

    json_fp = os.path.join(DOCS_OUT, "feature_board.json")
    with open(json_fp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=lambda o: None)
    print(f"\nwrote {json_fp}")

    write_md(out)
    return out


def write_md(out):
    lines = []
    lines.append("# Cross-family feature board")
    lines.append("")
    lines.append(f"Rule: {out['rule']['note']}")
    lines.append("")
    lines.append("## Leg parity (reproduced locally vs the doc's own numbers)")
    lines.append("")
    lines.append("| leg | window | n pre / lb | net pre / lb | parity |")
    lines.append("|---|---|---|---|---|")
    any_bad = False
    for lg in out["legs"]:
        p = lg["parity"]
        if p["ok"] is False:
            any_bad = True
        parity_str = ("n/a (defaults, no doc)" if p["source"] == "defaults"
                      else ("PASS" if p["ok"] else f"MISMATCH (expected ${p['expected_net']:,.0f})"
                           if p["ok"] is not None else "n/a"))
        lines.append(f"| {lg['label']} | {lg['window'][0]}..{lg['window'][1]} | "
                    f"{lg['n_pre']} / {lg['n_lb']} | ${lg['net_pre']:,.0f} / ${lg['net_lb']:,.0f} | "
                    f"{parity_str} |")
    lines.append("")
    if any_bad:
        lines.append("**One or more legs did NOT reproduce within 2% of the doc's own net — see the "
                     "table above. Feature scores for those legs are still included but should be "
                     "read with that caveat.**")
        lines.append("")

    promoted = [v for v in out["verdicts"] if v["tier"] == "PROMOTED"]
    watch = [v for v in out["verdicts"] if v["tier"] == "WATCH"]
    lines.append(f"## PROMOTED ({len(promoted)})")
    lines.append("")
    if not promoted:
        lines.append("None cleared the 3-family + lockbox bar this round.")
    for v in promoted:
        lines.append(f"- **{v['feature']}** ({v['sign']}, {v['basis']}, {', '.join(v['families_agree'])}): "
                    f"{v['reason']}")
    lines.append("")
    lines.append(f"## WATCH ({len(watch)})")
    lines.append("")
    if not watch:
        lines.append("None.")
    for v in watch[:10]:
        lines.append(f"- {v['feature']} ({v['sign']}, {v['basis']}, {', '.join(v['families_agree'])}): "
                    f"{v['reason']}")
    lines.append("")

    lines.append("## LIFT — tail-aware second read")
    lines.append("")
    lines.append(out["rule"]["lift_note"])
    lines.append("")
    legs_meta = out["legs"]
    fam_of = {lg["key"]: lg["family"] for lg in legs_meta}
    label_of = {lg["key"]: lg["label"] for lg in legs_meta}

    lines.append("### `compressed_60m` on every leg — rank vs lift")
    lines.append("")
    lines.append("| leg | rank rho | rank survives | lift_r (R) | lift survives | lockbox lift agrees |")
    lines.append("|---|---|---|---|---|---|")
    comp_cells = out["cells"].get("compressed_60m", {})
    for lg in legs_meta:
        c = comp_cells.get(lg["key"])
        if not c:
            lines.append(f"| {lg['label']} | n/a | n/a | n/a | n/a | n/a |")
            continue
        lift_r_str = "n/a" if c.get("lift_r") is None else f"{c['lift_r']:+.3f}"
        lift_surv_str = "n/a" if c.get("lift_survives") is None else str(c["lift_survives"])
        lb_str = "n/a" if c.get("lb_lift_agrees") is None else str(c["lb_lift_agrees"])
        lines.append(f"| {lg['label']} | {c['rho']:+.4f} | {c['survives']} | {lift_r_str} | "
                    f"{lift_surv_str} | {lb_str} |")
    lines.append("")

    lift_hits = []
    for nm, per_leg in out["cells"].items():
        for legkey, c in (per_leg or {}).items():
            if c and c.get("lift_survives"):
                lift_hits.append((nm, legkey, c))
    lines.append(f"### Cells where lift_survives=true ({len(lift_hits)})")
    lines.append("")
    if not lift_hits:
        lines.append("None this round.")
    else:
        lines.append("| feature | leg | family | lift_r (R) | 95% CI | lockbox lift_r | lockbox agrees |")
        lines.append("|---|---|---|---|---|---|---|")
        for nm, legkey, c in sorted(lift_hits, key=lambda t: -abs(t[2]["lift_r"])):
            lb_r_str = "n/a" if c.get("lb_lift_r") is None else f"{c['lb_lift_r']:+.3f}"
            lb_ok_str = "n/a" if c.get("lb_lift_agrees") is None else str(c["lb_lift_agrees"])
            lines.append(f"| {nm} | {label_of.get(legkey, legkey)} | {fam_of.get(legkey, '?')} | "
                        f"{c['lift_r']:+.3f} | [{c['lift_lo']:+.3f}, {c['lift_hi']:+.3f}] | "
                        f"{lb_r_str} | {lb_ok_str} |")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("- The lockbox sign check is a light peek, not a second statistical test — treat "
                "`lb_agrees` as directional support, not proof.")
    lines.append("- NQDIP and ENGU-Q have the fewest lockbox trades of the four families, so their "
                "`lb_agrees` flags are the least reliable and most likely to be null (below 30 trades).")
    lines.append("- Shadow-probe and block-bootstrap constants are shared with "
                "`augur_engine/context.py` (MIN_FEATURE_TRADES, FDR_Q, block-days sizing) so this "
                "board's bar matches the site's own PARAM RELATIONSHIP panel.")

    md_fp = os.path.join(DOCS_OUT, "FEATURE_BOARD.md")
    with open(md_fp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {md_fp}")


if __name__ == "__main__":
    main()
