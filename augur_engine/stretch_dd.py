"""STRETCH DD - DD% from peak and the worst $ drawdown of every stretch, on a VALUED daily series.

Owner item 51 (MANAGER #130). Design: C:/EdgeLog/_research_cache/item51/ENGINE_DESIGN.md, whose Critic
section (C1-C7) overrides its body, and DECISIONS_1020.md.

WHAT. Each stretch a validate reports - IS, the walk-forward chain, the lockbox, WF+LB, the whole run, and
every per-stretch block of the top-level gate_validate - gets two numbers more: `dd_pct_peak`, the worst
fall from an equity high in % of a $100,000 one-contract account, and `dd_usd`, the deepest $ drawdown
(peak from a flat account). Both are read off the stretch's DAILY curve valued at each session close:
closed P&L plus the mark-to-market of whatever is still open. A trade held over a losing night now shows
that night; the closed-trade curve never could (one long held three days: closed DD $0, valued DD $600).

GLUE ONLY. Valuation = book._mtm_increments, called one trade at a time on the bars it was open; the
numbers = drawdowns.four_numbers. Nothing here runs a backtest or changes a value that already exists:
every caller hands over trades it already had, and every failure becomes a written reason, never an
exception out of a validate.

THE RULES (tests/test_stretch_dd.py pins each one):
  * MEMBERSHIP BY ENTRY, the block's own rule. A trade that enters in IS and exits in WF is IS's, and the
    IS series runs on to its exit day.
  * THE CENT CHECK. A stretch's valued daily series must sum to its stored net x money to the cent, and
    its member count must equal the block's own trade count. Otherwise nothing is stored for it.
  * THE DAY (critic C1). On a CME ETH master a bar belongs to the CME trading day with the 18:00 ET roll
    (session_calendar._trading_ymd): a bar at or after 18:00 is the next date's, Sunday evening trades
    Monday, so each day's last bar is the session close and a weekend is no row. Every other master uses
    the US/Eastern calendar date; RTH reads the same under every rule. dd_pct_src.day_rule says which.
  * ROLL SEAMS (critic C2). On an unadjusted NQ / ES master the roll plan re-prices fills to raw contract
    prices with the roll step out. After a switch the raw close is the NEW contract, so a mark taken from
    it carries the step while the cent check still passes. A trade held across a switch is therefore
    marked on the difference-adjusted series (close + shift, entry + shift at its fill bar) - the series
    its P&L was computed on. Ratio plans: refused (RATIO_ROLL) until that maths is designed; any other
    plan holding across a switch: refused (SWITCH_HELD). Never a mark with the step in it.
  * MONEY (critic C3). ONE money_ctx(job_mult, instrument, strategy): a futures root -> the job's
    multiplier when given, else the house table (book._MULT); QQQ, stocks, yahoo_adj, alpaca and a
    PNL_UNITS = "usd" file -> UNSIZED. Never a default 20.
  * A multi-day trade that cannot be valued (no side or entry price, a non-finite close, a size it
    folded in that we do not know - and the WF chain never knows a sizing file's sizes) makes its
    stretch null with the count recorded - never 0. A non-finite valued amount is NON_FINITE, never
    "within a cent".
  * FRAME BOUNDS (critic C7). Every member satisfies 0 <= entry <= exit < bars, else OUT_OF_FRAME.
  * SAME TAPE. Fold stamps + closes (FOLD_TS / TAPE_MOVED), the lockbox's recorded tape, the whole
    run's bar count: a master rewritten mid-validate never yields a figure off moved bars.
  * A stretch with no trade (a lockbox that took none) is a flat series: DD 0, marked 0.
  * ISOLATION. An error in one stretch / gate block nulls that one, with its reason; the rest are written.

Kill switch: AUGUR_STRETCH_DD=0 turns the whole thing off (no new key anywhere).
"""
from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd

DD_KEYS = ("dd_pct_peak", "dd_usd", "dd_marked")
STRETCHES = ("is", "wf", "lb", "wf_lb", "full")
VERSION = 1
CENT = 0.005                     # the to-the-cent tolerance of the net check, in dollars

# Per-trade status, worst first. A stretch with any member not OK reports the lowest code present.
OK, BAD_TRADE, OUT_OF_FRAME, UNMARKED, SIZE_UNKNOWN, RATIO_ROLL, SWITCH_HELD, MARK_ERROR = range(8)
CODES = {BAD_TRADE: "BAD_TRADE", OUT_OF_FRAME: "OUT_OF_FRAME", UNMARKED: "UNMARKED",
         SIZE_UNKNOWN: "SIZE_UNKNOWN", RATIO_ROLL: "RATIO_ROLL", SWITCH_HELD: "SWITCH_HELD",
         MARK_ERROR: "MARK_ERROR"}
_WHY = {BAD_TRADE: "could not be read (entry / exit / P&L)",
        OUT_OF_FRAME: "have bar indices outside the stretch's price arrays",
        UNMARKED: "were open overnight with no side, entry price or finite close to value them by",
        SIZE_UNKNOWN: "were open overnight at a size the strategy folded into its P&L and this stretch "
                      "does not carry",
        RATIO_ROLL: "were held across a contract switch on a ratio-adjusted plan (not designed yet)",
        SWITCH_HELD: "were held across a contract switch on a plan whose marks cannot be cleared of the "
                   "roll step",
        MARK_ERROR: "raised an error while being marked (roll table / price arrays)"}
DIFF_KIND = "difference-adjusted signals"
RATIO_KIND = "ratio-adjusted signals"


