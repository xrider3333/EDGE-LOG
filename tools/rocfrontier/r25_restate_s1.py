"""EDRIFT r1 and NEWISSUE r1 - RESTATED UNDER MANAGER's HYGIENE EDIT S1 (MANAGER #565, 'restate EDRIFT 2.85 / NEWISSUE 2.87 under S1 as one-line report restatements; verdicts stay dead'; 2026-10-08).

Both families were judged on the REGISTERED reading, post_mode 'remove': a name flagged anywhere inside the hold (a registered split, the gap scan, TBIS, a raw gap beyond +-50%, a spin-off / stock-dividend ex-date) was removed
before the ranking - look-ahead (a name is dropped because of what happened after the rank). MANAGER's hygiene edit S1 (#127; r17_resmom's post_mode 'close', [HYG-S1] in the code) removes no name for an in-hold event: every flagged name
stays on the split-safe path, and a spin-off / stock-dividend ex-date e inside the hold (f < e <= x) closes the position at the official close of e-1 (no mark, dividend or borrow after it, the exit cost on that row). r19_edrift and
r20_newissue carry that reading as post_mode 'close' (the registered 'remove' reading is byte for byte unchanged).

For each family this builds the registered WF world exactly as the harness's stage_a does (the same loaders, checks, audit file and refusals, up to its first evaluate; nothing is judged, nothing is written but the result file, the
sealed year is never read: every loader cuts before 2025-06-30), then
  1. evaluates the registered cells under 'remove' with NO null and REFUSES unless every cell's WF net reproduces the registered Stage A record (<family>_stageA.json in the family's OUT) within $1 (and its positions / rebalances
     exactly) - nothing else is computed or written before that;
  2. puts the calendar's splits on the grid (counted under 'close', never a removal) and evaluates the same cells under 'close', no null;
  3. prints, per cell, the WF ROC @ $30k, DD5 (the owner's yardstick: the mean depth of the 5 deepest non-overlapping drawdown episodes of the cell's daily curve on the same stretch as the ROC; augur_engine.drawdowns.dd5; 'driven by one
     episode' when the worst drawdown is more than 1.3 x DD5), the worst drawdown, the net and dollars a year and the Sortino, REGISTERED -> S1, with the pool counts (names kept with an in-hold flag, calendar splits kept, positions closed
     before a spin-off / stock-dividend ex-date) and the one-line restatement text; the verdict is stated 'unchanged DEAD' only while every cell stays under the registered ROC bar (b) of 15 - then Stage A still fails whatever the null
     (no null is drawn here); otherwise the line says REVIEW;
  4. lists, per cell, the POSITIONS S1 MOVES (MANAGER's addition to #565, 2026-10-08): the ones S1 ADDS (in 'close', not in 'remove'), the ones it CHANGES (in both, a different P&L: a close, a new hedge ratio, a new match) and, as a count and a sum, the ones it
     DISPLACES (in 'remove', not in 'close': the extra names move the ranking's cut); the top 10 of each by |P&L| (a change: by |the P&L it moved|) with symbol, rank date, side, the in-hold reason 'remove' dropped it for (split / gap / tbis / jump / spin; a calendar
     split is added when the calendar has one - 'remove' never read it), P&L and the largest one-day move inside the hold; and the share of the cell's net change that the top 3 movers explain (the rest: the other movers and the displaced positions);
  5. writes <family>_restate_close.json beside the family's Stage A file (refuses to overwrite an existing file that differs; an identical re-run is a no-op; --force-report rewrites a file whose registered and S1 numbers are ALL identical to this run's, to add the
     keys it lacks - the movers - and changes nothing it holds).
The reference book (#463 + 0.264 x RES) is loaded as stage_a loads it (evaluate needs it) and is NOT restated here: the reference-relative rows (A2, DO / rho_dd) are not reported - that restatement is RESMOM's own ledger row.
CHOICE (NEWISSUE cell E): the ES hedge is the basket's - beta x the rebalance's short notional, sized at the rank and run to the exit session - so the hedge share of a NEW short closed before an ex-date is NOT cut; S1 closes the stock
position. The closed NEW shorts and matched longs are counted below, so the size of that choice is on the page.
usage (from the worktree, EDGELOG_ROOT = the shared checkout; the real runs need several GB: run them under the memory guard):
  python tools/rocfrontier/r25_restate_s1.py edrift|newissue|both [--force-report]
  python tools/rocfrontier/r25_restate_s1.py --selftest [quick]     synthetic worlds only (toy worlds + the harnesses' synthetic markets; 'quick' skips the markets); no real data is read or written"""
import contextlib, gc, hashlib, io, json, math, os, sys, tempfile, time
from collections import Counter
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import numpy as np                                                              # noqa: E402
import pandas as pd                                                             # noqa: E402
import r17_resmom as M17                                                        # noqa: E402  (the engine: 'close', rm_units, l1_pnl_x, attach_calendar_splits)
import r19_edrift as ED                                                         # noqa: E402  (EDRIFT r1: its stage_a world, evaluate, post_mode 'close')
import r20_newissue as NI                                                       # noqa: E402  (NEWISSUE r1: the same)
from augur_engine.drawdowns import dd5 as _dd5                                  # noqa: E402  (the owner's DD5, MANAGER #120; the repo root is on the path through r11_risk)

DV, D15, A13, R11, S = ED.DV, M17.D15, M17.A13, M17.R11, M17.S
TS = pd.Timestamp
REG, S1 = "remove", "close"                                                      # the registered reading and S1's (r17_resmom's 'close', [HYG-S1])
NET_TOL = 1.0                                                                    # the registered Stage A net must be reproduced within $1 (MANAGER's rule for this run)
DD_TOL = 0.02                                                                    # DD5's worst episode equals the ROC figure's worst drawdown to the cent (augur_engine.drawdowns)
TOP_N = 10                                                                       # the movers listed per cell and group
MOVER_TOL = 1e-9                                                                 # a position in both readings whose P&L differs by more than this ($) is CHANGED
NUM_TOL = 1e-9                                                                   # --force-report: a number on file equals this run's to within NUM_TOL (relative; a deterministic re-run is bit for bit)
USAGE = ("usage: r25_restate_s1.py edrift | newissue | both [--force-report]   (the real runs: several GB, under the memory guard)\n"
         "       r25_restate_s1.py --selftest [quick]            (synthetic worlds only; 'quick' skips the harnesses' synthetic markets)")


def refuse(msg):
    raise SystemExit(msg)


def usd(v, nd=0):
    """-$1,234 / $1,234 (nan -> nan)"""
    if not math.isfinite(v):
        return "nan"
    return ("-" if v < 0 else "") + f"${abs(v):,.{nd}f}"


# ------------------------------------------------------------------ the two worlds, call for call as each harness's stage_a builds them (up to its first evaluate)
def world_edrift():
    """r19_edrift.stage_a's world: the prereg, the wide calendar, #463 and its checks, the reference line, the cache manifest, the data / TBIS / ES loaders (cut at 2025-06-30), the audit file, build_world, the cut checks, the Russell list, the audit
    rows, #463's rows on the World and the event arrays [E1]. (stage_a's earnings-calendar read feeds the [E5'] report only - never a cell's P&L - and is not repeated.) -> w with W, B, S12, ref, rows, cal"""
    ED.prereg_ok()
    cal, _winfo = M17.wide_load(ED.S.LB0)
    B, _legs_meta = ED.A13.load_463()
    bk, dd, S12 = ED.book_checks(B)
    print(f"BOOK #463 WF check (must be {ED.BOOK_WF[0]} / {ED.BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${ED.DEEPEST_WF:,.0f})", flush=True)
    if ED.CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("restatement refused: the #463 records do not reproduce the registered WF numbers / drawdown structure (nothing computed)")
    ref = ED.DV.ref_load(B, check_facts=ED.CHECK_BOOK)
    msha = ED.manifest_sha()
    if ED.CHECK_BOOK and not (msha and msha.startswith(ED.D15.MANIFEST_PREFIX)):
        refuse("restatement refused: the SIPORB cache manifest is missing or is not the registered photograph of the vendor (nothing computed)")
    t0 = time.time()
    D = M17.load_data(ED.S.LB0)
    tbis = ED.D15.load_tbis(ED.S.LB0)
    es_frames, _es_meta = ED.D15.load_es(ED.S.LB0)
    audit = ED.read_audit()
    W = M17.build_world(D, ED.S.LB0, es_frames, tbis, cal)
    ED.D15.release(D)
    ED.cut_checks(W, cal, ED.S.LB0)
    ED.check_russell(W.days)
    ED.apply_audit(W, audit)
    rows = ED.A13.book_rows(B, W)
    ED.attach_events(W)
    print(f"EDRIFT world ready ({time.time() - t0:.0f}s): {W.T:,} sessions ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}), {W.S:,} names ever in the universe, audit file: {'none' if audit is None else str(len(audit)) + ' rows'}", flush=True)
    return SimpleNamespace(W=W, B=B, S12=S12, ref=ref, rows=rows, cal=cal)


