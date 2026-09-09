"""KEEL - the skill-gated expectancy tilt (built 2026-09-06, owner: "make your own ML").

A tilt with a conscience. It keeps what the existing overlays got right and fixes what the
evidence says they got wrong (138 gate-bearing runs swept: the crowned CUT has a median
lockbox delta of exactly $0; TILT is the only spending mode with a positive median; xgb is
the worst model out-of-sample in every mode).

  from the GATE (cut)  : causal entry features, rolling refit on trades finished before entry,
                         |pnl| sample weights.  CHANGED: no cut, ever - a trade is never deleted
                         (LO..HI size bounds, floor 0.5x), because cuts amputate the tail
                         winners that ARE the edge on low-win-rate strategies.
  from the TILT        : continuous size from the score.  CHANGED: the slope is EARNED, not
                         a-priori - scaled by the overlay's own demonstrated out-of-sample skill.
  from the HYBRID      : nothing (a floor pinned to a cut-off is a cut).
  from sizing.py       : the mean-1 / hard-cap discipline; "size, don't filter".
  from TTM round 6     : the 60m compression state as a FEATURE (coiled hours earn 2-3x EV R).
  from the model zoo   : logistic (the KISS member) + ExtraTrees, decorrelated biases,
                         each weighted ONLINE by its own record (ORB.md 4.28: the best
                         single model flips between instruments, so never bet on one).

Three structural ideas:
  1. TARGET = expectancy, not win-rate. The tree member regresses sign(R)*log1p(|R|)
     (R = pnl / average losing trade) - tail winners keep their rank instead of being
     truncated; the logistic member is |pnl|-weighted so its 0.5 is break-even. Members
     are combined in z-space, so calibration drift cannot poison the size.
  2. SKILL-GATED SLOPE. The overlay keeps a ledger of its OWN out-of-sample scores vs the
     realised pnl of every resolved trade. Skill = t-stat of g_i = pnl_i * z_i (the marginal
     dollars of a unit-slope tilt) over the last W resolved trades. trust = clip(t/2, 0, 1),
     per member (for stacking weights) and again for the combined score.
     size = clip(1 + K * trust * z, LO, HI). No demonstrated skill -> size 1 = the raw
     strategy. It cannot make a strategy materially worse than raw for long: it stands down.
  3. RECENCY. Sample weight *= exp(-age/TAU) trades, so a regime break fades out smoothly
     instead of being a hard refit cliff.

Iteration log (all four legs = NOISE #243, ORB #234 NQ + ES, ENGU-Q #265; pinned window
2010-06-07..2026-06-30, lockbox 2025-06-30, plus the untouched 2026-07-01..09-04 tail):
  v1  W 150 rank ledger, clip-5 target, equal-weight members.  NOISE pre-LB MAR 1.22 -> 2.06
      (best on the board) but the ledger is too noisy: it trusted ORB (no signal) and the
      clipped target cost ENGU-Q its 2020/2024 tail years.
  v2  W 600, dead-zone trust, log target, trust-weighted stacking.  Rank correlation is the
      WRONG skill metric for tail-driven legs: on ENGU-Q it trusted the Huber member (-$55k)
      and distrusted the logistic member (+$56k).
  v3  dollar ledger with the v2 dead zone: too strict - stood down 98% of the time.
  v4  dollar ledger, proportional trust (this file's default).  Neutral where there is no
      edge (ORB NQ/ES, ENGU-Q pre-LB: within $4k of raw), positive where there is (NOISE
      pre-LB +$54,829 / MAR 1.22 -> 1.63 with drawdown DOWN $2.4k; ENGU-Q lockbox +$15,410
      at MAR 7.22 vs 5.83). It does NOT out-earn the a-priori logistic TILT in-sample; it
      out-MARs it and never hurts. Standing: comparison-only in gate_validate, forward
      test as a PAPER leg. See BACKTESTING_STACK.md section 4 (KEEL) for the full table.
"""
import os
import datetime as _dt
import numpy as np
import pandas as pd

from augur_engine.ml_gate import entry_features, _CLOCK_FEATS, _stats  # noqa: F401