class Refused(Exception):
    """A whole stretch (or the whole pass) cannot be valued; `code` is the reason class."""

    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__("%s: %s" % (code, detail) if detail else code)


def enabled():
    """AUGUR_STRETCH_DD=0 (or off / false / no) turns item 51 off everywhere."""
    return str(os.environ.get("AUGUR_STRETCH_DD", "1")).strip().lower() not in ("0", "off", "false", "no")


def start_usd():
    from .drawdowns import DEFAULT_START_USD
    return float(DEFAULT_START_USD)


# ── MONEY (critic C3 / decision 5) ──────────────────────────────────────────────────────────────────
def money_ctx(job_mult, instrument, strategy=None, source=None):
    """THE money rule, shared by the engine and the backfill: (ctx, None) or (None, "UNSIZED: why").

    ctx = {"mult": $ per point for one contract, "mult_src": "job" | "table", "instrument": root}.
    A futures root the house table knows (book._MULT) takes the job's multiplier when one is given and
    positive, else the table's. Anything else - QQQ, ETFs, stocks, yahoo_adj daily, alpaca data, or a
    strategy whose P&L is already dollars (PNL_UNITS = "usd") - is UNSIZED: one share on $100k makes a
    DD% meaningless, and the runner's own default of 20 is no evidence of a point value."""
    src = str(source or "").strip().lower()
    if src.startswith(("yahoo_adj", "alpaca")):
        return None, "UNSIZED: %s prices are not futures points" % source
    if strategy is not None:
        try:
            from .strategies import load_strategy
            mod = strategy if hasattr(strategy, "run_backtest") else load_strategy(strategy)
            if str(getattr(mod, "PNL_UNITS", "points") or "points").strip().lower() == "usd":
                return None, "UNSIZED: the strategy reports P&L in dollars (PNL_UNITS = 'usd')"
        except Exception as e:
            return None, "UNSIZED: could not read the strategy's P&L units (%s)" % type(e).__name__
    from .book import _MULT
    from .rolls import normalize_instrument
    inst = normalize_instrument(instrument)
    tab = _MULT.get(inst)
    if not tab:
        return None, "UNSIZED: %r is not a futures root with a known point value" % (instrument,)
    try:
        jm = float(job_mult) if job_mult is not None else None
    except (TypeError, ValueError):
        jm = None
    if jm is not None and math.isfinite(jm) and jm > 0:
        return {"mult": jm, "mult_src": "job", "instrument": inst}, None
    return {"mult": float(tab), "mult_src": "table", "instrument": inst}, None


# ── THE DAY (critic C1 / decision 3) ────────────────────────────────────────────────────────────────
def day_rule(meta):
    """'cme_1800_roll' on a CME ETH master (data._is_eth), else 'et_date'."""
    try:
        from .data import _is_eth
        return "cme_1800_roll" if _is_eth(meta or {}) else "et_date"
    except Exception:
        return "et_date"


def _et_ymd(index):
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    return (np.asarray(idx.year, dtype=np.int64) * 10000 + np.asarray(idx.month, dtype=np.int64) * 100
            + np.asarray(idx.day, dtype=np.int64))


def trading_ymd(index, meta):
    """(rule, int64 YYYYMMDD of every bar's day under that rule)."""
    rule = day_rule(meta)
    if rule == "cme_1800_roll":
        from .session_calendar import _trading_ymd
        return rule, np.asarray(_trading_ymd(index), dtype=np.int64)
    return rule, _et_ymd(index)


def _ymd_days(ymd_unique):
    if not len(ymd_unique):
        return np.zeros(0, dtype="datetime64[D]")
    return pd.to_datetime(np.asarray(ymd_unique).astype(str), format="%Y%m%d").values.astype("datetime64[D]")


def day_stamps(index, meta=None):
    """datetime64[D] day of every bar under the item-51 day rule."""
    _r, ymd = trading_ymd(index, meta)
    u, inv = np.unique(ymd, return_inverse=True)
    return _ymd_days(u)[np.asarray(inv).ravel()]


class Frame:
    """ONE price-arrays dict, day-stamped once. Every stretch's trades live on it by bar index (the
    whole-window arrays of a validate hold the WF chain and the warm lockbox too, at an offset)."""

    def __init__(self, arrays):
        idx = (arrays or {}).get("index")
        close = (arrays or {}).get("close")
        if idx is None or close is None:
            raise Refused("NO_ARRAYS", "the price arrays carry no index or close")
        self.index = pd.DatetimeIndex(idx)
        self.close = np.asarray(close, dtype=float)
        self.n = len(self.close)
        if len(self.index) != self.n:
            raise Refused("FRAME", "index has %d bars, close %d" % (len(self.index), self.n))
        self.meta = (arrays or {}).get("meta") or {}
        self.rule, ymd = trading_ymd(self.index, self.meta)
        if self.n > 1 and bool(np.any(np.diff(ymd) < 0)):
            raise Refused("FRAME", "the bars are not in time order")
        u, inv = np.unique(ymd, return_inverse=True)
        self.days = _ymd_days(u)                        # the distinct days, ascending
        self.pos = np.asarray(inv).ravel().astype(np.int64)   # each bar's position in self.days
        self.ns = np.asarray(self.index.asi8, dtype=np.int64)  # what Timestamp comparisons compare

    def bar_at(self, ts):
        """First bar at or after `ts` (n when none): the bar a [ts, ...) stretch opens on."""
        return int(np.searchsorted(self.ns, _ts_ns(ts, self.index), side="left"))


def _ts_ns(ts, index=None):
    t = pd.Timestamp(ts)
    if t.tzinfo is None and index is not None and getattr(index, "tz", None) is not None:
        t = t.tz_localize(index.tz)
    return int(t.value)