def world_newissue():
    """r20_newissue.stage_a's world: the prereg, the wide calendar and its two tables, #463 and its checks, the reference line, the cache manifest, the loaders, the audit file, build_world, the cut checks, the first-session check, the listing /
    calendar / ES context, the audit rows, #463's rows on the World and the two drawdown-day stretches. -> w with W, ctx, B, S12, SN, SRN, ref, rows, cal"""
    NI.prereg_ok()
    cal, _winfo = M17.wide_load(NI.S.LB0)
    extra, _einfo = NI.cal_extra(NI.S.LB0)
    B, _legs_meta = NI.A13.load_463()
    bk, dd, S12 = NI.book_checks(B)
    print(f"BOOK #463 WF check (must be {NI.BOOK_WF[0]} / {NI.BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${NI.DEEPEST_WF:,.0f})", flush=True)
    if NI.CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("restatement refused: the #463 records do not reproduce the registered WF numbers / drawdown structure (nothing computed)")
    ref = NI.DV.ref_load(B, check_facts=NI.CHECK_BOOK)
    msha = NI.manifest_sha()
    if NI.CHECK_BOOK and not (msha and msha.startswith(NI.D15.MANIFEST_PREFIX)):
        refuse("restatement refused: the SIPORB cache manifest is missing or is not the registered photograph of the vendor (nothing computed)")
    t0 = time.time()
    D = M17.load_data(NI.S.LB0)
    tbis = NI.D15.load_tbis(NI.S.LB0)
    es_frames, _es_meta = NI.D15.load_es(NI.S.LB0)
    audit = NI.read_audit()
    W = M17.build_world(D, NI.S.LB0, es_frames, tbis, cal)
    NI.D15.release(D)
    NI.cut_checks(W, cal, extra, NI.S.LB0)
    if NI.CHECK_BOOK and W.days[0] != NI.FIRST_SESSION:
        refuse(f"restatement refused: the cache's first session is {W.days[0]:%Y-%m-%d}, not the registered {NI.FIRST_SESSION:%Y-%m-%d} - listings would be dated from the wrong session (nothing computed)")
    ctx = NI.make_ctx(W, extra)
    NI.apply_audit(W, audit)
    rows = NI.A13.book_rows(B, W)
    SN = NI.restrict_stretch(S12, B.raw, B.index, NI.WFN, NI.PRE_END)
    SRN = NI.restrict_stretch(ref.S, ref.raw, B.index, NI.WFN, NI.PRE_END)
    print(f"NEWISSUE world ready ({time.time() - t0:.0f}s): {W.T:,} sessions ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}), {W.S:,} names ever in the universe, audit file: {'none' if audit is None else str(len(audit)) + ' rows'}", flush=True)
    return SimpleNamespace(W=W, ctx=ctx, B=B, S12=S12, SN=SN, SRN=SRN, ref=ref, rows=rows, cal=cal)


# ------------------------------------------------------------------ one reading of a family, no null
def eval_edrift(w, pm):
    return ED.evaluate(w.W, w.B, w.S12, w.ref, w.rows, pm, 0, 0, full=False)


def eval_newissue(w, pm):
    return NI.evaluate(w.W, w.ctx, w.B, w.SN, w.ref, w.SRN, w.rows, pm, 0, 0, full=False)


def picked_edrift(w, obj, cell):
    """the positions a cell trades (WF) and how many of them are closed before a spin-off / stock-dividend ex-date, by side"""
    out = {"positions": 0, "closed": 0, "closed_long": 0, "closed_short": 0, "rebalances": 0}
    for rec in obj.legs.recs:
        cc = rec.cell[cell]
        if not cc.traded:
            continue
        out["rebalances"] += 1
        out["positions"] += int(len(cc.long) + len(cc.short))
        for side, idx in (("long", cc.long), ("short", cc.short)):
            n = int((rec.close[cc.idx[idx]] >= 0).sum())
            out["closed_" + side] += n
            out["closed"] += n
    return out


def picked_newissue(w, obj, cell):
    """the positions a cell trades (WF; one NEW short each, E: with its share of the ES hedge, M: with its matched SEASONED long) and how many of the NEW shorts / matched longs are closed before a ex-date"""
    out = {"positions": 0, "closed": 0, "closed_short": 0, "closed_long": 0, "rebalances": 0}
    for rec in obj.legs.recs:
        if not NI.traded(rec, cell):
            continue
        idx = np.arange(rec.n_new) if cell == "E" else np.flatnonzero(rec.match >= 0)
        if not len(idx):
            continue
        out["rebalances"] += 1
        out["positions"] += int(len(idx))
        out["closed_short"] += int((rec.close[idx] >= 0).sum())
        if cell == "M":
            out["closed_long"] += int((rec.close[rec.match[idx]] >= 0).sum())
    out["closed"] = out["closed_short"] + out["closed_long"]
    return out


def kept_edrift(cn):
    return {"kept_flagged": int(cn.get("kept_flagged", 0)), "kept_calendar_split": int(cn.get("kept_calendar_split", 0)), "closed_spin": int(cn.get("closed_spin", 0))}


def kept_newissue(cn):
    g = lambda k: int(cn.get("new_" + k, 0) + cn.get("seas_" + k, 0))
    return {"kept_flagged": g("kept_flagged"), "kept_calendar_split": g("kept_calendar_split"), "closed_spin": g("closed_spin"), "closed_spin_new": int(cn.get("new_closed_spin", 0)), "closed_spin_seasoned": int(cn.get("seas_closed_spin", 0))}


def removed_edrift(cn):
    return int(sum(cn.get(f"post_{h}", 0) for h in ED.HYG) + cn.get("post_spin", 0))


def removed_newissue(cn):
    return int(sum(cn.get(f"{pf}post_{h}", 0) for pf in ("new_", "seas_") for h in NI.HYG) + cn.get("new_post_spin", 0) + cn.get("seas_post_spin", 0))


# the movers' two family hooks: a cell's positions keyed for the comparison, and what else moves a position of the family (the movers section below)
def positions_edrift(obj, cell):
    """{(rebalance, column, side): the position's net P&L in $} of a cell's WF positions - the run's per-position table (costs, borrow and dividends in; side +1 long / -1 short). The rebalance is the index into the leg's records (the two readings share one schedule)"""
    p = obj.runs[cell].pos
    out = {(int(a), int(b), int(s)): float(v) for a, b, s, v in zip(p.rec, p.col, p.side, p.pnl)}
    if len(out) != len(p.rec):
        refuse(f"restatement refused: EDRIFT {cell}: a name is held twice in one rebalance - the position table cannot be keyed (nothing written)")
    return out


def positions_newissue(obj, cell):
    """{(rebalance, NEW column, -1): net P&L in $} - a position is the NEW name's short with its other side (E: its share of the beta-sized ES hedge; M: the matched SEASONED long), as the run's table books it"""
    p = obj.runs[cell].pos
    out = {(int(a), int(b), -1): float(v) for a, b, v in zip(p.rec, p.col, p.pnl)}
    if len(out) != len(p.rec):
        refuse(f"restatement refused: NEWISSUE {cell}: a NEW name appears twice in one rebalance - the position table cannot be keyed (nothing written)")
    return out


def extra_edrift(w, obj0, obj1, cell, ri, col, i):
    """EDRIFT: a position's P&L moves only when S1 closes it (its path is the name's own, the size is the slot) -> (extra fields, reasons it changed)"""
    return {}, []


def extra_newissue(w, obj0, obj1, cell, ri, col, i):
    """NEWISSUE: besides a close, a NEW short's P&L moves with its other side - E: the hedge ratio (the basket's beta moves with the NEW set); M: the matched long (the match moves with the pool) and its own close -> (extra fields, reasons it changed)"""
    W = w.W
    r1, r0 = obj1.legs.recs[ri], obj0.legs.recs[ri]
    i0 = np.flatnonzero(r0.pool == col)
    i0 = int(i0[0]) if len(i0) else -1
    out, why = {}, []
    if cell == "M":
        m1 = int(r1.match[i])
        out["mate"] = str(W.syms[r1.pool[m1]]) if m1 >= 0 else ""
        if m1 >= 0 and int(r1.close[m1]) >= 0:
            out["mate_closed_on"] = f"{W.days[int(r1.close[m1])]:%Y-%m-%d}"
            why.append(f"matched long closed {out['mate_closed_on']}")
        if i0 >= 0:
            m0 = int(r0.match[i0])
            out["mate_registered"] = str(W.syms[r0.pool[m0]]) if m0 >= 0 else ""
            if out["mate_registered"] != out["mate"]:
                why.append(f"matched long {out['mate_registered'] or '-'} -> {out['mate'] or '-'}")
    elif i0 >= 0:
        b0, b1 = float(r0.beta), float(r1.beta)
        out["hedge_ratio"], out["hedge_ratio_registered"] = b1, b0
        if not (abs(b0 - b1) <= 1e-12 or (math.isnan(b0) and math.isnan(b1))):
            why.append(f"hedge ratio {b0:.3f} -> {b1:.3f}")
    return out, why


FAMILIES = {
    "edrift": SimpleNamespace(key="edrift", name="EDRIFT", mod=ED, cells=ED.CELLS, lo=ED.WF0, hi=ED.PRE_END, stage_file="edrift_stageA.json", out_file="edrift_restate_close.json", world=world_edrift, evaluate=eval_edrift,
                              picked=picked_edrift, kept=kept_edrift, removed=removed_edrift, positions=positions_edrift, extra=extra_edrift),
    "newissue": SimpleNamespace(key="newissue", name="NEWISSUE", mod=NI, cells=NI.CELLS, lo=NI.WFN, hi=NI.PRE_END, stage_file="newissue_stageA.json", out_file="newissue_restate_close.json", world=world_newissue, evaluate=eval_newissue,
                                picked=picked_newissue, kept=kept_newissue, removed=removed_newissue, positions=positions_newissue, extra=extra_newissue),
}


def total_counts(L):
    """the leg's counters summed over the fill years"""
    tot = Counter()
    for cn in L.cnt.values():
        tot.update(cn)
    return {k: int(v) for k, v in tot.items()}


def dd5_rec(B, x, lo, hi):
    """DD5 of a daily series x (on #463's index) over [lo, hi] - the same curve and stretch the ROC figure uses: the mean depth of the 5 deepest non-overlapping drawdown episodes, the worst drawdown, the one-episode flag (worst > 1.3 x DD5), the
    episodes (deepest first)"""
    k = B.mask(lo, hi)
    r = _dd5(pd.Series(np.asarray(x, float)[k], index=pd.DatetimeIndex(B.index[k])))
    eps = [{"peak": e["peak"], "trough": e["trough"], "recovered": e["recovered"], "depth": float(e["depth"]), "open": bool(e["open"])} for e in r["episodes"]]
    return {"dd5": float(r["dd5_usd"]), "n": int(r["n"]), "max_dd": float(r["max_dd"]), "one_episode": bool(r["one_episode"]), "episodes": eps}


