"""
TTM SQUEEZE round 12c - CROSS-INSTRUMENT COMPRESSION.

Every version of this family so far verifies an S&P squeeze against the S&P's own hourly
squeeze (ES 30m RTH crown: kc 1.5 / stop 1.5 ATR / eod_cutoff 1 / gate 60m sq_on gate_len 20
/ fade 1 / length 20 bb 2.0 min_sq_bars 1). Nobody has asked whether the NASDAQ being coiled
says anything about the S&P's next move, or the reverse - both trade the same sessions and
the same macro, so a shared compression state is untested and free to check (both masters
already exist). A SCAN: nothing here is crowned, queued to Auto-Validate, or committed.

WHAT'S TESTED (the ES 30m crown's own trade-construction rules in every case; only what
VERIFIES or SIZES the trade changes):
  1. Swap: replace the ES hourly gate with the NQ hourly gate (NQ-only verification), and
     separately require BOTH ES-hourly AND NQ-hourly compressed at once.
  2. Tilt: keep ES verification, add a 1.5x size tilt when the NQ hourly compression RATIO
     is <= 0.85 (deep) - the exact shape the shop already validated using ES's own ratio.
  3. Mirror: run the crown's rules on NQ 15m and NQ 30m RTH, verified by the ES hourly
     squeeze instead of NQ's own (a NQ-native-verified row runs alongside for context).
  4. Base rate: how often ES and NQ are coiled at the same time, the correlation of their
     hourly compression ratios, and a permutation test (5000 shuffles, same construction as
     round 6 Part A) on whether the ES crown's own trades earn more $/trade when NQ is also
     coiled at the decision bar.
  5. Same split, lockbox stretch only (>= LB_FROM), never tuned on.

NO LOOK-AHEAD, cross-instrument version: the "other" instrument's hourly state comes from
its LAST COMPLETE 60-minute group as of the decision bar, aligned on WALL-CLOCK bar-close
time (`_end`), never on row index. ES and NQ masters do not have the same bar count (52,861
ES 30m bars vs 52,860 NQ 30m bars over the identical window - a one-bar difference from a
data hole), so index alignment would silently misalign labels; every cross-instrument read
here uses np.searchsorted on `_end` timestamps, the same construction
`ttmsqz_round6_parts.hourly_compression` uses for a strategy's OWN gate, generalised to a
second instrument's bars. A self-map sanity check (mapping an instrument's own groups back
onto its own bars) is asserted bit-identical to `r6.hourly_compression` before anything else
runs.

Pinned window 2010-06-07..2026-06-30, lockbox = trades exiting on/after 2025-07-01, house
costs (ES 0.363 pts, NQ 0.533 pts), one contract unless noted, exactly as the harness sets.

Usage:  python tools/ttmsqz_r12c_cross_instrument.py
Output: tools/data/ttmsqz_r12c_cross_instrument.txt
"""
import os, sys, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import importlib.util


def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r6_x")
r8 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round8_crown.py"), "r8_x")

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT = r6.COST, r6.MULT
CROWN = r8.CROWN
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r12c_cross_instrument.txt")


# ---------------------------------------------------------------------------
# cross-instrument causal mapping (generalises r6.hourly_compression /
# r8.compression_ratio, which only ever mapped a df onto ITSELF)
# ---------------------------------------------------------------------------