def frame_for(cache, arrays):
    """The Frame of `arrays`, built once per arrays dict and kept in `cache` (a dict)."""
    frames = cache.setdefault("_frames", {}) if isinstance(cache, dict) else {}
    key = (id(arrays.get("index")), id(arrays.get("close")), len(arrays.get("close")))
    fr = frames.get(key)
    if fr is None:
        fr = Frame(arrays)
        frames[key] = fr
    return fr


# ── ROLL SEAMS (critic C2 / decision 4) ─────────────────────────────────────────────────────────────
def roll_info(meta, result=None, table_dir=None):
    """What the run's roll plan did to its fills, or None when marks need no correction (an adjusted
    master, a stock, a root with no contract rolls). `result` is a run_backtest result of this run:
    its _meta.roll_stamp names the plan kind (`calendar`) and signal method."""
    from . import rolls as R
    root = R.unadjusted_futures_root(meta or {})
    if root is None:
        return None
    st = ((result or {}).get("_meta") or {}).get("roll_stamp") if isinstance(result, dict) else None
    st = st if isinstance(st, dict) else {}
    return {"root": root, "kind": st.get("calendar"), "method": st.get("signal_method"),
            "table_dir": table_dir}


class _RollMarks:
    """Clears the roll step out of the marks of a trade held across a contract switch."""

    def __init__(self, frame, roll):
        from . import rolls as R
        self.R = R
        self.frame = frame
        self.root = roll.get("root")
        self.kind = str(roll.get("kind") or "")
        self.table_dir = roll.get("table_dir")
        self.inst, _off, _ib = R._switch_arrays(self.root, self.table_dir)
        sample = R.epoch_seconds(frame.index[:min(frame.n, 2000)])
        self.tf = int(R.tf_seconds_of(frame.meta, sample))
        self.corrected = 0

    def adjust(self, e, x, seg_close, px):
        """(status, close slice, entry price) to mark a multi-day trade [e, x] with."""
        if not len(self.inst):
            return OK, seg_close, px
        tex = self.R.epoch_seconds(self.frame.index[[e, x]])
        seg = np.searchsorted(self.inst, tex + self.tf, side="left")   # switches before each bar's close
        if int(seg[0]) == int(seg[1]):
            return OK, seg_close, px                                    # one contract the whole hold
        if self.kind == DIFF_KIND:
            t = self.R.epoch_seconds(self.frame.index[e:x + 1])
            sc = np.asarray(self.R.roll_map(t, self.root, self.tf, self.table_dir)["shift_close"], dtype=float)
            self.corrected += 1
            # the plan re-priced the entry to raw with sc[e]; marking on close + sc puts every mark on the
            # adjusted series the P&L was computed on, so no mark carries the step
            return OK, seg_close + sc, float(px) + float(sc[0])
        if self.kind == RATIO_KIND:
            return RATIO_ROLL, seg_close, px
        return SWITCH_HELD, seg_close, px


# ── VALUATION: book._mtm_increments, one trade at a time ────────────────────────────────────────────
def aligned_sizes(res, trades):
    """A result's own per-trade sizes (`trade_sizes`, NOISE's tilt) when aligned to `trades`, else None."""
    sz = (res or {}).get("trade_sizes") if isinstance(res, dict) else None
    if isinstance(sz, (list, tuple, np.ndarray)) and len(sz) == len(trades or []):
        return list(sz)
    return None


def folds_size(sizes):
    """True when some size differs from 1: the file folds a size into t[2], so a multi-day trade whose
    size this stretch does not carry cannot be marked (critic C3)."""
    try:
        return sizes is not None and any(abs(float(s) - 1.0) > 1e-12 for s in sizes)
    except Exception:
        return True


def emits_sizes(*results):
    """True when any of these run_backtest results carries `trade_sizes` (NOISE's tilt): the FILE folds a
    per-trade size into t[2], whatever one champion's sizes happen to be. A stretch that does not carry
    those sizes - the WF chain, whose folds each crowned their own params - cannot mark a multi-day trade
    (critic C3): a whole-run champion at size 1 says nothing about fold 3's champion at size 2."""
    return any(isinstance(r, dict) and r.get("trade_sizes") is not None for r in results)


# ── SAME TAPE (the bars a stretch's trades were made on = the bars it is valued on) ─────────────────
def close_fp(close):
    """A short sha1 of a close array's float64 bytes: two loads of the same bars give the same value."""
    import hashlib
    a = np.ascontiguousarray(np.asarray(close, dtype=np.float64))
    return hashlib.sha1(a.tobytes()).hexdigest()[:20]


def tape_of(arrays, i0=0):
    """What a stretch ran on, from bar `i0` to the end of `arrays`: bar count, first / last stamp and
    the closes' fingerprint. validate's lockbox runner records it so the gate-stage load can be proved
    to be the same tape (a master rewritten mid-validate moves bars under the trades' indices)."""
    idx, c = arrays.get("index"), arrays.get("close")
    n = len(c)
    return {"bars": int(n - i0), "first": str(idx[i0]), "last": str(idx[n - 1]),
            "cfp": close_fp(c[i0:])}