def cell_rec(fam, w, res, obj, cell):
    """one cell of one reading: the WF statistics beside the DD5 of the same daily curve"""
    st = res["cells"][cell]["base"]
    dd = dd5_rec(w.B, obj.series[cell][0], fam.lo, fam.hi)
    if not abs(dd["max_dd"] - st["max_dd"]) <= DD_TOL:
        refuse(f"restatement refused: {fam.name} {cell}: DD5's worst episode ${dd['max_dd']:,.2f} is not the ROC figure's worst drawdown ${st['max_dd']:,.2f} - the two are not on the same curve (nothing written)")
    return {"roc": float(st["roc"]), "sortino": float(st["sortino"]), "net": float(st["net"]), "years": float(st["years"]), "usd_year": float(st["net"]) / float(st["years"]), "max_dd": float(st["max_dd"]), "dd5": dd["dd5"], "dd5_n": dd["n"],
            "one_episode": dd["one_episode"], "episodes": dd["episodes"], "n_pos": int(st["n_pos"]), "n_units": int(st["n_units"]), "years_pos": int(st["years_pos"]), "net_10bps": float(res["cells"][cell]["stress"]["10 bps"]["net"])}


# ------------------------------------------------------------------ the movers: the positions S1 adds and changes
def reasons_of(W, rec, col):
    """the in-hold events of a name in rank rebalance `rec`, the ones 'remove' drops a name for: the four hygiene reasons on rows r+1 .. x (split / gap / tbis / jump) and a [D2] spin-off / stock-dividend ex-date on rows f+1 .. x (spin); plus 'calendar split' when the calendar's
    splits are on the grid and one falls in f+1 .. x ('remove' never read the calendar's splits: it is counted under S1 and listed here only as a marker) -> list of labels"""
    c = np.array([col])
    hy = W.hyg(rec.r + 1, rec.x, c)[:, 0]
    out = [h for q, h in enumerate(M17.HYG) if hy[q]]
    if M17.spn_hit(W, rec.f + 1, rec.x, c)[0]:
        out.append("spin")
    if getattr(W, "cscs", None) is not None and M17.csplit_hit(W, rec.f + 1, rec.x, c)[0]:
        out.append("calendar split")
    return out


def biggest_move(W, rec, i):
    """the largest one-day move of pool name i inside its hold, on the split-safe prices the P&L reads: the entry open -> the close of the fill session -> each close -> the exit open (a position S1 closes before an ex-date: up to the close of e-1, the cut path's last level; a missing
    bar carries the last mark, a move of zero) -> (the signed move of the STOCK, the session it falls on; nan / None when no move is defined)"""
    U = rec.U
    H = rec.x - rec.f + 1
    xc = H - 1 if getattr(U, "xc", None) is None else int(U.xc[i])
    lev = np.concatenate([np.asarray(U.mk[i, :xc + 1], float), [float(U.ve[i])]])
    with np.errstate(invalid="ignore", divide="ignore"):
        mv = lev[1:] / lev[:-1] - 1.0
    ok = np.isfinite(mv)
    if not ok.any():
        return float("nan"), None
    k = int(np.argmax(np.where(ok, np.abs(mv), -1.0)))
    return float(mv[k]), W.days[rec.f + k]


def mover_row(fam, w, obj0, obj1, cell, key, p1, p0):
    """one listed position: who, when, which side, what 'remove' dropped it for (an add) or what moved its P&L (a change), the P&L under S1 (and under 'remove'), the effect on the cell's net (an add: its S1 P&L; a change: the P&L it moved) and the largest one-day move inside the hold"""
    ri, col, side = key
    W = w.W
    rec = obj1.legs.recs[ri]
    i = int(np.flatnonzero(rec.pool == col)[0])
    mv, mvd = biggest_move(W, rec, i)
    rs = reasons_of(W, rec, col)
    cl = int(rec.close[i])
    extra, why = fam.extra(w, obj0, obj1, cell, ri, col, i)
    if cl >= 0:
        why = [f"closed {W.days[cl]:%Y-%m-%d}"] + why
    add = p0 is None
    row = {"kind": "add" if add else "change", "symbol": str(W.syms[col]), "rank_date": f"{W.days[rec.r]:%Y-%m-%d}", "fill": f"{W.days[rec.f]:%Y-%m-%d}", "exit": f"{W.days[rec.x]:%Y-%m-%d}", "side": "long" if side > 0 else "short",
           "reason": " + ".join(rs) if rs else ("none - the extra names moved the ranking's cut" if add else "-"), "pnl": float(p1), "pnl_registered": None if add else float(p0), "effect": float(p1 - (0.0 if add else p0)),
           "max_move": mv, "max_move_date": None if mvd is None else f"{mvd:%Y-%m-%d}", "closed": cl >= 0, "closed_on": f"{W.days[cl]:%Y-%m-%d}" if cl >= 0 else None, "why": "; ".join(why) if not add else "-", **extra}
    return row


def movers(fam, w, obj0, obj1, cell, d_net, top=TOP_N):
    """a cell's positions S1 moves: ADDS (in 'close', not in 'remove'), CHANGES (in both, a P&L that differs by more than MOVER_TOL) and the DISPLACED (in 'remove', not in 'close': counted and summed, not listed); the top `top` adds by |P&L| and changes by |the P&L moved|, each with its
    detail row; the cell's net change d_net against what the three groups add up to (residual: the positions' table against the daily series' net - zero when both read the same days); the three biggest movers over adds and changes and the share of d_net they explain -> dict"""
    L0, L1 = obj0.legs.recs, obj1.legs.recs
    if len(L0) != len(L1) or any((a.r, a.f, a.x) != (b.r, b.f, b.x) for a, b in zip(L0, L1)):
        refuse(f"restatement refused: {fam.name} {cell}: the two readings do not share one rebalance schedule - the positions cannot be matched (nothing written)")
    P0, P1 = fam.positions(obj0, cell), fam.positions(obj1, cell)
    adds = {k: v for k, v in P1.items() if k not in P0}
    chg = {k: (P0[k], v) for k, v in P1.items() if k in P0 and abs(v - P0[k]) > MOVER_TOL}
    gone = {k: v for k, v in P0.items() if k not in P1}
    s_add, s_chg, s_gone = sum(adds.values()), sum(b - a for a, b in chg.values()), sum(gone.values())
    eff = {**adds, **{k: b - a for k, (a, b) in chg.items()}}
    order = lambda d, f_: sorted(d, key=lambda k: (-abs(f_(d[k])), k))
    t_add, t_chg = order(adds, lambda v: v)[:top], order(chg, lambda v: v[1] - v[0])[:top]
    t3 = order(eff, lambda v: v)[:3]
    rows = {k: mover_row(fam, w, obj0, obj1, cell, k, P1[k], P0.get(k)) for k in dict.fromkeys(t_add + t_chg + t3)}
    explained = s_add + s_chg - s_gone
    e3 = float(sum(eff[k] for k in t3))
    share = e3 / d_net if math.isfinite(d_net) and abs(d_net) > 0.005 else float("nan")
    m = {"positions": {"registered": len(P0), "s1": len(P1)}, "adds": {"n": len(adds), "pnl": float(s_add), "top": [rows[k] for k in t_add]}, "changes": {"n": len(chg), "delta": float(s_chg), "top": [rows[k] for k in t_chg]},
         "displaced": {"n": len(gone), "pnl": float(s_gone)}, "net_change": float(d_net), "explained_by_positions": float(explained), "residual": float(d_net - explained),
         "top3": {"labels": [f"{rows[k]['symbol']} {rows[k]['rank_date']} {rows[k]['side']}" for k in t3], "rows": [rows[k] for k in t3], "effect": e3, "share": share}}
    m["line"] = movers_line(cell, m)
    return m


def movers_line(cell, m):
    """the cell's net change split into the three groups, and the share the top 3 movers explain"""
    t3, sh = m["top3"], m["top3"]["share"]
    names = ", ".join("%s %s %s %s" % (r["symbol"], r["rank_date"], r["side"], usd(r["effect"])) for r in t3["rows"])
    return (f"{cell}: net change {usd(m['net_change'])} = {m['adds']['n']:,} positions added {usd(m['adds']['pnl'])} + {m['changes']['n']:,} changed {usd(m['changes']['delta'])} - {m['displaced']['n']:,} displaced (in 'remove', not in S1) {usd(m['displaced']['pnl'])}"
            + (f" (residual {usd(m['residual'], 2)})" if abs(m["residual"]) > 1.0 else "")
            + f"; the top 3 movers ({names}) explain {usd(t3['effect'])} = " + (f"{sh:.0%}" if math.isfinite(sh) else "n/a") + " of it")


def print_movers(fam, cell, m):
    """the cell's movers as tables: adds, changes, the displaced count, then the net-change line"""
    for title, g, kind in ((f"ADDS - in S1, not in 'remove': {m['adds']['n']:,} positions, {usd(m['adds']['pnl'])}", m["adds"], "add"), (f"CHANGES - in both, a different P&L: {m['changes']['n']:,} positions, {usd(m['changes']['delta'])} moved", m["changes"], "change")):
        print(f"      {title}" + (f"; top {len(g['top'])} by |{'P&L' if kind == 'add' else 'P&L moved'}|" if g["top"] else ""))
        for q, r in enumerate(g["top"], 1):
            mv = "n/a" if r["max_move_date"] is None else f"{r['max_move']:+.0%} on {r['max_move_date']}"
            what = f"'remove' dropped it for: {r['reason']}" if kind == "add" else f"moved by: {r['why']}"
            pn = usd(r["pnl"]) + ("" if kind == "add" else f" (was {usd(r['pnl_registered'])})")
            mate = f", matched long {r['mate']}" if r.get("mate") else ""
            print(f"        {q:>2}. {r['symbol']:<8} rank {r['rank_date']} {r['side']:<5} {pn:>26} | {what} | largest 1-day move {mv}" + (f" | closed {r['closed_on']}" if r["closed"] else "") + mate)
    print(f"      DISPLACED - in 'remove', not in S1: {m['displaced']['n']:,} positions, {usd(m['displaced']['pnl'])} (the extra names move the ranking's cut)")
    print(f"      {m['line']}")