# -- constants -----------------------------------------------------------------
K_MAX = 0.5          # size change per z-unit at full trust
LO, HI = 0.5, 2.0    # size bounds (never 0: a trade is never deleted)
TAU = 400.0          # recency decay in trades (weight e^-1 at 400 trades old)
MIN_SKILL_N = 30     # ledger size before any trust is granted
MIN_HISTORY = 30     # same warm-up as the gate
REFIT_EVERY = 25     # same refit cadence as the gate
SEED = 42
# v1 (2026-09-06 first draft, pre-registered):  W 150, trust = clip(t/2), R clipped at 5,
#    members averaged with equal weight.
# v2 (after the 3-leg read + plateau sweep):     W 600 (rho sd ~0.04, so a no-signal leg like
#    ORB stays untrusted), DEAD ZONE trust = clip((t-1)/2) (nothing below t=1, full at t=3),
#    target = sign(R)*log1p(|R|) (tail winners keep their rank instead of being truncated -
#    the truncation cost ENGU-Q its 2020 and 2024 tail years), members STACKED ONLINE: each
#    member's z is weighted by its OWN ledger trust, then the combined score must earn trust
#    on its own ledger too.
CFG = {
    "v1": {"W": 150, "t_lo": 0.0, "t_hi": 2.0, "target": "clip5", "stack": "equal"},
    "v2": {"W": 600, "t_lo": 1.0, "t_hi": 3.0, "target": "log", "stack": "trust",
           "ledger": "rank", "members": ("logit", "et", "huber")},
    # v3: the ledger measures skill in DOLLARS - t-stat of g_i = pnl_i * z_i, the marginal P&L
    #    of a unit-slope tilt - instead of Spearman rank (rank ignores magnitude: on ENGU-Q it
    #    trusted the member that lost $55k and distrusted the one that made $56k). Huber dropped:
    #    corr 0.83 with logistic on ORB (same linear bias, minus the |pnl| weighting).
    "v3": {"W": 600, "t_lo": 1.0, "t_hi": 3.0, "target": "log", "stack": "trust",
           "ledger": "dollar", "members": ("logit", "et")},
    # v4: same dollar ledger, but the dead zone was a rank-ledger calibration; a fat-tailed
    #    dollar t-stat over 600 trades rarely reaches 1 even for a real edge (v3 stood down
    #    98% of the time on ENGU-Q). trust = clip(t/2): proportional from t=0, full at t=2.
    "v4": {"W": 600, "t_lo": 0.0, "t_hi": 2.0, "target": "log", "stack": "trust",
           "ledger": "dollar", "members": ("logit", "et")},
    # v5 (2026-09-07, owner: "earn more without adding drawdown"): same model and ledger as v4,
    #    only the size schedule moves. 288-cell read on the saved v4 walks, rule = pre-lockbox
    #    drawdown not worse than raw on the deployed legs: the passing cells form a plateau at
    #    floor 0.75 (never 1.0 - up-only sizing adds drawdown), slope 1.0-1.5, trust earned from
    #    t 0.5 to 1.0. This cell was chosen for the lockbox year too: NOISE LB drawdown exactly
    #    raw's. Second read on the spent window - the paper leg is the test.
    "v5": {"W": 600, "t_lo": 0.5, "t_hi": 1.0, "target": "log", "stack": "trust",
           "ledger": "dollar", "members": ("logit", "et"), "K": 1.5, "LO": 0.75, "HI": 2.0},
    # v6 (2026-09-07, pre-registered before it was run): v5 + a FAST-DISTRUST ledger. The 600-trade
    #    ledger is slow to notice that skill has faded (about a year of NOISE trades), and v5's
    #    steep slope turned that lag into 2x-sized losers in the #304 lockbox (DD -44.7k vs raw
    #    -24.5k). A second ledger of the SAME dollar statistic over the last 100 resolved trades
    #    can only CUT trust: cut = clip((t100 + 0.5) / 1.0, 0, 1). Slow to trust, fast to distrust.
    #    Plateau: fast windows 50-100 all work, 200 is too slow. Read on the runs' own stretches:
    #    #243 WF +$113k (+37%) at DD -23.1k vs -18.4k, LB +$5.7k at raw's DD, MAR 2.00 vs 1.83;
    #    #304 WF +$49k (+16%) at DD -13.9k vs -16.9k, LB -$2.7k at DD -28.4k vs -24.5k.
    "v6": {"W": 600, "t_lo": 0.5, "t_hi": 1.0, "target": "log", "stack": "trust",
           "ledger": "dollar", "members": ("logit", "et"), "K": 1.5, "LO": 0.75, "HI": 2.0,
           "fast": {"W": 100, "lo": -0.5, "hi": 0.5}},
    # v7 (2026-09-07) = v6 + SHADE WHEN WRONG. When the 100-trade fast ledger says the model is
    #    confidently wrong (t100 < -1), v6 only stands down to 1.0; v7 leans a little against the
    #    score instead: size = clip(1 - 0.5 * z, 0.75, 1.25). Active on ~10% of trades. Read on the
    #    runs' own stretches: walk-forward unchanged (#243 $414k, #304 $367k), lockbox up on BOTH
    #    NOISE runs with drawdown better on both (#243 $69,575 / DD -21.0k vs raw -22.1k, MAR 2.21
    #    vs 1.83; #304 $79,414 / DD -25.3k vs v6's -28.4k). Calendar-day fast windows and a
    #    drawdown brake were tried in the same pass and did not earn their keep.
    "v7": {"W": 600, "t_lo": 0.5, "t_hi": 1.0, "target": "log", "stack": "trust",
           "ledger": "dollar", "members": ("logit", "et"), "K": 1.5, "LO": 0.75, "HI": 2.0,
           "fast": {"W": 100, "lo": -0.5, "hi": 0.5},
           "shade": {"t": -1.0, "k": 0.5, "lo": 0.75, "hi": 1.25}},
    # v8 (2026-09-07) = SYMMETRIC shade. Grid over fast window x shade trigger x lean x bounds on
    #    both NOISE runs: every shade cell beats no-shade on the lockboxes and the harder the lean
    #    the more they earn, at ~2% of walk-forward. Full symmetry - lean against the score as
    #    hard as v5 leans with it - with the 50-trade fast window: #304 lockbox $103,078 vs raw
    #    $82,123 at identical DD; #243 lockbox $59,576 vs $60,615 at DD -19.9k vs -22.1k; WF
    #    +34% / +10%. Third rung of the forward ladder: K6 stand down, K7 mild lean, K8 full lean.
    "v8": {"W": 600, "t_lo": 0.5, "t_hi": 1.0, "target": "log", "stack": "trust",
           "ledger": "dollar", "members": ("logit", "et"), "K": 1.5, "LO": 0.75, "HI": 2.0,
           "fast": {"W": 50, "lo": -0.5, "hi": 0.5},
           "shade": {"t": -0.5, "k": 1.0, "lo": 0.5, "hi": 1.5}},
    # v9 (2026-09-07) = v8 with the 100-trade fast window, times an A-PRIORI compression multiplier:
    #    1.5x on trades entered while the 60m Bollinger/Keltner state is compressed (sq60_on, the
    #    TTM round-6 keeper: coiled-hour trades earn 2-3x EV R, lockbox-repeated on NOISE x2 + ORB).
    #    Not fitted here - the multiplier is the round-6 tilt at its moderate setting. Final size
    #    capped at 3x (sizing.py's cap). Read on the runs' own stretches: #243 WF $480,796 vs raw
    #    $303,685 (DD -21.3k vs -18.4k), LB $101,242 vs $60,615 at DD -18.3k (better); #304 WF
    #    $434,115 vs $316,495 (DD -18.0k vs -16.9k), LB $100,820 vs $82,123 at DD -29.6k vs -24.5k.
    #    2x was tried: more money, but #304 lockbox DD +43% - too much.
    "v9": {"W": 600, "t_lo": 0.5, "t_hi": 1.0, "target": "log", "stack": "trust",
           "ledger": "dollar", "members": ("logit", "et"), "K": 1.5, "LO": 0.75, "HI": 2.0,
           "fast": {"W": 100, "lo": -0.5, "hi": 0.5},
           "shade": {"t": -0.5, "k": 1.0, "lo": 0.5, "hi": 1.5},
           "comp": {"feature": "sq60_on", "mult": 1.5, "cap": 3.0}},
    # v10 (2026-09-08) = v9 with the 50-trade fast window. Chosen on year-by-year CONSISTENCY, not
    #    lockbox dollars: WF year-by-year t 3.41 vs 3.00 on #243 and 2.93 vs 2.11 on #304, WF drawdown
    #    better on both (#304 -14.4k vs raw -16.9k). Lockbox: #304 $121,069 (raw $82,123) at DD
    #    within 3%; #243 $70,527 (raw $60,615) at better DD. Graded-by-depth and strict-only
    #    compression both lose to the plain on/off rule. NOISE only (ENGU-Q K9 stays at v9).
    "v10": {"W": 600, "t_lo": 0.5, "t_hi": 1.0, "target": "log", "stack": "trust",
            "ledger": "dollar", "members": ("logit", "et"), "K": 1.5, "LO": 0.75, "HI": 2.0,
            "fast": {"W": 50, "lo": -0.5, "hi": 0.5},
            "shade": {"t": -0.5, "k": 1.0, "lo": 0.5, "hi": 1.5},
            "comp": {"feature": "sq60_on", "mult": 1.5, "cap": 3.0}},
    # v11 (2026-09-08) = v10 x an a-priori DAY-OF-WEEK tilt: 1.5x on Friday entries. Found by the
    #    same structural scan that found compression: Friday carries the highest EV R on both NOISE
    #    runs in BOTH walk-forward and lockbox (0.47/0.51 on #243, 0.39/0.38 on #304 vs ~0.25 other
    #    days). Year-by-year robustness of the tilt in WF: t 4.35 (9/10 years) on #243, 3.76 (9/10)
    #    on #304; lockbox 2/3 years on both. On top of v10: #243 WF $523,751 vs v10 $489,144 at DD
    #    -19.8k vs -22.2k (MAR 3.01), LB $86,074 vs $70,527 at DD -19.9k (raw -22.1k); #304 WF
    #    $490,614 at DD -16.6k (raw -16.9k), LB $139,016 vs $121,069 at DD -26.9k (raw -24.5k).
    #    NOISE only: fails ENGU-Q's lockbox (24h tape), and on ORB it costs WF drawdown.
    "v11": {"W": 600, "t_lo": 0.5, "t_hi": 1.0, "target": "log", "stack": "trust",
            "ledger": "dollar", "members": ("logit", "et"), "K": 1.5, "LO": 0.75, "HI": 2.0,
            "fast": {"W": 50, "lo": -0.5, "hi": 0.5},
            "shade": {"t": -0.5, "k": 1.0, "lo": 0.5, "hi": 1.5},
            "comp": {"feature": "sq60_on", "mult": 1.5, "cap": 3.0},
            "dow": {"4": 1.5, "cap": 3.0}},
    # v12 (2026-09-09) = v11 x an a-priori EVENT tilt: HALF SIZE on trades entered on a scheduled
    #    FOMC decision day BEFORE the 14:00 ET statement. The first new-information lever in the
    #    study - the Fed's own published calendar (tools/data/fomc_dates.txt), knowable years ahead.
    #    The pre-statement morning is the worst bucket found anywhere in this work: WF EV R -0.484
    #    (#243) / -0.426 (#304) against a +0.31 / +0.27 baseline; negative in IS, WF and the lockbox
    #    on BOTH runs (6 of 6 stretches); negative in 8 of 9 walk-forward years on both; the median
    #    trade loses; the worst single trade is only 13% of the hole, so it is broad, not a blow-up.
    #    Permutation test: against 4,000 random day-calendars of the same size the real FOMC calendar
    #    lands in the bottom 0.10% on both runs (z -2.71 / -2.58). Three placebos FAIL as they should
    #    - the morning BEFORE a decision day, a random matched day-set, and an every-morning shrink
    #    of the same dollar size all LOSE money - so the tilt is keyed to the events, not to mornings.
    #    On top of v11, ENGINE-VERIFIED through keel_walk on freshly backtested trade lists (4,429 and
    #    4,833 trades; 87 and 91 tagged pre-statement, 2.0% / 1.9%, every one exactly halved):
    #      #243 WF $523,751 -> $532,376 at IDENTICAL drawdown -19,810 (MAR 3.01 -> 3.06)
    #      #243 LB  $86,074 ->  $90,746 at -19,804 vs -19,862, i.e. BETTER (MAR 2.89 -> 3.06)
    #      #304 WF $490,614 -> $497,207 at -16,349 vs -16,599, BETTER (MAR 3.37 -> 3.46)
    #      #304 LB $139,016 -> $144,266 at identical -26,920 (MAR 3.45 -> 3.58)
    #    Reproduce all of it with `python tools/keel_event_check.py` (exits non-zero if the bar breaks).
    #    Better net on 4 of 4 stretches, drawdown never worse on any of them.
    #    Deeper cuts score monotonically better (0.25x > 0.5x > 0.75x); 0.5x is the honest middle,
    #    not the optimum, because the standing rule is never to tune a size on the lockbox.
    #    NOT NOISE-only: the same bucket is negative on the ORB #314 breakout (EV R -0.257 vs +0.211)
    #    and the ENGU-Q #309 continuation (-0.499 vs +0.444), which is why the tilt is also exposed
    #    through compression_sizes(event=...) for the model-free legs.
    #    Recorded honestly: the PRE-REGISTERED story was the opposite (I expected the 14:00 statement
    #    to be the bad half; it is the better half), so the bucket split is post-hoc - which is what
    #    the permutation test and the three placebos are there to price. It also misses the lab's
    #    year-by-year t >= 2.5 bar (t 1.57 / 2.00), unavoidable for a tilt touching 2.3% of trades,
    #    but that bar exists to reject leverage and this one adds no drawdown anywhere.
    "v12": {"W": 600, "t_lo": 0.5, "t_hi": 1.0, "target": "log", "stack": "trust",
            "ledger": "dollar", "members": ("logit", "et"), "K": 1.5, "LO": 0.75, "HI": 2.0,
            "fast": {"W": 50, "lo": -0.5, "hi": 0.5},
            "shade": {"t": -0.5, "k": 1.0, "lo": 0.5, "hi": 1.5},
            "comp": {"feature": "sq60_on", "mult": 1.5, "cap": 3.0},
            "dow": {"4": 1.5, "cap": 3.0},
            "event": {"mult": 0.5, "cut_hour": 14}},
}
for _k in ("v1", "v2"):
    CFG[_k].setdefault("ledger", "rank"); CFG[_k].setdefault("members", ("logit", "et", "huber"))