def _tape_moved(fr, i0, tape, res=None):
    """None when the frame's bars from `i0` on match what the stretch recorded running on, else why.
    With no recorded tape only a run_backtest result's own _meta.bars count can be checked."""
    if isinstance(tape, dict) and tape:
        got = {"bars": fr.n - i0, "first": str(fr.index[i0]), "last": str(fr.index[fr.n - 1])}
        for k, v in got.items():
            if tape.get(k) is not None and str(tape[k]) != str(v):
                return "it ran on %s %s, the gate-stage arrays hold %s" % (k, tape[k], v)
        if tape.get("cfp") and tape["cfp"] != close_fp(fr.close[i0:]):
            return "its closes changed between its run and the gate-stage load (same stamps, new prices)"
        return None
    bars = ((res or {}).get("_meta") or {}).get("bars") if isinstance(res, dict) else None
    if bars is not None and int(bars) != fr.n - i0:
        return "it ran on %d bars, the gate-stage arrays hold %d from its start" % (int(bars), fr.n - i0)
    return None


class Valuation:
    """Every trade's valued daily increments on one Frame, at size 1 (or the trade's own folded size).

    Rows (row_trade, row_pos, row_usd) are the trade's [(day, $)] from book._mtm_increments, called on
    the bars [entry, exit] the trade was open (exactly what the whole-array call computes for it: its
    marks only read day ends inside [entry, exit)). A same-day trade is one row on its exit day. A block
    is then any mask of member trades times any per-trade weight - linear, because _mtm_increments'
    scale multiplies the marks and the remainder alike (test_vectorized_equals_direct)."""

    def __init__(self, frame, trades, mult, offsets=0, sizes=None, sized_file=False, roll=None):
        from .book import _mtm_increments
        trades = list(trades or [])
        nt = len(trades)
        self.frame = frame
        self.mult = float(mult)
        self.status = np.zeros(nt, dtype=np.int8)
        self.marked = np.zeros(nt, dtype=bool)
        self.entry = np.full(nt, -1, dtype=np.int64)
        self.exit = np.full(nt, -1, dtype=np.int64)
        self.pnl = np.zeros(nt, dtype=float)
        if np.ndim(offsets) == 0:
            offs = np.full(nt, int(offsets), dtype=np.int64)
        else:
            offs = np.asarray(offsets, dtype=np.int64)
            if len(offs) != nt:
                raise Refused("FRAME", "%d offsets for %d trades" % (len(offs), nt))
        if sizes is not None and len(sizes) != nt:
            raise Refused("FRAME", "%d sizes for %d trades" % (len(sizes), nt))
        rm = _RollMarks(frame, roll) if roll else None
        n, pos, close, days = frame.n, frame.pos, frame.close, frame.days
        rt, rp, ru = [], [], []
        for i, t in enumerate(trades):
            try:
                e = int(t[0]) + int(offs[i])
                x = int(t[1]) + int(offs[i])
                p = float(t[2])
                if not math.isfinite(p):
                    raise ValueError("pnl")
            except Exception:
                self.status[i] = BAD_TRADE
                continue
            self.entry[i], self.exit[i], self.pnl[i] = e, x, p
            if not (0 <= e <= x < n):                     # critic C7: never let an index clamp
                self.status[i] = OUT_OF_FRAME
                continue
            if pos[e] == pos[x]:                          # same day: booked whole on its exit day
                rt.append(i)
                rp.append(int(pos[x]))
                ru.append(p * self.mult)
                continue
            s = None if sizes is None else sizes[i]
            if s is None:
                if sized_file:
                    self.status[i] = SIZE_UNKNOWN
                    continue
                s = 1.0
            try:
                s = float(s)
                if not (math.isfinite(s) and s > 0):
                    raise ValueError("size")
            except Exception:
                self.status[i] = SIZE_UNKNOWN
                continue
            try:
                side, px = float(t[3]), float(t[4])
            except Exception:
                self.status[i] = UNMARKED
                continue
            seg_close = close[e:x + 1]
            # one trade's marking can never take the others down: an error here is this trade's status
            try:
                if rm is not None:
                    st, seg_close, px = rm.adjust(e, x, seg_close, px)
                    if st != OK:
                        self.status[i] = st
                        continue
                # size s folded into t[2] (critic C3): value (t[2]/s) at size s, so the marks scale with s
                # and the increments still sum to t[2] x mult
                inc, mk, um = _mtm_increments(days[pos[e:x + 1]], seg_close,
                                              [((0, x - e, p / s, side, px), s)], self.mult, 1.0)
            except Exception:
                self.status[i] = MARK_ERROR
                continue
            # a NaN / inf close at a day-end bar (or a NaN roll shift) makes every mark after it NaN, and
            # a NaN sum slips past any "differs by a cent" test: such a position is not valued (decision 8)
            if um or mk != 1 or not inc or not all(math.isfinite(float(q[1])) for q in inc):
                self.status[i] = UNMARKED
                continue
            dd = np.asarray([q[0] for q in inc], dtype="datetime64[D]")
            rt.extend([i] * len(inc))
            rp.extend(np.searchsorted(days, dd).tolist())
            ru.extend(float(q[1]) for q in inc)
            self.marked[i] = True
        self.row_trade = np.asarray(rt, dtype=np.int64)
        self.row_pos = np.asarray(rp, dtype=np.int64)
        self.row_usd = np.asarray(ru, dtype=float)
        self.roll_corrected = rm.corrected if rm is not None else 0

    def __len__(self):
        return len(self.status)