# ------------------------------------------------------------------ the registered record, the restatement, the text, the file
def load_registered(fam):
    """the family's registered Stage A record (<family>_stageA.json in its OUT) -> (record, path, sha256); a missing / unreadable / unjudged record refuses (the registered reading could not be verified)"""
    p = os.path.join(fam.mod.OUT, fam.stage_file)
    if not os.path.exists(p):
        refuse(f"restatement refused: the registered Stage A record {p} is not on file - the registered reading cannot be reproduced (nothing computed)")
    raw = open(p, "rb").read()
    try:
        rec = json.loads(raw.decode("utf-8"))
        ok = rec.get("judged") is True and all(c in rec["stageA"]["cells"] and "net" in rec["stageA"]["cells"][c]["base"] and c in rec["parity"] for c in fam.cells)
    except (ValueError, KeyError, TypeError):
        ok = False
    if not ok:
        refuse(f"restatement refused: {p} is not a judged Stage A record of {fam.name} (no judged flag / cells / parity block) (nothing computed)")
    return rec, p, hashlib.sha256(raw).hexdigest()


def check_registered(fam, res, rec):
    """the 'remove' reading must BE the registered one: every cell's WF net within $1 of Stage A's, its positions and rebalances exactly -> {cell: {net, registered_net, difference, n_pos, n_units}}; any miss refuses"""
    out, bad = {}, []
    for cell in fam.cells:
        got, reg, par = res["cells"][cell]["base"], rec["stageA"]["cells"][cell]["base"], rec["parity"][cell]
        d = float(got["net"]) - float(reg["net"])
        ok = math.isfinite(d) and abs(d) <= NET_TOL and int(got["n_pos"]) == int(reg["n_pos"]) and int(got["n_units"]) == int(reg["n_units"]) and abs(float(par["net"]) - float(reg["net"])) <= 1e-6
        out[cell] = {"net": float(got["net"]), "registered_net": float(reg["net"]), "difference": d, "n_pos": int(got["n_pos"]), "n_units": int(got["n_units"]), "registered_n_pos": int(reg["n_pos"]), "registered_n_units": int(reg["n_units"])}
        if not ok:
            bad.append(f"{cell}: net ${got['net']:,.2f} against the registered ${reg['net']:,.2f} (difference ${d:,.2f}; allowed ${NET_TOL:.0f}), positions {got['n_pos']} / {reg['n_pos']}, rebalances {got['n_units']} / {reg['n_units']}")
    if bad:
        refuse(f"restatement refused: the 'remove' reading does not reproduce the registered Stage A record of {fam.name} - " + "; ".join(bad) + " - nothing written")
    return out


def verdict_of(fam, cells):
    """'unchanged DEAD' only while every cell's S1 ROC @ $30k stays under the registered bar (b) (or its net is not positive): Stage A then still fails whatever a null would say; else REVIEW (this run draws no null)"""
    bar = fam.mod.RULES["roc"]
    over = [c for c in fam.cells if cells[c]["s1"]["roc"] >= bar and cells[c]["s1"]["net"] > 0]
    if not over:
        return "verdict unchanged DEAD", True
    return f"REVIEW - {', '.join(over)} clear{'s' if len(over) == 1 else ''} the ROC >= {bar:g} bar under S1 and no null is drawn here: the verdict is NOT restated", False


def line_of(fam, cells, verdict, kept, picked, removed):
    """the one-line restatement text"""
    parts = []
    for c in fam.cells:
        a, b = cells[c]["registered"], cells[c]["s1"]
        fl = lambda d: " (driven by one episode)" if d["one_episode"] else ""
        parts.append(f"{c} ROC @ $30k {a['roc']:.1f} -> {b['roc']:.1f} / DD5 {usd(a['dd5'])}{fl(a)} -> {usd(b['dd5'])}{fl(b)}, {usd(a['usd_year'])} -> {usd(b['usd_year'])} a year (net {usd(a['net'])} -> {usd(b['net'])}, worst drawdown {usd(a['max_dd'])} -> {usd(b['max_dd'])}, "
                     f"Sortino {a['sortino']:.2f} -> {b['sortino']:.2f})")
    pk = ", ".join(f"{c} {picked[c]['closed']:,} of {picked[c]['positions']:,}" for c in fam.cells)
    return (f"{fam.name} r1 restated under S1 (report; {verdict}): " + "; ".join(parts) + f". Pool name-months: {kept['kept_flagged']:,} kept with an in-hold flag, {kept['kept_calendar_split']:,} calendar splits kept, {kept['closed_spin']:,} closed before a spin-off / stock-dividend ex-date "
            f"(the registered reading removed {removed:,} for an in-hold event); traded positions closed: {pk}.")


def restate(fam, w, rec):
    """the registered reading reproduced (refuses otherwise), then S1's: -> the result record (JSON-ready), line included. Order matters: 'remove' is evaluated BEFORE the calendar's splits go on the grid (the counts of 'close' need them; 'remove' never reads them)"""
    t0 = time.time()
    res0, obj0 = fam.evaluate(w, REG)
    reproduced = check_registered(fam, res0, rec)
    print(f"  '{REG}' (the registered reading, no null) reproduces {fam.stage_file}: " + "; ".join(f"{c} net ${v['net']:,.2f} (registered ${v['registered_net']:,.2f}, difference ${v['difference']:.2f}), {v['n_pos']:,} positions / {v['n_units']} rebalances" for c, v in reproduced.items()) + f" ({time.time() - t0:.0f}s)", flush=True)
    t1 = time.time()
    csi = M17.attach_calendar_splits(w.W, w.cal)
    res1, obj1 = fam.evaluate(w, S1)
    print(f"  '{S1}' (S1, no null) done ({time.time() - t1:.0f}s); the calendar's splits placed on the grid: {csi}", flush=True)
    cells = {c: {"registered": cell_rec(fam, w, res0, obj0, c), "s1": cell_rec(fam, w, res1, obj1, c)} for c in fam.cells}
    cn0, cn1 = total_counts(obj0.legs), total_counts(obj1.legs)
    kept, removed = fam.kept(cn1), fam.removed(cn0)
    picked = {c: fam.picked(w, obj1, c) for c in fam.cells}
    mov = {c: movers(fam, w, obj0, obj1, c, cells[c]["s1"]["net"] - cells[c]["registered"]["net"]) for c in fam.cells}          # (needs both readings' objects and the World: before they go)
    verdict, dead = verdict_of(fam, cells)
    line = line_of(fam, cells, verdict, kept, picked, removed)
    by_year = {str(y): fam.kept(dict(c)) for y, c in sorted(obj1.legs.cnt.items())}
    return {"what": f"{fam.name} r1 restated under MANAGER's hygiene edit S1 (#565): registered post_mode '{REG}' reproduced, S1 = '{S1}' (r17_resmom [HYG-S1]: no in-hold removal, a spin-off / stock-dividend ex-date closes the position at the close before it); a REPORT - no null, no new search",
            "family": fam.key, "registered_post_mode": REG, "restated_post_mode": S1, "wf": [f"{fam.lo:%Y-%m-%d}", f"{fam.hi:%Y-%m-%d}"], "verdict": verdict, "still_dead": dead, "reproduced": reproduced, "cells": cells,
            "pool_counts": {"s1_kept_and_closed": kept, "s1_by_fill_year": by_year, "registered_removed_for_an_in_hold_event": removed, "s1_all": cn1, "registered_all": cn0}, "traded_positions": picked, "s1_movers": mov, "calendar_splits_on_grid": csi,
            "choice_E_hedge": "NEWISSUE cell E: the ES hedge share of a closed NEW short runs to the exit session (S1 closes the stock position); the closed NEW shorts are counted in traded_positions" if fam.key == "newissue" else None,
            "reference_note": "the reference book (#463 + 0.264 x RES) is loaded as stage_a loads it and is not restated here; no reference-relative row (A2, DO, rho_dd) is reported", "line": line}