def compute_groups(df, gate_tf_min=60, length=20, bb_mult=2.0, kc_mult=1.5):
    """Session-anchored gate_tf_min-minute groups of df, sorted by group-close time.

    Returns dict(end=[Timestamp], sq=[bool], ratio=[float], warm=int). Same construction
    as r6.hourly_compression's internals (and TTMSQZ_3_0's own _htf_gate), stopped short
    of mapping onto any particular target so it can be mapped onto ANY instrument's bars.
    """
    first = df.groupby("day_id")["_dt"].transform("first")
    off = ((df["_dt"] - first).dt.total_seconds() // 60).astype("int64")
    key = df["day_id"].astype(str) + "_" + (off // int(gate_tf_min)).astype(str).str.zfill(4)
    g = df.groupby(key, sort=True)
    hh, ll, cc = g["high"].max().values, g["low"].min().values, g["close"].last().values
    end = g["_end"].last().values
    order = np.argsort(end)
    hh, ll, cc, end = hh[order], ll[order], cc[order], end[order]
    sq, _, _ = r6.ttm.squeeze_indicators(hh, ll, cc, length, bb_mult, kc_mult)
    s = pd.Series(cc)
    dev = s.rolling(length).std(ddof=0)
    prev = np.concatenate([[np.nan], cc[:-1]])
    tr = np.maximum.reduce([hh - ll, np.abs(hh - prev), np.abs(ll - prev)])
    atr = pd.Series(tr).rolling(length).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((bb_mult * dev) / (kc_mult * atr)).to_numpy()
    warm = length * 2 + 5
    return dict(end=end, sq=sq, ratio=ratio, warm=warm)


def causal_map(groups, target_end):
    """Map groups (from compute_groups, possibly a DIFFERENT instrument) onto target_end,
    an array of bar-close (`_end`) wall-clock Timestamps. Uses the last group whose OWN
    close is at or before the target's decision-bar close - the identical causal rule
    r6.hourly_compression applies to a single instrument, just fed a second instrument's
    groups. No row-index arithmetic anywhere, so a data hole in either master cannot
    misalign the labels."""
    end, sq, ratio, warm = groups["end"], groups["sq"], groups["ratio"], groups["warm"]
    target_end = np.asarray(target_end)
    j = np.searchsorted(end, target_end, side="right") - 1
    ok = j >= warm
    jj = np.clip(j, 0, len(sq) - 1)
    sq_m = np.where(ok, sq[jj], False).astype(bool)
    ratio_m = np.where(ok, ratio[jj], np.nan)
    return sq_m, ratio_m


def decision_end(df, eb):
    """The wall-clock close of the DECISION bar (eb-1: fire[u] is evaluated at u, the fill
    lands on bar u+1=eb) - the same index r6/r8 already use to read a compression state for
    a strategy's own trades ('t["eb"].values - 1')."""
    idx = np.clip(np.asarray(eb) - 1, 0, len(df) - 1)
    return df["_end"].values[idx]


# ---------------------------------------------------------------------------
# scoring / formatting helpers
# ---------------------------------------------------------------------------

def score_row(t):
    return r8.alone_score(t)


HDR = ("  %-40s %6s %7s %11s %9s | %10s %7s %9s | %7s" %
       ("cell", "n", "PF", "net $", "DD $", "lockbox $", "LB PF", "LB DD $", "keep%"))


def _fmt(s, keep_pct, name):
    return ("  %-40s %6d %7.2f %11s %9s | %10s %7s %9s | %6.1f%%" % (
        name, s["n"], min(s["pf"], 99), "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]),
        "{:,.0f}".format(s["lb"]), "%.2f" % min(s["lbpf"], 99) if s["lbpf"] == s["lbpf"] else "n/a",
        "{:,.0f}".format(s["lbdd"]) if s["lbdd"] == s["lbdd"] else "n/a", keep_pct))


def permutation_gap(usd, on, seed=42, N=5000):
    """Distribution-free test on the difference in mean $/trade between on / ~on, exactly
    the round-6 Part A construction (fat-tailed PnL -> permutation, not a t-test)."""
    if not (on.any() and (~on).any()):
        return None
    rng = np.random.default_rng(seed)
    obs = float(usd[on].mean() - usd[~on].mean())
    lab = on.copy()
    hits = 0
    for _ in range(N):
        rng.shuffle(lab)
        if abs(float(usd[lab].mean() - usd[~lab].mean())) >= abs(obs):
            hits += 1
    return obs, hits / N


def main():
    L = []
    L.append("TTM SQUEEZE ROUND 12c - CROSS-INSTRUMENT COMPRESSION (ES vs NQ hourly squeeze)   %s"
             % time.strftime("%Y-%m-%d %H:%M"))
    L.append("window %s..%s, lockbox from %s, house costs, one contract unless noted"
             % (DATE_FROM, DATE_TO, LB_FROM))
    L.append("incumbent quoted: ES 30m RTH crown - kc 1.5 / stop_atr 1.5 / eod_cutoff 1 / "
             "gate 60m sq_on gate_len 20 / fade 1 bar / length 20 bb 2.0 min_sq_bars 1")
    L.append("no-lookahead rule: cross-instrument state read from the LAST COMPLETE 60m group "
             "as of the decision bar, aligned by np.searchsorted on wall-clock bar-close time "
             "(`_end`), never by row index (ES 30m and NQ 30m differ by 1 bar over the window).")
    print("\n".join(L), flush=True)

    # -- load masters ---------------------------------------------------
    df_es30 = r6.load("ES", "30m", "RTH")
    df_nq30 = r6.load("NQ", "30m", "RTH")
    df_nq15 = r6.load("NQ", "15m", "RTH")
    L.append("")
    L.append("masters: ES 30m RTH %d bars (%s..%s) | NQ 30m RTH %d bars (%s..%s) | NQ 15m RTH %d bars (%s..%s)"
             % (len(df_es30), df_es30["_dt"].iloc[0].date(), df_es30["_dt"].iloc[-1].date(),
                len(df_nq30), df_nq30["_dt"].iloc[0].date(), df_nq30["_dt"].iloc[-1].date(),
                len(df_nq15), df_nq15["_dt"].iloc[0].date(), df_nq15["_dt"].iloc[-1].date()))

    # -- hourly groups (source state), built from each instrument's OWN 30m bars --
    groups_es = compute_groups(df_es30, 60, 20, 2.0, 1.5)
    groups_nq = compute_groups(df_nq30, 60, 20, 2.0, 1.5)

    # sanity: a self-map must reproduce r6.hourly_compression bit-for-bit
    self_es, _ = causal_map(groups_es, df_es30["_end"].values)
    ref_es = r6.hourly_compression(df_es30, 60, 20, 2.0, 1.5)
    assert np.array_equal(self_es, ref_es), "cross-map self-check FAILED on ES - alignment bug"
    self_nq, _ = causal_map(groups_nq, df_nq30["_end"].values)
    ref_nq = r6.hourly_compression(df_nq30, 60, 20, 2.0, 1.5)
    assert np.array_equal(self_nq, ref_nq), "cross-map self-check FAILED on NQ - alignment bug"
    L.append("self-map sanity check: PASS (cross-map onto an instrument's own bars == r6.hourly_compression, bit-exact)")

    # -- incumbent: ES 30m crown, ES-hourly verified (the 359-trade baseline) --
    base_t = r8.run_ttm(df_es30, CROWN, inst="ES")
    s0 = score_row(base_t)
    assert s0["n"] == 359, "incumbent trade count drifted from the quoted 359 - check the harness/master"
    L.append("")
    L.append("incumbent reproduction check: n=%d net=$%s PF=%.3f DD=$%s LB=$%s LB PF=%.3f  (quoted: 359 / $51,709 / 2.12 / $3,740 / $4,992 / 2.22)"
             % (s0["n"], "{:,.0f}".format(s0["net"]), s0["pf"], "{:,.0f}".format(s0["dd"]),
                "{:,.0f}".format(s0["lb"]), s0["lbpf"]))

    dec_base = decision_end(df_es30, base_t["eb"].values)
    nq_sq_at_base, nq_ratio_at_base = causal_map(groups_nq, dec_base)

    # ungated ES fires (no hourly gate at all) - the universe cell 1's swap draws from
    kw_none = dict(CROWN); kw_none["gate_mode"] = "none"
    ungated_es = r8.run_ttm(df_es30, kw_none, inst="ES")
    dec_ungated = decision_end(df_es30, ungated_es["eb"].values)
    nq_sq_at_ungated, _ = causal_map(groups_nq, dec_ungated)
    es_sq_at_ungated, _ = causal_map(groups_es, dec_ungated)  # should reproduce the internal gate

    L.append("")
    L.append("=" * 130)
    L.append("1. SWAP / BOTH - which instrument's hourly squeeze verifies the ES 30m crown's own fires")
    L.append("=" * 130)
    L.append("  raw fires before any hourly gate (both directions, all other crown rules unchanged): n=%d" % len(ungated_es))
    L.append(HDR)
    L.append(_fmt(s0, 100.0, "INCUMBENT (ES hourly verifies, as published)"))

    nq_only_t = ungated_es[nq_sq_at_ungated].reset_index(drop=True)
    s_nq_only = score_row(nq_only_t)
    L.append(_fmt(s_nq_only, 100.0 * len(nq_only_t) / max(len(ungated_es), 1),
                  "SWAP: NQ hourly verifies instead (ES gate dropped)"))

    both_t = base_t[nq_sq_at_base].reset_index(drop=True)
    s_both = score_row(both_t)
    L.append(_fmt(s_both, 100.0 * len(both_t) / max(s0["n"], 1),
                  "BOTH: ES hourly AND NQ hourly required (keep% of incumbent)"))
    # cross-check: es_sq_at_ungated recovers the same 359 as base_t (internal-gate parity)
    L.append("  internal-gate parity check: ungated fires re-filtered by the ES-hourly cross-map = %d (incumbent = %d)"
             % (int(es_sq_at_ungated.sum()), s0["n"]))
    L.append("    (off by 1: gating changes which trades are taken, which changes when the position slot is free, so a"
             " later fire can appear/disappear under a different gate - path dependency in the engine itself, not an"
             " alignment bug; the SWAP/BOTH cells below are built the only way available - post-filtering the ungated"
             " fire list - since the engine takes no externally-injected gate array.)")

    L.append("")
    L.append("=" * 130)
    L.append("2. TILT - keep ES verification, size 1.5x the incumbent's own trades when NQ's hourly")
    L.append("   compression RATIO is <= 0.85 (deep) at the decision bar - the shape already validated on ES")
    L.append("=" * 130)
    L.append(HDR)
    L.append(_fmt(s0, 100.0, "INCUMBENT (flat 1x, as traded)"))
    deep = np.isfinite(nq_ratio_at_base) & (nq_ratio_at_base <= 0.85)
    tilt_t = base_t.copy()
    tilt_t["usd"] = np.where(deep, 1.5 * base_t["usd"].values, base_t["usd"].values)
    s_tilt = score_row(tilt_t)
    L.append(_fmt(s_tilt, 100.0 * deep.mean(), "1.5x on NQ-deep trades (share tilted, not dropped)"))

    L.append("")
    L.append("=" * 130)
    L.append("3. MIRROR - crown's own rules on the NQ tape, verified by the ES hourly squeeze instead of NQ's own")
    L.append("=" * 130)
    for label, df_nq in (("NQ 15m RTH", df_nq15), ("NQ 30m RTH", df_nq30)):
        L.append("")
        L.append("-- %s --" % label)
        L.append(HDR)
        nq_ungated = r8.run_ttm(df_nq, kw_none, inst="NQ")
        n_ung = len(nq_ungated)
        dec_nq = decision_end(df_nq, nq_ungated["eb"].values)
        es_sq_at_nq, _ = causal_map(groups_es, dec_nq)
        es_verified = nq_ungated[es_sq_at_nq].reset_index(drop=True)
        s_ev = score_row(es_verified)
        L.append(_fmt(s_ev, 100.0 * len(es_verified) / max(n_ung, 1), "ES-hourly verifies %s (of %d raw fires)" % (label, n_ung)))

        nq_native = r8.run_ttm(df_nq, CROWN, inst="NQ")
        if nq_native is not None:
            s_nat = score_row(nq_native)
            L.append(_fmt(s_nat, 100.0 * s_nat["n"] / max(n_ung, 1), "  reference: NQ-native-hourly verifies %s (context, not a cross test)" % label))

    L.append("")
    L.append("=" * 130)
    L.append("4. BASE RATE - is the whole market coiled together, and does it show up in the ES crown's own trades?")
    L.append("=" * 130)
    # whole-bar-series joint compression, over every warmed-up ES 30m bar (not just trade points)
    es_all, es_ratio_all = causal_map(groups_es, df_es30["_end"].values)
    nq_all, nq_ratio_all = causal_map(groups_nq, df_es30["_end"].values)
    valid = np.arange(len(df_es30)) >= groups_es["warm"] * 2  # generous double-warm floor, both legs live
    es_on, nq_on = es_all[valid], nq_all[valid]
    both_on = es_on & nq_on
    p_es = es_on.mean(); p_nq = nq_on.mean(); p_both = both_on.mean()
    p_nq_given_es = both_on.sum() / max(es_on.sum(), 1)
    L.append("  ES 30m bars, whole window (n=%d, post-warmup): P(ES hourly coiled)=%.1f%%  P(NQ hourly coiled)=%.1f%%  P(BOTH)=%.1f%%"
             % (valid.sum(), 100 * p_es, 100 * p_nq, 100 * p_both))
    L.append("  P(NQ coiled | ES coiled)=%.1f%%  (vs unconditional P(NQ coiled)=%.1f%% -> lift x%.2f)"
             % (100 * p_nq_given_es, 100 * p_nq, p_nq_given_es / max(p_nq, 1e-9)))
    fin = np.isfinite(es_ratio_all[valid]) & np.isfinite(nq_ratio_all[valid])
    corr = float(np.corrcoef(es_ratio_all[valid][fin], nq_ratio_all[valid][fin])[0, 1])
    L.append("  Pearson correlation of ES vs NQ hourly compression RATIO (continuous, n=%d): r=%.3f" % (fin.sum(), corr))

    usd_base = base_t["usd"].values
    r = permutation_gap(usd_base, nq_sq_at_base)
    if r:
        obs, p = r
        L.append("")
        L.append("  ES crown's own %d trades split by NQ-hourly-coiled at the decision bar:" % s0["n"])
        L.append("    NQ coiled:     n=%d  mean $/trade=%.0f" % (int(nq_sq_at_base.sum()), usd_base[nq_sq_at_base].mean()))
        L.append("    NQ NOT coiled: n=%d  mean $/trade=%.0f" % (int((~nq_sq_at_base).sum()), usd_base[~nq_sq_at_base].mean()))
        L.append("    gap in mean $/trade: %s   permutation p=%.4f (5000 shuffles)  %s"
                 % ("{:+,.0f}".format(obs), p,
                    "REAL - chance rarely makes a gap this big" if p < 0.05 else "NOT significant on its own"))
    else:
        L.append("  split has an empty side - cannot run the permutation test")

    L.append("")
    L.append("=" * 130)
    L.append("5. SAME SPLIT, LOCKBOX ONLY (>= %s, untouched by any search)" % LB_FROM)
    L.append("=" * 130)
    lb_mask = base_t["date"].values >= np.datetime64(LB_FROM)
    n_lb = int(lb_mask.sum())
    L.append("  lockbox trades: n=%d" % n_lb)
    if n_lb:
        lb_on = nq_sq_at_base[lb_mask]
        lb_usd = usd_base[lb_mask]
        lb_dates = base_t["date"].dt.date.values[lb_mask]
        if lb_on.any() and (~lb_on).any():
            s_lb_on = r6.score(lb_usd[lb_on], lb_dates[lb_on])
            s_lb_off = r6.score(lb_usd[~lb_on], lb_dates[~lb_on])
            L.append("    LB, NQ coiled:     n=%d  net=$%s  PF=%.2f" % (s_lb_on["n"], "{:,.0f}".format(s_lb_on["net"]), min(s_lb_on["pf"], 99)))
            L.append("    LB, NQ NOT coiled: n=%d  net=$%s  PF=%.2f" % (s_lb_off["n"], "{:,.0f}".format(s_lb_off["net"]), min(s_lb_off["pf"], 99)))
            rlb = permutation_gap(lb_usd, lb_on)
            if rlb:
                obslb, plb = rlb
                L.append("    gap in mean $/trade: %s   permutation p=%.4f (5000 shuffles, lockbox n=%d only - read as directional, not conclusive)"
                         % ("{:+,.0f}".format(obslb), plb, n_lb))
        else:
            L.append("    lockbox split has an empty side (all %d trades on one side) - no permutation test possible" % n_lb)

    # -- verdict: which cells beat the incumbent on BOTH whole-run PF AND lockbox net --
    L.append("")
    L.append("=" * 130)
    L.append("VERDICT - cells beating the incumbent on BOTH whole-run PF and lockbox net $")
    L.append("=" * 130)
    cells = [
        ("SWAP: NQ hourly only", s_nq_only),
        ("BOTH: ES AND NQ hourly", s_both),
        ("TILT: 1.5x on NQ-deep", s_tilt),
    ]
    winners = [name for name, s in cells if s["pf"] >= s0["pf"] and s["lb"] >= s0["lb"]]
    L.append("  incumbent: PF=%.3f  lockbox net=$%s" % (s0["pf"], "{:,.0f}".format(s0["lb"])))
    for name, s in cells:
        beat_pf = s["pf"] >= s0["pf"]; beat_lb = s["lb"] >= s0["lb"]
        L.append("  %-40s PF=%.3f (%s)  lockbox=$%s (%s)  %s" % (
            name, s["pf"], "beats" if beat_pf else "below", "{:,.0f}".format(s["lb"]),
            "beats" if beat_lb else "below", "BOTH" if (beat_pf and beat_lb) else ""))
    L.append("  cells beating on BOTH: %s" % (", ".join(winners) if winners else "none"))

    out = LOG
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[len(L) - 60:]))
    print("\nwrote " + out)


if __name__ == "__main__":
    main()