def reading(val, members, lo_bar, hi_bar, expect_usd, weights=None, expect_n=None):
    """One stretch: ({"dd_pct_peak", "dd_usd", "marked"}, None) or (None, (code, count, text)).

    `members` masks the valuation's trades (entry membership, decided by the caller); `weights` sizes
    each trade (a tilt / hybrid row); the day grid runs from the stretch's first bar `lo_bar` to
    max(`hi_bar`, the last member exit), every distinct day present, zero days included. A stretch with
    no member trade (a lockbox that took none) is a FLAT series over its own days: DD 0, marked 0, still
    cent-checked against its stored net (which must then be 0)."""
    fr = val.frame
    m = np.asarray(members, dtype=bool)
    if len(m) != len(val):
        return None, ("FRAME", 0, "the member mask has %d rows for %d trades" % (len(m), len(val)))
    idx = np.flatnonzero(m)
    if expect_n is not None and len(idx) != int(expect_n):
        return None, ("MEMBERSHIP", len(idx), "%d member trades where the block counts %d"
                      % (len(idx), int(expect_n)))
    st = val.status[idx]
    if st.any():
        code = int(st[st > 0].min())
        k = int((st == code).sum())
        return None, (CODES[code], k, "%d trade(s) %s" % (k, _WHY[code]))
    if len(idx):
        lo = max(0, int(min(int(lo_bar), int(val.entry[idx].min()))))
        hi = min(fr.n - 1, int(max(int(hi_bar), int(val.exit[idx].max()))))
    else:
        lo, hi = max(0, int(lo_bar)), min(fr.n - 1, int(hi_bar))
    if hi < lo:
        return None, ("FEW_DAYS", 0, "the stretch has no bars")
    sel = m[val.row_trade] if len(val.row_trade) else np.zeros(0, dtype=bool)
    usd = val.row_usd[sel]
    if weights is not None:
        w = np.asarray(weights, dtype=float)
        if len(w) != len(val):
            return None, ("FRAME", 0, "%d weights for %d trades" % (len(w), len(val)))
        usd = usd * w[val.row_trade[sel]]
    bad = ~np.isfinite(usd)
    if bad.any():                    # a NaN never compares >= a cent: refuse it before any check reads it
        k = int(len(np.unique(val.row_trade[sel][bad])))
        return None, ("NON_FINITE", k, "%d trade(s) valued to a non-finite amount (a NaN close, size or "
                                       "weight)" % k)
    whole = np.bincount(val.row_pos[sel], weights=usd, minlength=len(fr.days)) if len(usd) \
        else np.zeros(len(fr.days))
    d0, d1 = int(fr.pos[lo]), int(fr.pos[hi])
    ser = whole[d0:d1 + 1]
    if not (abs(math.fsum(whole) - math.fsum(ser)) <= 1e-6):  # an increment outside the grid = a frame bug
        return None, ("FRAME", 0, "valued increments fall outside the stretch's days")
    if len(ser) < 2:
        return None, ("FEW_DAYS", len(ser), "the stretch spans fewer than 2 days")
    tot = math.fsum(ser)
    try:
        exp = float(expect_usd)
    except (TypeError, ValueError):
        exp = float("nan")
    if not math.isfinite(exp):
        return None, ("NO_NET", 0, "no stored net to check the valued series against")
    if not (math.isfinite(tot) and abs(tot - exp) < CENT):    # NaN-safe: only a provable match passes
        return None, ("NET_MISMATCH", 0, "valued net %.2f != block net %.2f" % (tot, exp))
    from .drawdowns import four_numbers
    f = four_numbers([float(v) for v in ser], dates=[str(d) for d in fr.days[d0:d1 + 1]],
                     start=start_usd())
    return {"dd_pct_peak": f["dd_pct_peak"], "dd_usd": f["max_dd"],
            "marked": int(val.marked[idx].sum())}, None


def _why_of(e):
    """An exception -> a stretch's (code, count, text): a Refused keeps its code, anything else is ERROR."""
    if isinstance(e, Refused):
        return (e.code, 0, e.detail)
    return ("ERROR", 0, "%s: %s" % (type(e).__name__, str(e)[:160]))


def safe_reading(*args, **kw):
    """reading() that never raises: an exception becomes that stretch's own reason, so one bad stretch
    is null and every other stretch is still written (decision 7)."""
    try:
        return reading(*args, **kw)
    except Exception as e:
        return None, _why_of(e)


def as_block_keys(r):
    """Run-level reading -> the per-block key names."""
    return {"dd_pct_peak": r["dd_pct_peak"], "dd_usd": r["dd_usd"], "dd_marked": r["marked"]}


def attach(block, r):
    """Add the three keys to a block - never overwriting one already there. True when attached."""
    if not isinstance(block, dict) or set(DD_KEYS) & set(block):
        return False
    block.update(as_block_keys(r))
    return True


def strip_keys(obj):
    """A copy of `obj` with the three per-block keys removed from every dict in it (lists and dicts are
    rebuilt, leaves shared). For the validate.gate_bakeoff mirror: the keys ride on the top-level
    gate_validate copy only (decision 2 - doc size)."""
    if isinstance(obj, dict):
        return {k: strip_keys(v) for k, v in obj.items() if k not in DD_KEYS}
    if isinstance(obj, list):
        return [strip_keys(v) for v in obj]
    return obj


def _count(rep, code):
    rep[code] = rep.get(code, 0) + 1


# ── GATE BLOCKS (ml_gate.gate_validate, `mtm=`) ─────────────────────────────────────────────────────
def gate_ctx(money, roll=None, sizes=None, sized_file=None):
    """The `mtm=` dict validate hands gate_validate. gate_pass fills "report" and caches the Frame.
    `sized_file`: does the strategy file fold a size into t[2] (emits_sizes of its result)? None = judge
    by `sizes` alone (some size != 1)."""
    return {"money": money, "roll": roll, "sizes": sizes,
            "sized_file": folds_size(sizes) if sized_file is None else bool(sized_file),
            "report": None}