def same_numbers(a, b, tol=NUM_TOL):
    """two JSON values equal, a number to within tol (relative, 1 as the floor); nan equals nan"""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_numbers(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_numbers(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return (math.isnan(a) and math.isnan(b)) or abs(a - b) <= tol * max(1.0, abs(a), abs(b))
    return a == b


def write_result(fam, result, stamp, force_report=False):
    """<family>_restate_close.json beside the Stage A file. An existing file that differs is never overwritten: it is 'unchanged' when everything it holds equals this run's (the stamp - the code's hash - and a report_rewritten note apart) and this run has no other key; a different number, text
    or key refuses. force_report (--force-report): a file whose keys are ALL identical to this run's (to NUM_TOL) but which lacks keys this run adds (the movers) is rewritten with them - everything it held is kept as it was, the new stamp is set and the old one is kept in
    report_rewritten with the old file's sha256; any number that differs refuses and writes nothing -> 'written' | 'unchanged' | 'rewritten'"""
    p = os.path.join(fam.mod.OUT, fam.out_file)
    new = {**result, "stamp": stamp}
    data = json.dumps(new, indent=1, default=R11.js).encode("utf-8")
    if not os.path.exists(p):
        os.makedirs(fam.mod.OUT, exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return "written"
    raw = open(p, "rb").read()
    if raw == data:
        return "unchanged"
    try:
        old = json.loads(raw.decode("utf-8"))
        assert isinstance(old, dict)
    except (ValueError, AssertionError):
        refuse(f"restatement refused: {p} is already on file and is not a readable restatement - nothing overwritten (move it aside to write a new one)")
    cur, skip = json.loads(data.decode("utf-8")), ("stamp", "report_rewritten")
    bad = [k for k in old if k not in skip and not (k in cur and same_numbers(old[k], cur[k]))]
    if bad:
        refuse(f"restatement refused: {p} is already on file and DIFFERS from this run's result in {bad} - nothing overwritten" + (" (--force-report rewrites a file only when every number on it is identical)" if force_report else " (move it aside to write a new one)"))
    added = [k for k in cur if k not in old and k not in skip]
    if not added:
        return "unchanged"
    if not force_report:
        refuse(f"restatement refused: {p} is already on file and DIFFERS from this run's result: this run adds {added}, which the file lacks - nothing overwritten (--force-report adds them when every number on the file is identical)")
    note = {"added_keys": added, "previous_stamp": old.get("stamp"), "previous_file_sha256": hashlib.sha256(raw).hexdigest()}
    if "report_rewritten" in old:
        note["earlier"] = old["report_rewritten"]
    out = {**{k: v for k, v in old.items() if k not in skip}, **{k: cur[k] for k in added}, "stamp": cur["stamp"], "report_rewritten": note}
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        f.write(json.dumps(out, indent=1, default=R11.js).encode("utf-8"))
    os.replace(tmp, p)
    return "rewritten"


def stamp_of(fam):
    """the code this ran with: this file's, the family's harness and the engine's LF sha256 (+ the harness's own stamp: r17 / r18 / r15 / siporb / r11 / r12 / r13, the pinned calendars)"""
    return {"r25_sha256": R11.sha_lf(os.path.abspath(__file__)), **fam.mod.stamp()}


def print_result(fam, result):
    print(f"\n{fam.name} r1 RESTATED UNDER S1 - WF {result['wf'][0]} .. {result['wf'][1]}; REGISTERED ('{REG}') -> S1 ('{S1}'); a report: no null is drawn")
    for c in fam.cells:
        a, b = result["cells"][c]["registered"], result["cells"][c]["s1"]
        print(f"  {c}: ROC@30k {a['roc']:.2f} -> {b['roc']:.2f} | DD5 {usd(a['dd5'])} (n={a['dd5_n']}) -> {usd(b['dd5'])} (n={b['dd5_n']}) | worst DD {usd(a['max_dd'])} -> {usd(b['max_dd'])}"
              f"{' - driven by one episode (registered)' if a['one_episode'] else ''}{' - driven by one episode (S1)' if b['one_episode'] else ''} | net {usd(a['net'])} -> {usd(b['net'])} = {usd(a['usd_year'])} -> {usd(b['usd_year'])} a year | Sortino {a['sortino']:.3f} -> {b['sortino']:.3f} "
              f"| net at 10 bps {usd(a['net_10bps'])} -> {usd(b['net_10bps'])} | {b['n_pos']:,} positions / {b['n_units']} rebalances (registered {a['n_pos']:,} / {a['n_units']})")
        print("      S1 DD5 episodes: " + "; ".join(f"{e['peak']}..{e['trough']} {usd(e['depth'])}{' (open)' if e['open'] else ''}" for e in b["episodes"]))
        pk = result["traded_positions"][c]
        print(f"      traded positions closed before a spin-off / stock-dividend ex-date: {pk['closed']:,} of {pk['positions']:,} (short side {pk['closed_short']:,}, " + ("matched longs" if fam.key == "newissue" else "long side") + f" {pk['closed_long']:,})")
        print_movers(fam, c, result["s1_movers"][c])
    k = result["pool_counts"]["s1_kept_and_closed"]
    print(f"  pool name-months under S1: kept with an in-hold flag {k['kept_flagged']:,}, calendar splits kept {k['kept_calendar_split']:,}, closed before an ex-date {k['closed_spin']:,}"
          + (f" (NEW {k['closed_spin_new']:,}, SEASONED {k['closed_spin_seasoned']:,})" if fam.key == "newissue" else "") + f"; the registered reading removed {result['pool_counts']['registered_removed_for_an_in_hold_event']:,} for an in-hold event")
    if fam.key == "newissue":
        print("  CHOICE: cell E's ES hedge share of a closed NEW short runs to the exit session (S1 closes the stock position); the closed NEW shorts are counted above")
    print(result["line"])


def run_family(key, force_report=False):
    """the whole restatement of one family: the registered record first (cheap), the world, the two readings, the result file (force_report: add the movers to a file whose numbers are identical) -> the result"""
    fam = FAMILIES[key]
    t0 = time.time()
    rec, path, sha = load_registered(fam)
    print(f"{fam.name}: registered Stage A record {path} (sha256 {sha[:16]}...); {len(fam.cells)} cells {list(fam.cells)}", flush=True)
    w = fam.world()
    try:
        result = restate(fam, w, rec)
    finally:
        del w
        gc.collect()
    result["registered_record"] = {"path": path, "sha256": sha}
    status = write_result(fam, result, stamp_of(fam), force_report)
    print_result(fam, result)
    pm = ED.peak_mb()
    print(f"{fam.name}: {os.path.join(fam.mod.OUT, fam.out_file)} {status} ({time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ")", flush=True)
    return result


# ------------------------------------------------------------------ selftest: synthetic worlds only
def brute_dd5(x):
    """plain python: the average depth of the 5 deepest non-overlapping drawdown episodes of the curve cumsum(x) from a flat account, and the worst (augur_engine.drawdowns' definition, written out again)"""
    cum, peak, eps, in_ep, trough = 0.0, 0.0, [], False, 0.0
    for v in x:
        cum += float(v)
        if cum >= peak - 1e-9:
            if in_ep:
                eps.append(peak - trough)
                in_ep = False
            peak = cum
        elif not in_ep:
            in_ep, trough = True, cum
        elif cum < trough:
            trough = cum
    if in_ep:
        eps.append(peak - trough)
    top = sorted(eps, reverse=True)[:5]
    return (sum(top) / len(top) if top else 0.0), (top[0] if top else 0.0), len(top)


def stage_record(fam, res):
    """a Stage A record in the shape the harness writes it (only the blocks check_registered reads), from a reading's result: for the toy worlds, where no harness wrote one"""
    return {"judged": True, "stageA": {"cells": {c: {"base": res["cells"][c]["base"]} for c in fam.cells}},
            "parity": {c: {"net": res["cells"][c]["base"]["net"], "n_pos": res["cells"][c]["base"]["n_pos"], "n_units": res["cells"][c]["base"]["n_units"]} for c in fam.cells}}


def refused(fn, *frag):
    """the call must refuse (SystemExit) with every fragment in the message"""
    try:
        fn()
    except SystemExit as e:
        msg = str(e)
        assert all(f in msg for f in frag), (msg, frag)
        return msg
    raise AssertionError(f"expected a refusal containing {frag}")


def toy_worlds():
    """(family, world, context managers, a registered record) on the harnesses' hand-made worlds: EDRIFT's toy market with its volume events, NEWISSUE's planted world with spin-off / stock-dividend ex-dates inside the first hold"""
    out = []
    B, S12 = M17.synth_book(seed=15)
    with ED.spec(n_side=2, min_scored=8, min_side=2):
        W = ED.toy_events()
        ED.attach_events(W)
        w = SimpleNamespace(W=W, B=B, S12=S12, ref=DV.mk_ref(B), rows=A13.book_rows(B, W), cal=None)
        out.append((FAMILIES["edrift"], w, (ED.spec(n_side=2, min_scored=8, min_side=2), ED.patched(ED, A2_WIN=(TS("2024-12-02"), TS("2025-05-30"))))))
    B3, S3 = M17.synth_book(seed=3, hi="2026-06-30")
    rb = DV.mk_ref(B3)
    with NI.spec(**NI.SMALL):
        wd, _r1, _f1, _x1, planted = NI.close_world()
        w = SimpleNamespace(W=wd.W, ctx=wd.ctx, B=B3, S12=S3, SN=NI.restrict_stretch(S3, B3.raw, B3.index, NI.WFN, NI.PRE_END), SRN=NI.restrict_stretch(rb.S, rb.raw, B3.index, NI.WFN, NI.PRE_END), ref=rb, rows=A13.book_rows(B3, wd.W), cal=None, planted=planted)
        out.append((FAMILIES["newissue"], w, (NI.spec(**NI.SMALL),)))
    return out


def brute_positions(fam, w, cell, pm):
    """plain python (the harnesses' own recounts, none of the run's per-position table): {(rebalance, column, side): net P&L in $} of a cell's WF positions under reading `pm`, and {rebalance: (r, f, x)} - EDRIFT: the recount's picks (brute_ed) on brute_pos_ed's paths at the slot;
    NEWISSUE: every NEW short with its matched long / its share of the ES hedge, as brute_cell_series books it"""
    W, out, info = w.W, {}, {}
    if fam.key == "edrift":
        slot = M17.SPEC["slot"]
        for ri, b in enumerate(ED.brute_ed(W, fam.lo, fam.hi, pm)):
            info[ri] = (b["r"], b["f"], b["x"])
            bc = b["cell"][cell]
            for sd, js in ((1, bc["long"]), (-1, bc["short"])):
                for j in js:
                    out[(ri, int(j), sd)] = slot * float(np.sum(ED.brute_pos_ed(W, b, int(j), sd)))
        return out, info
    slot, L = NI.SPEC["slot"], NI.ni_build(W, w.ctx, fam.lo, fam.hi, pm)
    for ri, q in enumerate(L.recs):
        info[ri] = (q.r, q.f, q.x)
        if not NI.traded(q, cell):
            continue
        es = NI.brute_es_leg(W, q.f, q.x, NI.ES_BPS)
        mt = NI.brute_match([NI.brute_dv(W, q.r, int(c_)) for c_ in q.new], [NI.brute_dv(W, q.r, int(c_)) for c_ in q.seas], q.new.tolist(), q.seas.tolist()) if cell == "M" else None
        for i, col in enumerate(q.new):
            if mt is not None and mt[i] < 0:
                continue
            s_ = NI.brute_pos_c(W, q.f, q.x, int(col), -1, NI.COST_BPS, NI.BORROW, pm)
            o_ = q.beta * slot * es if cell == "E" else NI.brute_pos_c(W, q.f, q.x, int(q.seas[mt[i]]), +1, NI.COST_BPS, NI.BORROW, pm)
            out[(ri, int(col), -1)] = float(np.sum(s_ + o_))
    return out, info


def brute_reasons(W, r, f, x, j):
    """plain python: the labels reasons_of gives, by scanning the sessions one by one (the hygiene arrays W.fl in HYG's order on rows r+1 .. x, [D2]'s W.SPN and the calendar's W.CSPL on rows f+1 .. x)"""
    out = [h for q, h in enumerate(M17.HYG) if any(bool(W.fl[q][t, j]) for t in range(r + 1, x + 1))]
    if any(bool(W.SPN[t, j]) for t in range(f + 1, x + 1)):
        out.append("spin")
    if getattr(W, "CSPL", None) is not None and any(bool(W.CSPL[t, j]) for t in range(f + 1, x + 1)):
        out.append("calendar split")
    return out


def brute_move(W, f, x, j, cl):
    """plain python: the largest one-day move of a name inside the hold - the entry open, then each close of rows f .. x-1 (a missing bar carries the last), then the exit open (no open: the last mark); closed at the close of row cl >= 0: the closes of rows f .. cl and nothing after -> (move, session)"""
    last = float(W.Ao[f, j])
    lev = [last]
    for t in range(f, (cl if cl >= 0 else x - 1) + 1):
        c = float(W.Ac[t, j])
        last = c if math.isfinite(c) else last
        lev.append(last)
    if cl < 0:
        o = float(W.Ao[x, j])
        lev.append(o if math.isfinite(o) else last)
    mv = [(lev[q + 1] / lev[q] - 1.0, f + q) for q in range(len(lev) - 1)]
    return max(mv, key=lambda a: abs(a[0]))


def check_biggest_move():
    """biggest_move on hand-made unit paths (H = 5, f = 2): a position held to the exit (the exit open's overnight move counts), a flat one (zero, the fill session), one closed at the close of row f+2 (its levels end at that close; the zeros after it are not read), one with an undefined path"""
    W = SimpleNamespace(days=pd.bdate_range("2024-01-01", periods=12))
    nan = float("nan")
    U = SimpleNamespace(mk=np.array([[1.0, 1.1, 1.2, 1.1, 1.0], [1.0, 1.0, 1.0, 1.0, 1.0], [1.0, 1.2, 1.0, 0.0, 0.0], [nan, nan, nan, nan, nan]]), ve=np.array([2.0, 1.0, 0.7, nan]), xc=np.array([4, 4, 2, 4]))
    rec = SimpleNamespace(f=2, x=6, U=U)
    got = [biggest_move(W, rec, i) for i in range(4)]
    assert abs(got[0][0] - 1.0) < 1e-12 and got[0][1] == W.days[6], got[0]
    assert got[1] == (0.0, W.days[2]), got[1]
    assert abs(got[2][0] - (-0.3)) < 1e-12 and got[2][1] == W.days[4], got[2]
    assert math.isnan(got[3][0]) and got[3][1] is None, got[3]
    rec.U = SimpleNamespace(mk=U.mk, ve=U.ve)                                                       # no exit column (the registered reading's units): held to the exit
    assert biggest_move(W, rec, 2)[0] != got[2][0]


def check_reasons_window(W):
    """reasons_of reads the hygiene rows r+1 .. x (a flag ON the rank row is the pre-window's, it removes the name before any pool) and [D2]'s rows f+1 .. x (an ex-date ON the fill session is bought ex): found on the toy world's own events"""
    n = 0
    for q, h in enumerate(M17.HYG):
        for t, j in zip(*np.nonzero(W.fl[q][:W.T - 7])):
            t, j = int(t), int(j)
            if t >= 2 and not any(bool(W.fl[q2][t + 1:t + 6, j].any()) or bool(W.SPN[t + 1:t + 6, j].any()) for q2 in range(4)) and not W.SPN[t - 1:t + 1, j].any():
                assert reasons_of(W, SimpleNamespace(r=t, f=t + 1, x=t + 5), j) == [], (h, t, j, "a flag on the rank row is not in the hold")
                assert reasons_of(W, SimpleNamespace(r=t - 1, f=t, x=t + 4), j) == [h] or h in reasons_of(W, SimpleNamespace(r=t - 1, f=t, x=t + 4), j), (h, t, j)
                n += 1
                break
        else:
            continue
    for t, j in zip(*np.nonzero(W.SPN[:W.T - 7])):
        t, j = int(t), int(j)
        if t >= 3 and not W.SPN[t + 1:t + 6, j].any():
            assert "spin" in reasons_of(W, SimpleNamespace(r=t - 2, f=t - 1, x=t + 3), j) and "spin" not in reasons_of(W, SimpleNamespace(r=t - 1, f=t, x=t + 4), j), (t, j, "an ex-date on the fill session is bought ex")
            n += 1
            break
    assert n >= 2, "the toy world holds hygiene flags and a spin-off to read"
    return n


def check_movers(fam, w, result, obj_r, obj_c):
    """the movers against a plain-python recount of both readings' positions (brute_positions): the adds / changes / displaced counts and sums, the top lists in order, each listed row (P&Ls, effect, reason, close, largest move and its date), the net-change line and the top 3's share; the
    toy worlds must hold adds (a closed or flagged name S1 keeps) - NEWISSUE's planted names by their symbols; the calendar's split marker; a shorter list. -> number of rows checked"""
    W, n_rows = w.W, 0
    tol = lambda a, b: abs(a - b) < 1e-6
    for c in fam.cells:
        m = result["s1_movers"][c]
        P0, info = brute_positions(fam, w, c, REG)
        P1, info1 = brute_positions(fam, w, c, S1)
        assert info == info1, "one rebalance schedule"
        adds = {k: v for k, v in P1.items() if k not in P0}
        chg = {k: (P0[k], v) for k, v in P1.items() if k in P0 and abs(v - P0[k]) > 1e-6}
        gone = {k: v for k, v in P0.items() if k not in P1}
        s_add, s_chg, s_gone = sum(adds.values()), sum(b - a for a, b in chg.values()), sum(gone.values())
        d_net = result["cells"][c]["s1"]["net"] - result["cells"][c]["registered"]["net"]
        assert m["positions"] == {"registered": len(P0), "s1": len(P1)} and m["adds"]["n"] == len(adds) and tol(m["adds"]["pnl"], s_add), (fam.key, c, m["adds"]["n"], len(adds))
        assert m["changes"]["n"] == len(chg) and tol(m["changes"]["delta"], s_chg) and m["displaced"]["n"] == len(gone) and tol(m["displaced"]["pnl"], s_gone), (fam.key, c)
        assert tol(m["net_change"], d_net) and tol(m["explained_by_positions"], s_add + s_chg - s_gone) and tol(m["residual"], d_net - (s_add + s_chg - s_gone)), (fam.key, c)
        assert abs(m["residual"]) < 0.01, (fam.key, c, "the positions' table and the daily series' net read the same days", m["residual"])
        look = {}
        for ri, col, sd in set(P0) | set(P1):
            r, f, x = info[ri]
            look[(str(W.syms[col]), f"{W.days[r]:%Y-%m-%d}", "long" if sd > 0 else "short")] = (ri, col, sd)
        order = lambda d, f_: sorted(d, key=lambda k: (-abs(f_(d[k])), k))
        eff = {**adds, **{k: b - a for k, (a, b) in chg.items()}}
        for g, exp, kind in ((m["adds"]["top"], order(adds, lambda v: v)[:TOP_N], "add"), (m["changes"]["top"], order(chg, lambda v: v[1] - v[0])[:TOP_N], "change")):
            assert len(g) == len(exp) and all(r_["kind"] == kind for r_ in g), (fam.key, c, kind, len(g), len(exp))
            assert all(abs(abs(r_["effect"]) - abs(eff[k_])) < 1e-6 for r_, k_ in zip(g, exp)), (fam.key, c, kind, "the list is in order of |the P&L moved| (positions whose effects tie to the float are interchangeable)")
            for row in g:
                k = look[(row["symbol"], row["rank_date"], row["side"])]
                assert k in (adds if kind == "add" else chg), (fam.key, c, kind, row["symbol"], row["rank_date"])
                ri, col, sd = k
                r, f, x = info[ri]
                ex = next((t for t in range(f + 1, x + 1) if bool(W.SPN[t, col])), -1)
                rs = brute_reasons(W, r, f, x, col)
                mv, ms = brute_move(W, f, x, col, ex - 1 if ex >= 0 else -1)
                p0 = P0.get(k)
                assert tol(row["pnl"], P1[k]) and (p0 is None and row["pnl_registered"] is None or tol(row["pnl_registered"], p0)) and tol(row["effect"], P1[k] - (p0 or 0.0)), (fam.key, c, k)
                assert row["reason"] == (" + ".join(rs) if rs else ("none - the extra names moved the ranking's cut" if kind == "add" else "-")), (fam.key, c, k, row["reason"], rs)
                assert row["closed"] is (ex >= 0) and row["closed_on"] == (f"{W.days[ex - 1]:%Y-%m-%d}" if ex >= 0 else None) and abs(row["max_move"] - mv) < 1e-9 and row["max_move_date"] == f"{W.days[ms]:%Y-%m-%d}", (fam.key, c, k, row["max_move"], mv)
                assert (row["fill"], row["exit"]) == (f"{W.days[f]:%Y-%m-%d}", f"{W.days[x]:%Y-%m-%d}") and row["side"] == ("long" if sd > 0 else "short")
                n_rows += 1
        t3 = order(eff, lambda v: v)[:3]
        e3 = sum(eff[k] for k in t3)
        assert all(abs(abs(r_["effect"]) - abs(eff[k_])) < 1e-6 and look[(r_["symbol"], r_["rank_date"], r_["side"])] in eff for r_, k_ in zip(m["top3"]["rows"], t3)) and len(m["top3"]["rows"]) == len(t3) and tol(m["top3"]["effect"], e3), (fam.key, c)
        assert (math.isnan(m["top3"]["share"]) if abs(d_net) <= 0.005 else abs(m["top3"]["share"] - e3 / d_net) < 1e-9) and m["top3"]["labels"] == [f"{r_['symbol']} {r_['rank_date']} {r_['side']}" for r_ in m["top3"]["rows"]]
        assert m["line"].startswith(f"{c}: net change {usd(d_net)} = {len(adds):,} positions added") and "explain" in m["line"] and ("n/a" in m["line"] or f"{m['top3']['share']:.0%}" in m["line"]), m["line"]
        # a shorter list keeps the totals and the top 3
        m1 = movers(fam, w, obj_r, obj_c, c, d_net, top=1)
        assert len(m1["adds"]["top"]) == min(1, len(adds)) and len(m1["changes"]["top"]) == min(1, len(chg)) and m1["adds"]["n"] == m["adds"]["n"] and m1["top3"]["labels"] == m["top3"]["labels"] and tol(m1["top3"]["effect"], m["top3"]["effect"])
    allm = result["s1_movers"]
    assert sum(allm[c]["adds"]["n"] for c in fam.cells) >= 1, f"{fam.key}: the toy world holds positions S1 adds"
    closed_adds = [r_ for c in fam.cells for r_ in allm[c]["adds"]["top"] if r_["closed"]]
    assert closed_adds and all("spin" in r_["reason"] for r_ in closed_adds), f"{fam.key}: an added position closed before an ex-date is listed with 'spin' as its reason"
    if fam.key == "newissue":                                                                       # the planted names: ka a spin-off in the hold (closed), kb a stock dividend on the exit session (closed), kc a gap flag in the hold (kept to the exit)
        pl, adds_e = w.planted, {r_["symbol"]: r_ for r_ in allm["E"]["adds"]["top"]}
        assert {pl["ka"], pl["kb"], pl["kc"]} <= set(adds_e), (sorted(adds_e), pl)
        ka, kb, kc = adds_e[pl["ka"]], adds_e[pl["kb"]], adds_e[pl["kc"]]
        assert ka["reason"] == "spin" and ka["closed"] and kb["reason"] == "spin" and kb["closed"] and kc["reason"] == "gap" and not kc["closed"], (ka["reason"], kb["reason"], kc["reason"])
        assert allm["E"]["changes"]["n"] >= 1 and any("hedge ratio" in r_["why"] for r_ in allm["E"]["changes"]["top"]), "E: the basket's beta moves with the NEW set: every other short's hedge share changes"
        assert any(r_.get("mate") for r_ in allm["M"]["adds"]["top"]) and any(r_["closed"] and r_.get("mate_closed_on") for r_ in allm["M"]["adds"]["top"] + allm["M"]["changes"]["top"]), "M: the matched long of a closed short closes too"
    # the calendar's split marker: a split on the grid inside the first listed add's hold adds 'calendar split' to its reason and moves nothing else
    c0 = next(c for c in fam.cells if allm[c]["adds"]["top"])
    row = allm[c0]["adds"]["top"][0]
    f0 = int(W.days.get_loc(TS(row["fill"])))
    M17.attach_calendar_splits(W, SimpleNamespace(split=pd.DataFrame({"symbol": [row["symbol"]], "ex": [W.days[f0 + 1]], "type": ["forward_split"]})))
    d0 = result["cells"][c0]["s1"]["net"] - result["cells"][c0]["registered"]["net"]
    mc = movers(fam, w, obj_r, obj_c, c0, d0)
    r2 = next(r_ for r_ in mc["adds"]["top"] if (r_["symbol"], r_["rank_date"], r_["side"]) == (row["symbol"], row["rank_date"], row["side"]))
    assert r2["reason"] == (row["reason"] + " + calendar split" if not row["reason"].startswith("none") else "calendar split") and r2["pnl"] == row["pnl"] and mc["adds"]["n"] == allm[c0]["adds"]["n"] and mc["adds"]["pnl"] == allm[c0]["adds"]["pnl"]
    M17.attach_calendar_splits(W, None)                                                           # (the toy's state again: an empty matrix; selftest_toy removes it)
    return n_rows


def selftest_toy():
    """the restatement logic on the hand-made worlds: the registered reading reproduced and refused when it is not (a net $2 off, a position off, no record), S1's numbers = the harness's own evaluate() on 'close', DD5 = a plain-python DD5 on the same curve, the calendar's splits
    counted and 'remove' untouched by them, the verdict logic (DEAD / REVIEW), the line, the file (written, an identical re-run a no-op, a different one refused), the stamp"""
    n, lines, n_mov = 0, [], 0
    check_biggest_move()
    for fam, w, ctxs in toy_worlds():
        with contextlib.ExitStack() as es:
            for c in ctxs:
                es.enter_context(c)
            res_r, obj_r = fam.evaluate(w, REG)
            rec = stage_record(fam, res_r)
            with tempfile.TemporaryDirectory() as td, ED.patched(fam.mod, OUT=os.path.join(td, "out")):
                # the result of the whole logic
                result = restate(fam, w, rec)
                res_c, obj_c = fam.evaluate(w, S1)
                for c in fam.cells:
                    a, b = result["cells"][c]["registered"], result["cells"][c]["s1"]
                    sr, sc = res_r["cells"][c]["base"], res_c["cells"][c]["base"]
                    assert a["net"] == sr["net"] and b["net"] == sc["net"] and a["roc"] == sr["roc"] and b["roc"] == sc["roc"] and b["max_dd"] == sc["max_dd"] and abs(b["usd_year"] - sc["net"] / sc["years"]) < 1e-9, (fam.key, c)
                    for rd, obj in ((a, obj_r), (b, obj_c)):                                           # DD5 = the plain-python DD5 of the same curve on the same stretch
                        k = w.B.mask(fam.lo, fam.hi)
                        want = brute_dd5(np.asarray(obj.series[c][0], float)[k])
                        assert abs(rd["dd5"] - want[0]) < 0.01 and abs(rd["max_dd"] - want[1]) < 0.01 and rd["dd5_n"] == want[2] and rd["one_episode"] is bool(want[2] and want[1] > 1.3 * want[0]), (fam.key, c, rd["dd5"], want)
                    n += 1
                assert any(result["cells"][c]["registered"]["net"] != result["cells"][c]["s1"]["net"] for c in fam.cells), f"{fam.key}: the in-hold names move the toy world's P&L"
                dead = all(not (result["cells"][c]["s1"]["roc"] >= fam.mod.RULES["roc"] and result["cells"][c]["s1"]["net"] > 0) for c in fam.cells)
                assert result["reproduced"][fam.cells[0]]["difference"] == 0.0 and result["still_dead"] is dead and (("verdict unchanged DEAD" in result["line"]) is dead) and (("REVIEW" in result["line"]) is not dead), result["line"]
                assert result["line"].startswith(f"{fam.name} r1 restated under S1 (report; ") and all(f"{c} ROC @ $30k" in result["line"] for c in fam.cells) and " a year " in result["line"] and "calendar splits kept" in result["line"] and "traded positions closed" in result["line"], result["line"]
                lines.append(result["line"])
                n_mov += check_movers(fam, w, result, obj_r, obj_c)
                check_reasons_window(w.W)
                # 'remove' is untouched by putting the calendar's splits on the grid (re-evaluate after restate attached them)
                res_r2, _o = fam.evaluate(w, REG)
                assert all(res_r2["cells"][c]["base"]["net"] == res_r["cells"][c]["base"]["net"] and res_r2["cells"][c]["base"]["n_pos"] == res_r["cells"][c]["base"]["n_pos"] for c in fam.cells), "'remove' ignores the calendar's splits"
                del w.W.CSPL, w.W.cscs
                # the counts: the picked positions closed are the recount's
                k = result["pool_counts"]["s1_kept_and_closed"]
                assert k["closed_spin"] == sum(int((r.close >= 0).sum()) for r in obj_c.legs.recs) and all(result["traded_positions"][c]["closed"] <= result["traded_positions"][c]["positions"] for c in fam.cells)
                if fam.key == "newissue":
                    assert k["closed_spin"] == k["closed_spin_new"] + k["closed_spin_seasoned"] and result["traded_positions"]["M"]["closed_long"] >= 1 and result["traded_positions"]["E"]["closed_short"] >= 1 and result["traded_positions"]["E"]["closed_long"] == 0
                else:
                    assert k["closed_spin"] >= 3 and result["pool_counts"]["registered_removed_for_an_in_hold_event"] >= 3
                # the registered record is refused when it is not reproduced
                for what, mut in (("net $2 off", lambda r: r["stageA"]["cells"][fam.cells[0]]["base"].__setitem__("net", r["stageA"]["cells"][fam.cells[0]]["base"]["net"] + 2.0)),
                                  ("a position off", lambda r: r["stageA"]["cells"][fam.cells[1]]["base"].__setitem__("n_pos", r["stageA"]["cells"][fam.cells[1]]["base"]["n_pos"] + 1))):
                    bad = json.loads(json.dumps(rec, default=R11.js))
                    mut(bad)
                    refused(lambda: check_registered(fam, res_r, bad), "does not reproduce the registered Stage A record", fam.name)
                ok_rec = json.loads(json.dumps(rec, default=R11.js))
                ok_rec["stageA"]["cells"][fam.cells[0]]["base"]["net"] += 0.5
                ok_rec["parity"][fam.cells[0]]["net"] += 0.5
                check_registered(fam, res_r, ok_rec)                                                    # $0.50 is inside the $1 rule
                # the file
                st = stamp_of(fam)
                p = os.path.join(fam.mod.OUT, fam.out_file)
                assert write_result(fam, result, st) == "written" and os.path.exists(p) and write_result(fam, result, st) == "unchanged"
                other = dict(result, verdict="x")
                before = open(p, "rb").read()
                refused(lambda: write_result(fam, other, st), "already on file", "DIFFERS")
                assert open(p, "rb").read() == before, "a refused write leaves the file as it was"
                loaded = json.load(open(p))
                assert loaded["line"] == result["line"] and loaded["stamp"]["r25_sha256"] == R11.sha_lf(os.path.abspath(__file__)) and set(loaded["cells"]) == set(fam.cells)
                assert set(loaded["s1_movers"]) == set(fam.cells) and all(loaded["s1_movers"][c]["line"] == result["s1_movers"][c]["line"] and len(loaded["s1_movers"][c]["adds"]["top"]) == len(result["s1_movers"][c]["adds"]["top"]) for c in fam.cells)
                # --force-report: a file written before the movers existed (the same numbers, no s1_movers, another stamp)
                old_doc = {k: v for k, v in loaded.items() if k != "s1_movers"}
                old_doc["stamp"] = {"r25_sha256": "0" * 64}
                open(p, "w").write(json.dumps(old_doc, indent=1))
                old_raw = open(p, "rb").read()
                refused(lambda: write_result(fam, result, st), "already on file", "DIFFERS", "s1_movers", "--force-report")
                assert open(p, "rb").read() == old_raw, "a refusal leaves the file as it was"
                bad_doc = json.loads(json.dumps(old_doc))
                bad_doc["cells"][fam.cells[0]]["s1"]["net"] += 1.0
                open(p, "w").write(json.dumps(bad_doc, indent=1))
                bad_raw = open(p, "rb").read()
                refused(lambda: write_result(fam, result, st, force_report=True), "DIFFERS", "cells", "every number on it is identical")
                assert open(p, "rb").read() == bad_raw, "--force-report writes nothing when a number differs"
                noisy = json.loads(json.dumps(old_doc))                                           # a number off by 1e-12 (relative) is the same number
                noisy["cells"][fam.cells[0]]["s1"]["net"] += 1e-12 * max(1.0, abs(noisy["cells"][fam.cells[0]]["s1"]["net"]))
                open(p, "w").write(json.dumps(noisy, indent=1))
                old_raw = open(p, "rb").read()
                assert write_result(fam, result, st, force_report=True) == "rewritten"
                new_doc = json.load(open(p))
                assert set(new_doc) == set(noisy) | {"s1_movers", "report_rewritten"} and all(same_numbers(new_doc[k], noisy[k], 0.0) for k in noisy if k != "stamp") and new_doc["stamp"] == json.loads(json.dumps(st, default=R11.js)), "everything it held is kept as it was"
                assert new_doc["report_rewritten"]["added_keys"] == ["s1_movers"] and new_doc["report_rewritten"]["previous_stamp"] == noisy["stamp"] and new_doc["report_rewritten"]["previous_file_sha256"] == hashlib.sha256(old_raw).hexdigest()
                assert same_numbers(new_doc["s1_movers"], json.loads(json.dumps(result["s1_movers"], default=R11.js)), 0.0)
                assert write_result(fam, result, st, force_report=True) == "unchanged" and write_result(fam, result, st) == "unchanged", "nothing left to add: a re-run (with or without the flag) is a no-op"
                again = open(p, "rb").read()
                st2 = {**st, "r25_sha256": "1" * 64}
                assert write_result(fam, result, st2) == "unchanged" and open(p, "rb").read() == again, "a different stamp alone (the code's hash) is not a different result"
                assert not os.path.exists(p + ".tmp")
                refused(lambda: write_result(fam, dict(result, verdict="x"), st, force_report=True), "DIFFERS", "verdict")
                open(p, "w").write("not json")
                refused(lambda: write_result(fam, result, st, force_report=True), "not a readable restatement")
                open(p, "wb").write(again)
                # the registered record on file: missing / not judged refuses
                refused(lambda: load_registered(fam), "is not on file")
                os.makedirs(fam.mod.OUT, exist_ok=True)
                json.dump({"judged": False}, open(os.path.join(fam.mod.OUT, fam.stage_file), "w"))
                refused(lambda: load_registered(fam), "is not a judged Stage A record")
                json.dump(json.loads(json.dumps(rec, default=R11.js)), open(os.path.join(fam.mod.OUT, fam.stage_file), "w"))
                rec2, p2, sha2 = load_registered(fam)
                assert rec2["parity"][fam.cells[0]]["net"] == rec["parity"][fam.cells[0]]["net"] and len(sha2) == 64
                # the verdict logic: a cell that clears the bar is REVIEW, never DEAD
                hi = json.loads(json.dumps(result["cells"], default=R11.js))
                hi[fam.cells[0]]["s1"]["roc"], hi[fam.cells[0]]["s1"]["net"] = fam.mod.RULES["roc"] + 1.0, 1.0
                v, dead = verdict_of(fam, hi)
                assert dead is False and v.startswith("REVIEW") and fam.cells[0] in v and "NOT restated" in v
                hi[fam.cells[0]]["s1"]["net"] = -1.0
                assert verdict_of(fam, hi)[1] is True, "a negative net fails (b) whatever the ROC"
            n += 1
    assert usd(-1234.4) == "-$1,234" and usd(1234.5) == "$1,234" and usd(float("nan")) == "nan"
    return n, lines, n_mov


def selftest_markets(root_base):
    """each family's whole path on its harness's SYNTHETIC market (r5_siporb's fake Alpaca, a fake ES master, a fake #463 and RESMOM line, a fake calendar - the smoke's own environment, never real data): the harness's own stage_a writes the registered record, then run_family
    builds the world through the real loaders (stage_a's calls), reproduces that record and restates it; the result file is written inside the synthetic folder, a second run is a no-op"""
    out = {}
    for fam, env_fn in ((FAMILIES["edrift"], ED.smoke_env), (FAMILIES["newissue"], NI.smoke_env)):
        root = tempfile.mkdtemp(prefix=f"r25_{fam.key}_smoke_", dir=root_base)
        t0 = time.time()
        with env_fn(root, nrep=20, build=("plant",)) as env:
            env.switch("plant")
            with contextlib.redirect_stdout(io.StringIO()):
                fam.mod.stage_a()                                                                   # the registered record, on the synthetic world, by the harness itself
            rec_path = os.path.join(fam.mod.OUT, fam.stage_file)
            assert os.path.exists(rec_path) and os.path.abspath(rec_path).startswith(os.path.abspath(root)), "the synthetic record is inside the synthetic folder"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                result = run_family(fam.key)
                again = run_family(fam.key)
            txt = buf.getvalue()
            assert result["reproduced"] and all(abs(v["difference"]) <= NET_TOL for v in result["reproduced"].values()), result["reproduced"]
            assert "unchanged" in txt.splitlines()[-1] and "written" in txt and result["line"] in txt and again["line"] == result["line"], "a second run changes nothing"
            f_ = os.path.join(fam.mod.OUT, fam.out_file)
            assert os.path.exists(f_) and json.load(open(f_))["line"] == result["line"] and os.path.abspath(f_).startswith(os.path.abspath(root))
            assert all(f"{c}: net change" in txt for c in fam.cells) and "ADDS - in S1, not in 'remove'" in txt and "CHANGES - in both" in txt and "DISPLACED" in txt, "the movers are printed"
            doc = json.load(open(f_))                                                                 # the file as the first real run wrote it (no movers), rewritten by --force-report
            assert set(doc["s1_movers"]) == set(fam.cells)
            old = {k: v for k, v in doc.items() if k != "s1_movers"}
            old["stamp"] = {"r25_sha256": "0" * 64}
            json.dump(old, open(f_, "w"), indent=1)
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                forced = run_family(fam.key, force_report=True)
            new = json.load(open(f_))
            assert "rewritten" in buf2.getvalue().splitlines()[-1] and forced["line"] == result["line"] and new["report_rewritten"]["added_keys"] == ["s1_movers"], "--force-report added the movers"
            assert same_numbers(new["s1_movers"], json.loads(json.dumps(result["s1_movers"], default=R11.js)), 0.0) and all(same_numbers(new[k], old[k], 0.0) for k in old if k != "stamp"), "the same movers, and everything the file held kept"
            # the planted world is not dead: the verdict must say REVIEW, not DEAD
            assert result["still_dead"] is False and "REVIEW" in result["line"], result["line"]
            # a record that is not the registered reading is refused before anything is written
            doc = json.load(open(rec_path))
            doc["stageA"]["cells"][fam.cells[0]]["base"]["net"] += 3.0
            doc["parity"][fam.cells[0]]["net"] += 3.0
            json.dump(doc, open(rec_path, "w"))
            os.remove(f_)
            with contextlib.redirect_stdout(io.StringIO()):
                refused(lambda: run_family(fam.key), "does not reproduce the registered Stage A record")
            assert not os.path.exists(f_), "a refusal writes nothing"
        out[fam.key] = (result, time.time() - t0)
    return out


def selftest(quick=False):
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="r25_selftest_") as base:
        with contextlib.redirect_stdout(io.StringIO()):
            n, lines, n_mov = selftest_toy()
        print(f"  toy worlds ok ({time.time() - t0:.0f}s): {n} checks - the registered reading reproduced / refused, S1 = the harness's own evaluate, DD5 = a plain-python DD5, the counts, the verdict logic, the file (--force-report), the movers ({n_mov} listed rows recounted by plain python)")
        for ln in lines:
            print("    e.g. (synthetic numbers) " + ln[:300] + (" ..." if len(ln) > 300 else ""))
        if not quick:
            t1 = time.time()
            res = selftest_markets(base)
            for k, (r, dt) in res.items():
                print(f"  {k}: synthetic market ok ({dt:.0f}s): the world built through the real loaders, the harness's own Stage A record reproduced to ${max(abs(v['difference']) for v in r['reproduced'].values()):.2f}, restated, written, rerun a no-op, --force-report added the movers to a file without them, a changed record refused")
            print(f"  synthetic markets ok ({time.time() - t1:.0f}s)")
    pm = ED.peak_mb()
    print(f"SELFTEST OK ({time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; no real data was read, nothing outside the temp folders was written")


def main(argv):
    if "--selftest" in argv:
        return selftest(quick="quick" in argv)
    args = [a for a in argv if not a.startswith("--")]
    keys = {"edrift": ["edrift"], "newissue": ["newissue"], "both": ["edrift", "newissue"]}
    if len(args) != 1 or args[0] not in keys or any(a.startswith("--") and a != "--force-report" for a in argv):
        print(USAGE)
        return 2
    for k in keys[args[0]]:
        run_family(k, force_report="--force-report" in argv)
        gc.collect()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