# -- scheduled macro events ----------------------------------------------------
_FOMC = None


def fomc_decision_days(path=None):
    """The Fed's own scheduled FOMC decision (statement) days, as ET calendar dates.
    Source: tools/data/fomc_dates.txt, scraped from federalreserve.gov (2010 -> 2027).
    Published years in advance, so a tilt keyed on it is knowable at entry - no look-ahead.
    Returns an empty set if the file is missing, which makes any event tilt a silent no-op."""
    global _FOMC
    if _FOMC is None:
        p = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "tools", "data", "fomc_dates.txt")
        out = set()
        try:
            with open(p, "r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if ln and not ln.startswith("#"):
                        out.add(_dt.date.fromisoformat(ln))
        except Exception:
            pass
        _FOMC = out
    return _FOMC


def pre_statement_mask(arrays, E, cut_hour=14):
    """True where the entry bar sits on a scheduled FOMC decision day BEFORE the ET statement.
    Handles both the naive and the tz-aware index paths (ETH masters carry a tz)."""
    idx = pd.DatetimeIndex(arrays["index"])
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern")
    e = idx[np.clip(np.asarray(E, int), 0, len(idx) - 1)]
    days = fomc_decision_days()
    if not days:
        return np.zeros(len(e), bool)
    return np.array([(t.date() in days) and (t.hour < int(cut_hour)) for t in e], bool)


# -- extra causal features -----------------------------------------------------
def _squeeze60(arrays, length=20, bb_mult=2.0, kc_mult=1.5, tf_min=60):
    """60-minute Bollinger/Keltner compression ratio, as of the LAST COMPLETE 60m group
    before each bar (session-anchored groups, like tools/ttmsqz_round6_parts.hourly_compression).
    ratio<1 = compressed. NaN until warm."""
    idx = pd.DatetimeIndex(arrays["index"])
    H = np.asarray(arrays["high"], float); L = np.asarray(arrays["low"], float)
    C = np.asarray(arrays["close"], float)
    day = np.asarray(arrays["day_id"])
    df = pd.DataFrame({"d": day, "h": H, "l": L, "c": C})
    df["t"] = idx
    first = df.groupby("d")["t"].transform("first")
    off = ((df["t"] - first).dt.total_seconds() // 60).astype("int64")
    grp = df["d"].astype(np.int64) * 100 + (off // int(tf_min))   # session-anchored groups of tf_min minutes
    g = df.groupby(grp, sort=True)
    hh = g["h"].max(); ll = g["l"].min(); cc = g["c"].last()
    ma = cc.rolling(length).mean()  # noqa: F841
    sd = cc.rolling(length).std(ddof=0)
    tr = pd.concat([hh - ll, (hh - cc.shift(1)).abs(), (ll - cc.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(length).mean()
    ratio = ((bb_mult * sd) / (kc_mult * atr).replace(0.0, np.nan)).to_numpy()
    codes = pd.factorize(grp, sort=True)[0]
    prev = codes - 1
    out = np.full(len(df), np.nan)
    ok = prev >= 0
    out[ok] = ratio[prev[ok]]
    return out


def extra_features(arrays):
    """Extra columns. `lagged` are 'as of bar i close' (caller lags them one bar);
    `unlagged` are known at bar i's open already."""
    O = pd.Series(np.asarray(arrays["open"], float)); H = pd.Series(np.asarray(arrays["high"], float))
    L = pd.Series(np.asarray(arrays["low"], float)); C = pd.Series(np.asarray(arrays["close"], float))
    day = pd.Series(np.asarray(arrays["day_id"]))
    tr = pd.concat([H - L, (H - C.shift(1)).abs(), (L - C.shift(1)).abs()], axis=1).max(axis=1)
    atr14 = tr.ewm(alpha=1 / 14, adjust=False).mean().replace(0.0, np.nan)
    rng = (H - L).replace(0.0, np.nan)
    body = ((C - O).abs() / rng).rolling(5, min_periods=1).mean()
    sv = np.sign(C.diff()).fillna(0.0).to_numpy()
    run = np.zeros(len(C)); r = 0.0
    for i in range(len(sv)):
        if sv[i] == 0:
            r = 0.0
        elif i > 0 and sv[i] == sv[i - 1]:
            r += sv[i]
        else:
            r = sv[i]
        run[i] = r
    dh = H.groupby(day).cummax(); dl = L.groupby(day).cummin()
    day_pos = (C - dl) / (dh - dl).replace(0.0, np.nan)
    day_open = O.groupby(day).transform("first")
    prev_close = C.groupby(day).last().shift(1)
    pc_on_bars = prev_close.reindex(day.to_numpy()).to_numpy()
    gap = (day_open.to_numpy() - pc_on_bars) / atr14.to_numpy()
    rv20 = C.pct_change().rolling(20).std(); rv100 = C.pct_change().rolling(100).std()
    sq = _squeeze60(arrays)
    lagged = pd.DataFrame({"body5": body, "run_len": pd.Series(run), "day_pos": day_pos,
                           "rv_ratio": (rv20 / rv100.replace(0.0, np.nan))})
    unlagged = pd.DataFrame({"gap_atr": pd.Series(gap), "sq60_ratio": pd.Series(sq),
                             "sq60_on": pd.Series((sq < 1.0).astype(float))})
    return lagged, unlagged


def keel_features(arrays):
    F, names = entry_features(arrays)
    lag, unl = extra_features(arrays)
    X = pd.DataFrame(F, columns=names)
    for c in lag.columns:
        X[c] = lag[c].to_numpy()
    mkt = [c for c in X.columns if c not in _CLOCK_FEATS]
    Xc = X.copy()
    Xc.loc[1:, mkt] = X[mkt].to_numpy()[:-1]
    for c in unl.columns:
        Xc[c] = unl[c].to_numpy()
    Xc = Xc.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return Xc.to_numpy(float), list(Xc.columns)


# -- the ensemble --------------------------------------------------------------
def _fit_members(X, y_pnl, w, seed, target="log", use=("logit", "et", "huber")):
    from sklearn.linear_model import LogisticRegression, HuberRegressor
    from sklearn.ensemble import ExtraTreesRegressor
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(X)
    Xs = sc.transform(X)
    losses = y_pnl[y_pnl < 0]
    avg_loss = float(-losses.mean()) if len(losses) else float(np.abs(y_pnl).mean() or 1.0)
    R = y_pnl / max(avg_loss, 1e-9)
    R = np.clip(R, -5.0, 5.0) if target == "clip5" else np.sign(R) * np.log1p(np.abs(R))
    members = []
    yb = (y_pnl > 0).astype(int)
    if "logit" in use and np.unique(yb).size == 2:
        lr = LogisticRegression(max_iter=500, C=1.0, random_state=seed)
        lr.fit(Xs, yb, sample_weight=w * (np.abs(y_pnl) + 1e-9))
        d = lr.decision_function(Xs)
        members.append(("logit", lr, float(d.mean()), float(d.std() + 1e-9)))
    if "et" in use:
        # n_jobs=1 on purpose: this refits inside the same rolling walk as the gate, and a
        # process pool per fit cost more than the fit (see _GATE_N_JOBS in ml_gate.py).
        et = ExtraTreesRegressor(n_estimators=200, max_depth=5, min_samples_leaf=15,
                                 n_jobs=1, random_state=seed)
        et.fit(Xs, R, sample_weight=w)
        d = et.predict(Xs)
        members.append(("et", et, float(d.mean()), float(d.std() + 1e-9)))
    hb = HuberRegressor(alpha=1.0, max_iter=300)
    if "huber" not in use:
        return sc, members
    try:
        hb.fit(Xs, R, sample_weight=w)
        d = hb.predict(Xs)
        members.append(("huber", hb, float(d.mean()), float(d.std() + 1e-9)))
    except Exception:
        pass
    return sc, members


def _predict_z(sc, members, x):
    xs = sc.transform(x)
    zs = {}
    for nm, m, mu, sd in members:
        d = m.decision_function(xs) if nm == "logit" else m.predict(xs)
        zs[nm] = float((d[0] - mu) / sd)
    return zs


def _trust(zled, pled, W, t_lo, t_hi, ledger="rank"):
    n = len(zled)
    if n < MIN_SKILL_N:
        return 0.0, np.nan, 0.0
    ok = ~np.isnan(zled)
    zled, pled = zled[ok][-W:], pled[ok][-W:]
    m = len(zled)
    if m < MIN_SKILL_N:
        return 0.0, np.nan, 0.0
    if ledger == "dollar":
        g = pled * zled                     # marginal $ of a unit-slope tilt, per trade
        sd = g.std(ddof=1)
        if not np.isfinite(sd) or sd <= 0:
            return 0.0, np.nan, 0.0
        t = g.mean() / (sd / np.sqrt(m))
        rho = float(g.mean() / (np.abs(pled).mean() + 1e-9))
    else:
        from scipy.stats import spearmanr
        rho = spearmanr(zled, pled).correlation
        if not np.isfinite(rho):
            return 0.0, np.nan, 0.0
        t = rho * np.sqrt(max(m - 2, 1)) / np.sqrt(max(1 - rho * rho, 1e-9))
    return float(np.clip((t - t_lo) / (t_hi - t_lo), 0.0, 1.0)), float(rho), float(t)


DEFAULT_VERSION = "v4"


def keel_walk(arrays, trades, feats=None, seed=SEED, trust_mode="skill", version=DEFAULT_VERSION):
    """Chronological walk. Returns per-trade arrays in ENTRY order: size, z (ensemble),
    z_members, trust, rho, member trusts, plus the sorted 3-tuples."""
    cfg = CFG[version]
    W, t_lo, t_hi, ledger = cfg["W"], cfg["t_lo"], cfg["t_hi"], cfg["ledger"]
    K, lo, hi = cfg.get("K", K_MAX), cfg.get("LO", LO), cfg.get("HI", HI)
    fast = cfg.get("fast")
    shade = cfg.get("shade")
    comp = cfg.get("comp")
    T = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in trades], key=lambda t: t[0])
    E = np.array([t[0] for t in T]); Xi = np.array([t[1] for t in T]); P = np.array([t[2] for t in T])
    n = len(T)
    F, names = feats if feats is not None else keel_features(arrays)
    X = F[np.clip(E, 0, len(F) - 1)]
    z = np.full(n, np.nan); trust = np.zeros(n); rho = np.full(n, np.nan)
    zm = {k: np.full(n, np.nan) for k in ("logit", "et", "huber")}
    tm = {k: np.zeros(n) for k in ("logit", "et", "huber")}
    size = np.ones(n)
    sc = members = None; fitted_on = -1; n_fits = 0
    for k in range(n):
        done = Xi[:k] < E[k]
        nd = int(done.sum())
        if nd < MIN_HISTORY:
            continue
        if members is None or (nd - fitted_on) >= REFIT_EVERY:
            idx = np.where(done)[0]
            age = (nd - 1 - np.arange(nd)).astype(float)
            w = np.exp(-age / TAU)
            sc, members = _fit_members(X[idx], P[idx], w, seed, target=cfg["target"], use=cfg["members"])
            fitted_on = nd; n_fits += 1
        zs = _predict_z(sc, members, X[k:k + 1])
        for kk, v in zs.items():
            zm[kk][k] = v
        led = np.where(done)[0]
        if cfg["stack"] == "equal":
            z[k] = float(np.mean(list(zs.values())))
        else:
            num = 0.0; den = 0.0
            for kk, v in zs.items():
                t_m, _, _ = _trust(zm[kk][led], P[led], W, t_lo, t_hi, ledger) if len(led) else (0.0, np.nan, 0.0)
                tm[kk][k] = t_m
                num += t_m * v; den += t_m
            z[k] = float(num / den) if den > 0 else 0.0
        if trust_mode == "skill":
            tr, rh, _ = _trust(z[led], P[led], W, t_lo, t_hi, ledger) if len(led) else (0.0, np.nan, 0.0)
            if cfg["stack"] != "equal" and den <= 0:
                tr = 0.0
        else:
            tr, rh = 1.0, np.nan
        t_fast = None
        if fast and len(led) and (tr > 0 or shade):
            # fast-distrust: the same dollar ledger over the last fast["W"] resolved trades may only CUT
            _, _, t_fast = _trust(z[led], P[led], fast["W"], 0.0, 1.0, ledger)
            tr *= float(np.clip((t_fast - fast["lo"]) / (fast["hi"] - fast["lo"]), 0.0, 1.0))
        trust[k] = tr; rho[k] = rh
        if shade and t_fast is not None and t_fast < shade["t"] and z[k] != 0:
            # shade when wrong: lean a little against a score the recent record says is inverted
            size[k] = float(np.clip(1.0 - shade["k"] * z[k], shade["lo"], shade["hi"]))
        else:
            size[k] = float(np.clip(1.0 + K * tr * z[k], lo, hi))
    dow = cfg.get("dow")
    if dow:
        # a-priori day-of-week multiplier on the entry bar's weekday (0=Mon .. 4=Fri)
        _idx = pd.DatetimeIndex(arrays["index"]); _wd = _idx[np.clip(E, 0, len(_idx) - 1)].dayofweek
        _m = np.array([float(dow.get(str(int(w)), 1.0)) for w in _wd])
        size = np.minimum(size * _m, float(dow.get("cap", 3.0)))
    if comp and comp["feature"] in names:
        # a-priori compression multiplier on top of the learned size (TTM round 6), capped
        on = X[:, names.index(comp["feature"])] > 0
        size = np.minimum(np.where(on, size * float(comp["mult"]), size), float(comp.get("cap", 3.0)))
    ev = cfg.get("event")
    if ev:
        # a-priori EVENT tilt, applied LAST so no cap can undo a cut: half size before the statement
        _pre = pre_statement_mask(arrays, E, ev.get("cut_hour", 14))
        size = np.where(_pre, size * float(ev.get("mult", 0.5)), size)
    return {"trades": T, "E": E, "X": Xi, "P": P, "size": size, "z": z, "z_members": zm,
            "trust": trust, "rho": rho, "trust_members": tm, "n_fits": n_fits,
            "feature_names": names, "version": version}


def compression_sizes(arrays, trades, mult=1.5, feature="sq60_on", deep=None, thr=0.85, dow=None, cap=3.0,
                      gate_tf_min=60, gate_len=20, gate_ratio=1.0, event=None):
    """RAW x compression, no model: the attribution control for v9. Size `mult` on trades entered
    while the 60m state is compressed, 1.0 otherwise. Trades sorted by entry bar.
    2026-09-08 options: `deep` = multiplier when sq60_ratio < `thr` (depth-graded: 2x deep / 1.5x on /
    1x off beat the flat 1.5x on the ORB and ENGU-Q crowns); `dow` = {"4": 1.5} weekday multiplier
    on the entry bar (comp x Friday passed on the ORB crown). Product capped at `cap`."""
    T = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in trades], key=lambda t: t[0])
    F, names = keel_features(arrays)
    E = np.clip(np.array([t[0] for t in T]), 0, len(F) - 1)
    if (int(gate_tf_min), int(gate_len), float(gate_ratio)) != (60, 20, 1.0):
        # 2026-09-08: the gate the fenced validates crowned twice (run 321 as a filter, run 333 as
        #   the 1.5x tilt: 30-minute check, length 16, ratio <= 1.15). Same last-complete-group
        #   construction as the default path, read at the entry bar; ratio <= gate_ratio, exactly as
        #   the validated NOISE_1_1_SBS_V90_CT15.py reads it (walked equal at group boundaries).
        r = _squeeze60(arrays, length=int(gate_len), tf_min=int(gate_tf_min))[E]
        on = np.isfinite(r) & (r <= float(gate_ratio))
    else:
        on = F[E, names.index(feature)] > 0
    m = np.where(on, float(mult), 1.0)
    if deep is not None and "sq60_ratio" in names:
        m = np.where(F[E, names.index("sq60_ratio")] < float(thr), float(deep), m)
    if dow:
        wd = pd.DatetimeIndex(arrays["index"])[E].dayofweek
        m = m * np.array([float(dow.get(str(int(w)), 1.0)) for w in wd])
    m = np.minimum(m, float(cap))
    if event:
        # v12's FOMC pre-statement half-size, model-free (that bucket is negative on ORB and ENGU-Q too)
        m = np.where(pre_statement_mask(arrays, E, event.get("cut_hour", 14)), m * float(event.get("mult", 0.5)), m)
    return m


def sizes_from_z(z, trust, k=K_MAX, lo=LO, hi=HI):
    zz = np.where(np.isnan(z), 0.0, z)
    return np.clip(1.0 + k * trust * zz, lo, hi)


# -- gate_validate row --------------------------------------------------------
def keel_block(arrays, trades, slicer, lb_start, wf0=None, wf1=None, version=DEFAULT_VERSION):
    """One comparison-only row for gate_validate's output (same stat-block shape as the
    TILT rows; never crownable). `slicer(ts, pnls, t0, t1)` is gate_validate's _sl."""
    kw = keel_walk(arrays, trades, version=version)
    idx = arrays["index"]; nb = len(idx)
    ts = np.array([idx[min(int(e), nb - 1)] for e in kw["E"]])
    pnl = kw["P"]; w = kw["size"]
    tp = pnl * w
    pre_m = ts < lb_start
    _rng = wf0 is not None and wf1 is not None
    row = {"model": "keel", "version": version, "scheme": "skill-gated expectancy tilt",
           "crownable": False, "n_trades": int(len(tp)), "kept_pre": int(pre_m.sum()),
           "avg_size": round(float(w[pre_m].mean()) if pre_m.any() else 1.0, 3),
           "max_size": round(float(w.max()), 2),
           "sizes": {"small": int((w < 0.75).sum()),
                     "normal": int(((w >= 0.75) & (w <= 1.5)).sum()),
                     "big": int((w > 1.5).sum()), "dropped": 0},
           "trust_mean": round(float(kw["trust"].mean()), 3),
           "trust_on": round(float((kw["trust"] > 0).mean()), 3),
           "member_trust": {k: round(float(v.mean()), 3) for k, v in kw["trust_members"].items()},
           "rule": "size = clip(1 + 0.5 * trust * z, 0.5, 2.0); trust = clip(t_dollar / 2, 0, 1)",
           "cutoff": None,
           "pre": slicer(ts, tp, None, lb_start),
           "lockbox": slicer(ts, tp, lb_start, None),
           "full": slicer(ts, tp, None, None),
           "is_rng": (slicer(ts, tp, None, wf0) if _rng else None),
           "wf_rng": (slicer(ts, tp, wf0, wf1) if _rng else None),
           "wf_lb": (slicer(ts, tp, wf0, None) if _rng else None)}
    try:
        from .analytics import downsample_curve
        row["equity"] = {"cum": downsample_curve(np.cumsum(tp), cap=300, ndp=None), "n": int(len(tp))}
    except Exception:
        pass
    return row