def gate_pass(mtm, arrays, trades, n_T, regs):
    """Value every registered gate block. `regs` = [(block, mask over T | None, weights over T | None,
    t0, t1)] in gate_validate's own trade order T (entry-sorted, stable). Writes the three keys into
    each block that passes its checks and leaves a report {"blocks", "refused": {code: n}, "day_rule"}
    in mtm. A block that raises is counted under ERROR (first messages in "errors"); the pass goes on."""
    rep = {"blocks": 0, "refused": {}}
    mtm["report"] = rep
    if not regs:
        return rep
    mult = float(mtm["money"]["mult"])
    fr = frame_for(mtm, arrays)
    rep["day_rule"] = fr.rule
    sizes = mtm.get("sizes")
    if sizes is not None and len(sizes) != len(trades):
        sizes = None
    pairs = [(t, (sizes[i] if sizes is not None else None)) for i, t in enumerate(trades) if len(t) >= 3]
    pairs.sort(key=lambda p: int(p[0][0]))              # gate_validate's T: same filter, same stable sort
    if len(pairs) != int(n_T):
        raise Refused("FRAME", "%d trades where the gate holds %d" % (len(pairs), int(n_T)))
    t5 = [p[0] for p in pairs]
    sz = [p[1] for p in pairs] if sizes is not None else None
    val = Valuation(fr, t5, mult, sizes=sz, sized_file=bool(mtm.get("sized_file")), roll=mtm.get("roll"))
    eb = np.minimum(np.asarray([int(t[0]) for t in t5], dtype=np.int64), fr.n - 1)
    ens = fr.ns[eb]                                     # entry_ts, as the gate stamps it
    seen = set()
    for block, mask, weights, t0, t1 in regs:
        if not isinstance(block, dict) or id(block) in seen:
            continue
        seen.add(id(block))
        try:
            m = np.ones(len(t5), dtype=bool) if mask is None else np.asarray(mask, dtype=bool).copy()
            if len(m) != len(t5):
                _count(rep["refused"], "FRAME")
                continue
            lo, hi = 0, fr.n - 1
            if t0 is not None:
                m &= ens >= _ts_ns(t0, fr.index)
                lo = fr.bar_at(t0)
            if t1 is not None:
                m &= ens < _ts_ns(t1, fr.index)
                hi = fr.bar_at(t1) - 1
            try:
                exp = float(block.get("total_pnl")) * mult
            except (TypeError, ValueError):
                exp = None
            r, why = reading(val, m, lo, hi, exp, weights=weights, expect_n=block.get("num_trades"))
        except Exception as e:                          # one block never costs the others their keys
            _count(rep["refused"], "ERROR")
            errs = rep.setdefault("errors", [])
            if len(errs) < 3:
                errs.append("%s: %s" % (type(e).__name__, str(e)[:160]))
            continue
        if r is None:
            _count(rep["refused"], why[0])
            continue
        if attach(block, r):
            rep["blocks"] += 1
    if val.roll_corrected:
        rep["roll_corrected"] = int(val.roll_corrected)
    return rep


# ── RUN LEVEL (validate.dd_pct) ─────────────────────────────────────────────────────────────────────
def chain_fold(fr_row):
    """The fields of one primary walk-forward fold row the chain needs, copied before validate pops the
    per-trade arrays off it."""
    g = fr_row.get
    return {"fold": g("fold"), "a": g("test_start"), "b": g("test_end"),
            "a_ts": g("test_start_ts"), "b_ts": g("test_end_ts"),
            "oos_pnl": g("oos_pnl"), "oos_trades": g("oos_trades"),
            "ei": list(g("_oos_ei") or []), "xi": list(g("_oos_xi") or []),
            "pnl": list(g("_oos_pnlf") if g("_oos_pnlf") is not None else (g("_oos_pnls") or [])),
            "side": (list(g("_oos_side")) if g("_oos_side") is not None else None),
            "px": (list(g("_oos_px")) if g("_oos_px") is not None else None),
            "cfp": g("_oos_cfp")}


def _chain_trades(fr, chain):
    """(trades, offsets, net points, lo bar, hi bar) of the WF chain on the whole-window frame."""
    trades, offs, net = [], [], 0.0
    lo = hi = None
    for fd in chain:
        a, b = fd.get("a"), fd.get("b")
        try:
            a, b = int(a), int(b)
        except (TypeError, ValueError):
            raise Refused("FOLD_TS", "fold %s carries no test bounds" % fd.get("fold"))
        if not (0 <= a < b <= fr.n):
            raise Refused("FOLD_TS", "fold %s bounds [%d, %d) are outside the window's %d bars"
                          % (fd.get("fold"), a, b, fr.n))
        # the tape must not have moved under the bar indices (a fill inserts bars: FOLD BOUNDS = BAR INDICES)
        if not fd.get("a_ts") or str(fr.index[a]) != str(fd.get("a_ts")):
            raise Refused("FOLD_TS", "fold %s starts at %s on the saved run, %s on these bars"
                          % (fd.get("fold"), fd.get("a_ts"), fr.index[a]))
        if fd.get("b_ts") and str(fr.index[b - 1]) != str(fd.get("b_ts")):
            raise Refused("FOLD_TS", "fold %s ends at %s on the saved run, %s on these bars"
                          % (fd.get("fold"), fd.get("b_ts"), fr.index[b - 1]))
        # same stamps are not the same tape: a restatement keeps them and changes the closes, and the
        #   marks would then mix new closes with the fold's old fill prices (run_auto's _oos_cfp)
        if fd.get("cfp") and close_fp(fr.close[a:b]) != fd.get("cfp"):
            raise Refused("TAPE_MOVED", "fold %s's closes changed between the walk-forward and the "
                                        "gate-stage load" % fd.get("fold"))
        ei, xi, pn = fd.get("ei") or [], fd.get("xi") or [], fd.get("pnl") or []
        side, px = fd.get("side"), fd.get("px")
        k = int(fd.get("oos_trades") or 0)
        if not (len(ei) == len(xi) == len(pn) == k) or (side is not None and len(side) != k) \
                or (px is not None and len(px) != k):
            raise Refused("MEMBERSHIP", "fold %s carries %d/%d/%d trade fields for %d trades"
                          % (fd.get("fold"), len(ei), len(xi), len(pn), k))
        for j in range(k):
            trades.append((ei[j], xi[j], pn[j], side[j] if side is not None else None,
                           px[j] if px is not None else None))
            offs.append(a)
        net += float(fd.get("oos_pnl") or 0.0)
        lo = a if lo is None else min(lo, a)
        hi = b - 1 if hi is None else max(hi, b - 1)
    return trades, offs, net, lo, hi


def validate_dd(money, arrays, *, full=None, gate=None, wf_split=None, chain=None, lb=None,
                lb_from=None, roll=None, cache=None, code_sha="", cut_rule=None, unsized=None,
                lb_tape=None, log=print):
    """The run-level block: (dd_pct, dd_pct_src).

    dd_pct = {"is", "wf", "lb", "wf_lb", "full": {"dd_pct_peak", "dd_usd", "marked"} | None}; a null
    stretch's reason is in dd_pct_src["reasons"] (decision 7). Every stretch lives on the whole-window
    arrays `arrays` (opt_from..date_to): IS and FULL are the champion's cold whole-window trades (`full`),
    the WF chain sits at each fold's test_start, the lockbox at the first bar of lb_from (the warm
    runner's own rebase). Each series is cent-checked against the stored net: gate_validate's
    ungated_is / ungated_full when the gate ran (else the trades' own sum), the folds' oos_pnl, and
    validate.lockbox.pnl.

    SAME TAPE. Each stretch's trades must sit on the bars they were made on: full by its _meta.bars
    count, every chain fold by its start / end stamps and (run_auto's _oos_cfp) its closes, the lockbox
    by `lb_tape` (the warm runner's bar count, end stamps and closes; tape_of) or else its own
    _meta.bars. A mismatch is TAPE_MOVED / FOLD_TS for that stretch, never a valued figure.

    ISOLATION. Any error inside one stretch nulls that stretch with its reason; the others are still
    valued and written."""
    src = {"src": "validate", "v": VERSION, "start": start_usd(), "membership": "entry",
           "code_sha": code_sha or "", "repro": "EXACT", "masked_bars": 0, "cut_rule": cut_rule}
    if money is None:
        src.update(status="UNSIZED", reason=unsized or "UNSIZED")
        return None, src
    mult = float(money["mult"])
    src.update(mult=mult, mult_src=money.get("mult_src"))
    out = {k: None for k in STRETCHES}
    reasons, unmarked, net_ref = {}, {}, {}

    def _no(name, why):
        code, k, text = why
        reasons[name] = "%s: %s" % (code, text)
        if code == "UNMARKED":
            unmarked[name] = int(k)

    def _put(name, rw):
        r, why = rw
        out[name] = r
        if r is None:
            _no(name, why)

    if arrays is None:
        for k in STRETCHES:
            _no(k, ("NO_ARRAYS", 0, "the whole-window price arrays did not load"))
    else:
        try:
            fr = frame_for(cache if isinstance(cache, dict) else {}, arrays)
        except Exception as e:
            fr = None
            for k in STRETCHES:
                _no(k, _why_of(e))
    if arrays is not None and fr is not None:
        src["day_rule"] = fr.rule
        if roll:
            src["roll"] = {"root": roll.get("root"), "kind": roll.get("kind"), "corrected": 0}
        gate = gate if isinstance(gate, dict) else {}
        tape = {}

        # ── is + full: the champion's cold whole-window trades ──
        ft = list((full or {}).get("trades") or []) if isinstance(full, dict) else []
        if not ft:
            _no("full", ("NO_TRADES", 0, "the whole-window backtest returned no trades"))
            _no("is", ("NO_TRADES", 0, "the whole-window backtest returned no trades"))
        else:
            try:
                bars = ((full.get("_meta") or {}).get("bars"))
                if bars is not None and int(bars) != fr.n:
                    raise Refused("FRAME", "the whole-window backtest ran on %d bars, the arrays hold %d"
                                  % (int(bars), fr.n))
                tape["full"] = "bars" if bars is not None else "unchecked"
                fsz = aligned_sizes(full, ft)
                vf = Valuation(fr, ft, mult, sizes=fsz, sized_file=emits_sizes(full) or folds_size(fsz),
                               roll=roll)
                if roll:
                    src["roll"]["corrected"] += int(vf.roll_corrected)
                allm = np.ones(len(ft), dtype=bool)
                ug = gate.get("ungated_full") if isinstance(gate.get("ungated_full"), dict) else None
                if ug is not None:
                    exp, n_exp, net_ref["full"] = ug.get("total_pnl"), ug.get("num_trades"), "gate_validate.ungated_full"
                else:
                    exp, n_exp, net_ref["full"] = full.get("total_pnl"), len(ft), "whole-window backtest"
                _put("full", safe_reading(vf, allm, 0, fr.n - 1, (None if exp is None else float(exp) * mult),
                                          expect_n=n_exp))
                if wf_split is None:
                    _no("is", ("NO_WF_SPLIT", 0, "no walk-forward fold gave an IS | WF split"))
                else:
                    try:
                        eb = np.minimum(np.asarray([int(t[0]) for t in ft], dtype=np.int64), fr.n - 1)
                        ism = fr.ns[eb] < _ts_ns(wf_split, fr.index)
                        cut = fr.bar_at(wf_split)
                        ui = gate.get("ungated_is") if isinstance(gate.get("ungated_is"), dict) else None
                        if ui is not None:
                            exp, n_exp, net_ref["is"] = ui.get("total_pnl"), ui.get("num_trades"), "gate_validate.ungated_is"
                        else:
                            exp, n_exp, net_ref["is"] = (math.fsum(vf.pnl[ism]), int(ism.sum()),
                                                         "whole-window backtest")
                        _put("is", safe_reading(vf, ism, 0, cut - 1,
                                                (None if exp is None else float(exp) * mult), expect_n=n_exp))
                    except Exception as e:
                        _no("is", _why_of(e))
            except Exception as e:
                for k in ("full", "is"):
                    if k not in reasons and out[k] is None:
                        _no(k, _why_of(e))

        # ── wf (the chain), lb, wf_lb: one valuation on the same frame ──
        try:
            ctr, coffs, cnet, clo, chi = ([], [], 0.0, None, None)
            chain_why = None
            if not chain:
                chain_why = ("NO_WF", 0, "walk-forward did not run")
            else:
                try:
                    ctr, coffs, cnet, clo, chi = _chain_trades(fr, chain)
                    tape["wf"] = "ends+closes" if all(fd.get("cfp") for fd in chain) else "ends"
                except Exception as e:
                    chain_why = _why_of(e)
                    ctr, coffs = [], []
            ltr = list((lb or {}).get("trades") or []) if isinstance(lb, dict) else []
            lb_why, lb_i = None, None
            if not isinstance(lb, dict):
                lb_why = ("NO_LOCKBOX", 0, "the lockbox did not run")
            elif not lb_from:
                lb_why = ("NO_LOCKBOX", 0, "no lockbox start date")
            else:
                lb_i = fr.bar_at(pd.Timestamp(str(lb_from)[:10], tz="US/Eastern"))
                if not (0 < lb_i < fr.n):
                    lb_why = ("FRAME", 0, "the lockbox start is bar %d of %d" % (lb_i, fr.n))
                else:
                    try:
                        moved = _tape_moved(fr, lb_i, lb_tape, lb)
                    except Exception as e:
                        moved = "its tape could not be compared (%s)" % type(e).__name__
                    if moved:
                        lb_why = ("TAPE_MOVED", 0, "the lockbox: " + moved)
                    else:
                        tape["lb"] = ("bars+ends+closes" if isinstance(lb_tape, dict) and lb_tape else
                                      ("bars" if ((lb.get("_meta") or {}).get("bars") is not None)
                                       else "unchecked"))
            if lb_why is not None:
                ltr = []
            lsz = aligned_sizes(lb, ltr) if ltr else None
            # critic C3: the chain's folds crowned their own params and carry no sizes, so a file that
            #   sizes its trades at all leaves the chain's multi-day trades SIZE_UNKNOWN, whatever the
            #   whole-run champion's own sizes are
            sized_file = emits_sizes(full, lb) or folds_size(lsz)
            sizes = None
            if sized_file:
                sizes = [None] * len(ctr) + (list(lsz) if lsz is not None else [None] * len(ltr))
            vc = Valuation(fr, ctr + ltr, mult, offsets=coffs + [int(lb_i or 0)] * len(ltr),
                           sizes=sizes, sized_file=sized_file, roll=roll)
            if roll:
                src["roll"]["corrected"] += int(vc.roll_corrected)
            nc = len(ctr)
            if chain_why is None:
                wm = np.zeros(len(vc), dtype=bool)
                wm[:nc] = True
                net_ref["wf"] = "walk-forward folds oos_pnl"
                _put("wf", safe_reading(vc, wm, clo, chi, cnet * mult, expect_n=nc))
            else:
                _no("wf", chain_why)
            lnet = None
            if lb_why is None:
                lnet = float(lb.get("total_pnl") or 0.0)
                lm = np.zeros(len(vc), dtype=bool)
                lm[nc:] = True
                net_ref["lb"] = "validate.lockbox.pnl"
                _put("lb", safe_reading(vc, lm, lb_i, fr.n - 1, lnet * mult, expect_n=lb.get("num_trades")))
            else:
                _no("lb", lb_why)
            if out["wf"] is not None and out["lb"] is not None:
                # ONE daily series: the chain, then the lockbox (a shared day sums)
                _put("wf_lb", safe_reading(vc, np.ones(len(vc), dtype=bool), clo, fr.n - 1,
                                           (cnet + lnet) * mult, expect_n=len(vc)))
            else:
                _no("wf_lb", ("NEEDS_WF_AND_LB", 0, "the WF chain and the lockbox must both be valued"))
        except Exception as e:
            for k in ("wf", "lb", "wf_lb"):
                if out[k] is None and k not in reasons:
                    _no(k, _why_of(e))
        if tape:
            src["tape"] = tape

    ok = sum(1 for k in STRETCHES if out[k] is not None)
    src["status"] = "OK" if ok == len(STRETCHES) else ("PARTIAL" if ok else "NONE")
    if reasons:
        src["reasons"] = reasons
    if unmarked:
        src["unmarked"] = unmarked
    if net_ref:
        src["net_ref"] = net_ref
    if log is not None:
        for k in STRETCHES:
            if k in reasons:
                log("[validate] stretch_dd %s: skipped - %s" % (k, reasons[k]))
    return out, src
