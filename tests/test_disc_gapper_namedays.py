"""tools/disc_gapper_namedays.py - the ONE name-day builder of the PMFAIL r1 / RUNNER2 r1 pull (PREREG_pmfail_r1 section 16).

SYNTHETIC daily frames only: no parquet, calendar or manifest under C:\\EdgeLog is read, nothing is written outside tmp_path.
Proved here:
  * PMFAIL's event filter: the prior-close band (1.00 / 20.00 inclusive), ADV$ over the 20 PRIOR sessions only (all
    present; t's own volume never counts; the 21st session never counts), the open ratio O / P >= 1.20;
  * split removal: S1 (|F / F' - 1| > 0.005), S2 through the name_change chain (each hop on or after the previous one,
    earliest first, any date; the FISV reuse shape), unit_split on new_symbol, stock_dividend; a cash dividend never
    removes; carry-over SSR in pmfail_event, not registered;
  * RUNNER2's day 2: the run, both bands, ADV$ over D0-19..D0 (both ends), 22 bars present, the half-day skip (counted as
    runs), S1 / S1c on D1 or D2, test M on D1 (its 20-session median window, k up to 50) and its calibration (0.90
    inclusive), carry SSR; the loosest reading = runner2_d2; the widened reading never reads D2's volume;
  * role order, one row per name-day, buckets from the prior close; pools exclude earlier roles; draws = the literal
    section-16 procedure (fresh generator per role, strata order, sorted pool, take-all without a draw, sorted(idx));
    seeds reproduce; quotes come from registered events only;
  * the cut at 2025-06-30; the csv (columns, LF, sort, no index) and the sha256sum file; never overwriting a different csv;
    --dry-run writes nothing; the input sha checks refuse.
"""
import hashlib
import json
import os
import re
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import disc_gapper_namedays as B  # noqa: E402

DAYS = pd.bdate_range("2016-05-02", "2017-09-29")          # WF years 2016-17 and 2017-18; holds the half day 2016-11-25
CA_COLS = ["type", "symbol", "old_symbol", "new_symbol", "ex_date", "process_date", "record_date", "payable_date", "rate",
           "new_rate", "old_rate", "cash", "special"]


class World:
    """flat daily bars (o = l = c = px, volume vol) per symbol; split factors fo / fc (split open = o / fo, split close = c / fc)"""
    def __init__(self, days=DAYS):
        self.days = pd.DatetimeIndex(days)
        self.T = len(self.days)
        self.s = {}

    def add(self, sym, px=10.0, vol=200_000.0, nosplit=False):
        T = self.T
        self.s[sym] = {"o": np.full(T, float(px)), "l": np.full(T, float(px)), "c": np.full(T, float(px)), "v": np.full(T, float(vol)),
                       "fo": np.ones(T), "fc": np.ones(T), "miss": np.zeros(T, bool), "nosplit": nosplit}
        return self

    def i(self, d, k=0):
        return self.days.get_loc(pd.Timestamp(d)) + k

    def set(self, sym, d, k=0, **kw):
        i = self.i(d, k)
        for f, v in kw.items():
            self.s[sym][f][i] = v
        return self

    def frames(self):
        raw, sp = [], []
        for sym, a in self.s.items():
            ok = ~a["miss"]
            d = self.days[ok]
            raw.append(pd.DataFrame({"symbol": sym, "date": d, "o": a["o"][ok], "l": a["l"][ok], "c": a["c"][ok], "v": a["v"][ok]}))
            if not a["nosplit"]:
                sp.append(pd.DataFrame({"symbol": sym, "date": d, "o": a["o"][ok] / a["fo"][ok], "c": a["c"][ok] / a["fc"][ok]}))
        return pd.concat(raw, ignore_index=True), pd.concat(sp, ignore_index=True)

    def build(self, ca=None):
        raw, sp = self.frames()
        return B.build(raw, sp, ca if ca is not None else cal([]))


def cal(rows):
    return pd.DataFrame([{**{c: "" for c in CA_COLS}, **r} for r in rows], columns=CA_COLS)


def keys(res, name):
    ti, si = np.nonzero(res.masks[name])
    return {(f"{res.days[t]:%Y-%m-%d}", res.syms[s]) for t, s in zip(ti, si)}


def nd(d, k=0):
    """the session k bdays after d, as a string"""
    return f"{DAYS[DAYS.get_loc(pd.Timestamp(d)) + k]:%Y-%m-%d}"


T0 = "2016-08-10"


# ------------------------------------------------------------------ PMFAIL event filter
@pytest.fixture(scope="module")
def pm():
    w = World()
    w.add("AAA").set("AAA", T0, o=12.0)                              # O / P = 1.20 exactly -> event
    w.add("AAB").set("AAB", T0, o=11.9)                              # 1.19 -> no
    w.add("LOWP", px=0.99, vol=2_000_000).set("LOWP", T0, o=1.5)     # P = 0.99 -> no
    w.add("ONE", px=1.0, vol=2_000_000).set("ONE", T0, o=1.3)        # P = 1.00 -> event, lt5
    w.add("TWENTY", px=20.0).set("TWENTY", T0, o=24.5)               # P = 20.00 -> event
    w.add("TWENTYB", px=20.01).set("TWENTYB", T0, o=25.0)            # P = 20.01 -> no
    w.add("FOURNN", px=4.99, vol=400_000).set("FOURNN", T0, o=6.0)   # lt5
    w.add("FIVE", px=5.0, vol=400_000).set("FIVE", T0, o=6.5)        # P = 5.00 -> 5to20
    w.add("ADVLO", vol=99_999).set("ADVLO", T0, v=50_000_000)      # 999,990 a day before t; t's own volume never counts
    w.set("ADVLO", T0, o=12.5)
    w.add("ADVEX", vol=100_000).set("ADVEX", T0, o=12.5)             # exactly 1,000,000 over the 20 prior sessions ...
    w.set("ADVEX", T0, k=-21, v=0.0)                                 # ... the 21st session back is not in the window
    w.add("ADVEXT", vol=100_000).set("ADVEXT", T0, o=12.5)         # the 20th session back IS in the window:
    w.set("ADVEXT", T0, k=-20, v=0.0)                               # 950,000 -> no
    w.add("BKT", px=5.0, vol=400_000).set("BKT", T0, o=6.5)          # P = c(t-1) = 5.00 -> 5to20, although c(t-2) = 4.00
    w.set("BKT", T0, k=-2, c=4.0).set("BKT", T0, k=-1, o=4.0)        # (t-1 opens flat over c(t-2): no gap there)
    w.add("HOLE").set("HOLE", T0, o=12.5).set("HOLE", T0, k=-5, miss=True)       # a missing bar inside the 20 -> no
    w.add("HOLEB").set("HOLEB", T0, o=12.5).set("HOLEB", T0, k=-21, miss=True)  # outside the 20 -> event
    w.add("S1A").set("S1A", T0, o=12.5, fo=1.006)                    # F / F' = 1.006 -> removed
    w.add("S1B").set("S1B", T0, o=12.5, fo=1.004)                    # 1.004 -> kept
    w.add("NOSPLIT", nosplit=True).set("NOSPLIT", T0, o=12.5)        # no split bars: S1 not computable, not removed
    for s in ("NEWC", "NEWD", "UNITE", "CHAINF", "DIVG", "SDIVH", "POSTCUT"):
        w.add(s).set(s, T0, o=12.5)
    w.add("SSRX").set("SSRX", T0, o=12.5).set("SSRX", T0, k=-1, l=9.0)    # l(t-1) = 0.9 x c(t-2): carry-over SSR
    w.add("SSRY").set("SSRY", T0, o=12.5).set("SSRY", T0, k=-1, l=9.01)   # just above: registered
    w.add("WHOLB").set("WHOLB", T0, o=20.0)                        # O / P = 2.0: S3p; volume unchanged -> not S3v
    w.add("WHOLV").set("WHOLV", T0, o=20.0)                      # 2.0 with volume halved from t on -> S3v too
    w.s["WHOLV"]["v"][w.i(T0):] = 100_000.0
    w.set("WHOLV", T0, k=-1, v=200_000.0)
    ca = cal([
        {"type": "reverse_split", "symbol": "OLDC", "ex_date": T0, "process_date": T0},
        {"type": "name_change", "old_symbol": "OLDC", "new_symbol": "NEWC", "process_date": "2017-01-05"},
        {"type": "reverse_split", "symbol": "OLDD", "ex_date": T0, "process_date": T0},
        {"type": "name_change", "old_symbol": "OLDD", "new_symbol": "NEWD", "process_date": "2016-07-15"},   # before the action: not followed
        {"type": "unit_split", "old_symbol": "UNITEU", "new_symbol": "UNITE", "ex_date": T0, "process_date": T0},
        {"type": "forward_split", "symbol": "OLD1", "ex_date": T0, "process_date": T0},
        {"type": "name_change", "old_symbol": "OLD1", "new_symbol": "ZZZ", "process_date": "2016-06-01"},     # decoy, earlier
        {"type": "name_change", "old_symbol": "OLD1", "new_symbol": "OLD2", "process_date": nd(T0, 5)},
        {"type": "name_change", "old_symbol": "OLD2", "new_symbol": "CHAINF", "process_date": nd(T0, 30)},
        {"type": "cash_dividend", "symbol": "DIVG", "ex_date": T0, "process_date": T0, "rate": "0.5"},
        {"type": "stock_dividend", "symbol": "SDIVH", "ex_date": T0, "process_date": T0, "rate": "1.05"},
        {"type": "reverse_split", "symbol": "OLDP", "ex_date": T0, "process_date": T0},
        {"type": "name_change", "old_symbol": "OLDP", "new_symbol": "POSTCUT", "process_date": "2026-01-15"},  # after the cut: still the identity
        {"type": "reverse_split", "symbol": "NOWHERE", "ex_date": T0, "process_date": T0},                     # not a cached name
        {"type": "forward_split", "symbol": "AAA", "ex_date": "2025-07-01", "process_date": "2025-07-01"},     # after the cut: dropped
    ])
    return w.build(ca)


def test_pmfail_event_filter(pm):
    ev = {s for d, s in keys(pm, "pm_event") if d == T0}
    assert {"AAA", "ONE", "TWENTY", "FOURNN", "FIVE", "ADVEX", "HOLEB", "S1B", "NOSPLIT", "NEWD", "DIVG", "SSRX", "SSRY", "BKT"} <= ev
    for s in ("AAB", "LOWP", "TWENTYB", "ADVLO", "HOLE", "ADVEXT"):
        assert s not in ev, s
    assert all(d == T0 for d, _ in keys(pm, "pm_event"))           # nothing else in this world gaps 20%


def test_split_removal(pm):
    ev = {s for d, s in keys(pm, "pm_event") if d == T0}
    for s in ("S1A", "NEWC", "UNITE", "CHAINF", "SDIVH", "POSTCUT"):
        assert s not in ev, s
    assert "NEWD" in ev and "DIVG" in ev and "S1B" in ev and "NOSPLIT" in ev
    by = pm.counts["calendar"]["split_types"]
    assert by["reverse_split"]["2016"]["matched"] == 2 and by["reverse_split"]["2016"]["unmatched_name"] == 2   # NEWC, POSTCUT; OLDD, NOWHERE
    assert by["reverse_split"]["2016"]["renamed"] == 2
    assert by["forward_split"]["2016"]["matched"] == 1 and by["forward_split"]["2025"]["dropped_at_cut"] == 1
    assert by["unit_split"]["2016"]["matched"] == 1 and by["stock_dividend"]["2016"]["matched"] == 1
    assert pm.counts["pmfail"]["s1_unknown_among_gap_survivors"] == 1


def test_shape_rules_guard(pm, r2, big):
    for res in (pm, r2, big):
        assert res.counts["inputs"]["symbols_dropped_by_shape_rules"] == []
    w = World()
    for s in ("GOOD", "ABCDW", "BRK.B", "003CVR016", "AB_DELISTED"):        # r5_siporb: suffix, dot, placeholder; X_DELISTED stays
        w.add(s).set(s, T0, o=12.5)
    res = w.build()
    assert res.counts["inputs"]["symbols_dropped_by_shape_rules"] == ["003CVR016", "ABCDW", "BRK.B"]
    assert {s for _, s in keys(res, "pm_event")} == {"GOOD", "AB_DELISTED"}


def test_map_symbol_chain_rules():
    d = pd.Timestamp
    nc = {"A": [(d("2016-01-01"), "X", 0), (d("2016-03-01"), "B", 1)], "B": [(d("2016-02-01"), "Y", 2), (d("2016-04-01"), "C", 3)],
          "C": [(d("2016-04-01"), "A", 4)]}
    # A->B (03-01; A->X is earlier than the action), B->C (04-01; B->Y is earlier than 03-01), C->A (04-01, >= 04-01), then none
    assert B.map_symbol("A", d("2016-02-15"), nc) == ("A", 3)
    nc["C"] = []
    assert B.map_symbol("A", d("2016-02-15"), nc) == ("C", 2)
    assert B.map_symbol("A", d("2016-03-02"), nc) == ("A", 0)          # every A row is before the action: not followed
    loop = {"A": [(d("2016-05-01"), "B", 0)], "B": [(d("2016-05-01"), "A", 1)]}
    assert B.map_symbol("A", d("2016-04-01"), loop) == ("A", 2)        # each row followed once: no endless loop
    # FISV's shape (ticker reuse): each hop must be dated on or after the PREVIOUS hop, not merely after the action. Action on
    # A 2018-03-20; A->B 2023-06-07; the old B's B->C 2021-10-04 predates that hop; B->A 2025-11-11 -> A (a fixed threshold gives C)
    fisv = {"A": [(d("2023-06-07"), "B", 0)], "B": [(d("2021-10-04"), "C", 1), (d("2025-11-11"), "A", 2)]}
    assert B.map_symbol("A", d("2018-03-20"), fisv) == ("A", 2)
    # earliest first: two eligible renames of one symbol -> the earlier one
    two = {"A": [(d("2016-03-01"), "B", 0), (d("2016-05-01"), "C", 1)]}
    assert B.map_symbol("A", d("2016-02-01"), two) == ("B", 1)
    # calendar_splits sorts each symbol's renames by date, whatever order the file lists them in
    days, syms = pd.DatetimeIndex(["2016-02-01"]), ["B", "C"]
    ca = cal([{"type": "name_change", "old_symbol": "A", "new_symbol": "C", "process_date": "2016-05-01"},
              {"type": "name_change", "old_symbol": "A", "new_symbol": "B", "process_date": "2016-03-01"},
              {"type": "forward_split", "symbol": "A", "ex_date": "2016-02-01", "process_date": "2016-02-01"}])
    got, _ = B.calendar_splits(ca, days, syms)
    assert got.tolist() == [[True, False]]


def test_carry_ssr_and_buckets(pm):
    reg = {s for d, s in keys(pm, "pm_reg") if d == T0}
    assert "SSRX" not in reg and "SSRY" in reg and ("2016-08-10", "SSRX") in keys(pm, "pm_event")
    r = pm.rows.set_index(["date", "symbol"])
    assert r.loc[(T0, "ONE"), "price_bucket"] == "lt5" and r.loc[(T0, "FOURNN"), "price_bucket"] == "lt5"
    assert r.loc[(T0, "FIVE"), "price_bucket"] == "5to20" and r.loc[(T0, "TWENTY"), "price_bucket"] == "5to20"
    assert r.loc[(T0, "BKT"), "price_bucket"] == "5to20"             # from c(t-1) = 5.00, never c(t-2) = 4.00
    assert r.loc[(T0, "SSRX"), "pmfail_event"] == 1 and r.loc[(T0, "SSRX"), "quotes_pmfail"] == 0
    assert (r["wf_year"] == "2016-17").loc[[(T0, "AAA")]].all()
    surv = pm.counts["pmfail"]["survivors_in_order"]
    assert list(surv) == ["bar_on_t", "p_band_1_20", "adv_1m_prior20", "gap_open_1.20", "s1_vendor_split", "s2_calendar_split", "carry_ssr"]
    tot = [v["total"]["all"] for v in surv.values()]
    assert tot == sorted(tot, reverse=True)
    assert surv["carry_ssr"]["total"]["all"] == len(keys(pm, "pm_reg")) and surv["s2_calendar_split"]["total"]["all"] == len(keys(pm, "pm_event"))


def test_s3_reports(pm):
    assert (T0, "WHOLB") in keys(pm, "s3p") and (T0, "WHOLV") in keys(pm, "s3p")
    assert (T0, "WHOLV") in keys(pm, "s3v") and (T0, "WHOLB") not in keys(pm, "s3v")
    assert (T0, "WHOLB") in keys(pm, "pm_reg")                     # a report, never a removal


# ------------------------------------------------------------------ RUNNER2 day 2
D0 = "2016-08-16"
D1, D2 = nd(D0, 1), nd(D0, 2)


def r2_world():
    w = World()
    w.add("RUNA").set("RUNA", D1, c=14.0).set("RUNA", D2, o=14.0, l=14.0, c=14.0)   # run 1.40 exactly; flat D2 open
    w.add("RUNB").set("RUNB", D1, c=13.9)                                           # 1.39 -> no
    w.add("RUNC", px=15.0).set("RUNC", D1, c=21.0)                                  # c(D1) > 20: loosest only
    w.add("RUND").set("RUND", D1, c=14.0, l=9.0)                                    # l(D1) = 0.9 c(D0): carry SSR -> loosest only
    w.add("RUNE").set("RUNE", D1, o=20.0, c=14.0, v=100_000.0)                      # g = 2.0, g x v / med = 1.0: test M -> loosest only
    w.add("RUNF", vol=99_999).set("RUNF", D1, c=14.0, v=50_000_000.0)               # ADV$ < 1M over D0-19..D0; D1's volume never counts
    w.add("RUNF2", vol=100_000).set("RUNF2", D1, c=14.0).set("RUNF2", D2, k=-22, v=0.0)   # exactly 1M; t-22 is outside
    w.add("RUNF3", vol=100_000).set("RUNF3", D1, c=14.0).set("RUNF3", D2, k=-21, v=0.0)   # D0-19 = t-21 is inside: 950k -> no
    w.add("RUNG").set("RUNG", D1, c=14.0).set("RUNG", D2, k=-21, miss=True)         # D0-19 missing -> no
    w.add("RUNG2").set("RUNG2", D1, c=14.0).set("RUNG2", D2, k=-22, miss=True)      # outside -> event
    w.add("RUNH").set("RUNH", "2016-11-24", c=14.0)                                 # D2 = 2016-11-25, a half day -> skipped
    w.add("RUNI").set("RUNI", D1, c=14.0, fo=1.01)                                  # S1 on D1
    w.add("RUNJ").set("RUNJ", D1, c=14.0).set("RUNJ", D2, fo=1.01)                  # S1 on D2
    w.add("RUNK").set("RUNK", D1, c=14.0)                                           # calendar split on D2
    w.add("RUNKD").set("RUNKD", D1, c=14.0)                                         # calendar split on D1 (through a rename)
    w.add("RUNKN").set("RUNKN", D1, c=14.0)                                         # calendar split on D0: not D1 / D2 -> kept
    w.add("RUNL", px=3.0, vol=1_000_000).set("RUNL", D1, c=4.5)                     # lt5 from c(D1)
    w.add("RUNM").set("RUNM", D1, c=14.0).set("RUNM", D2, o=17.0)                   # also a PMFAIL event day (17 / 14 >= 1.2)
    w.add("RUNP", px=4.0, vol=300_000).set("RUNP", D1, c=5.8)                       # c(D0) = 4.00 < 5 but c(D1) = 5.80: 5to20
    # runner2_nonevent pool edges; D2 opens at 11.6 (O / P 1.10-1.16: neither a PMFAIL gap nor a PMFAIL flat day)
    w.add("FLM").set("FLM", D1, o=20.0).set("FLM", D2, o=11.6)                      # flat run (1.00) but test M trips on D1 -> out
    w.add("FLN").set("FLN", D1, c=10.5).set("FLN", D2, o=11.6)                      # c(D1) / c(D0) = 1.05 exactly -> in
    return w, cal([{"type": "reverse_split", "symbol": "RUNK", "ex_date": D2, "process_date": D2},
                   {"type": "forward_split", "symbol": "OLDKD", "ex_date": D1, "process_date": D1},
                   {"type": "name_change", "old_symbol": "OLDKD", "new_symbol": "RUNKD", "process_date": "2018-03-01"},
                   {"type": "reverse_split", "symbol": "RUNKN", "ex_date": D0, "process_date": D0}])


@pytest.fixture(scope="module")
def r2():
    w, ca = r2_world()
    return w.build(ca)


def test_runner2_day2_definition(r2):
    reg = {s for d, s in keys(r2, "r_reg") if d == D2}
    loose = {s for d, s in keys(r2, "r_loose") if d == D2}
    assert reg == {"RUNA", "RUNF2", "RUNG2", "RUNL", "RUNM", "RUNKN", "RUNP"}
    assert loose == reg | {"RUNC", "RUND", "RUNE"}                                 # RUNF3 (D0-19's volume) in neither
    assert not any(s == "RUNH" for _, s in keys(r2, "r_loose"))
    hs = r2.counts["runner2"]["half_day_d2_skipped"]                              # the RUNS the half-day skip removes: RUNH only
    assert hs["registered_rule"]["total"]["all"] == 1 and hs["loosest_reading"]["total"]["all"] == 1
    assert hs["registered_rule"]["by_year"]["2016-17"]["5to20"] == 1
    assert hs["name_days_with_a_bar_on_a_half_day_d2"] > 1                       # every name with a bar there: a side figure only
    assert all(d == D2 for d, _ in keys(r2, "r_loose"))
    assert r2.m_keeps_volume is False and r2.counts["test_m_calibration"]["n"] == 0     # no calibration population: price-only
    surv = r2.counts["runner2"]["survivors_in_order"]
    assert list(surv)[-1] == "carry_ssr" and surv["carry_ssr"]["total"]["all"] == len(keys(r2, "r_reg"))
    rd = r2.counts["runner2"]["readings"]
    assert rd["loosest_runner2_d2"]["total"]["all"] == len(loose) and rd["registered"]["total"]["all"] == len(reg)
    assert rd["band_on_c_d0_only"]["total"]["all"] == len(reg) + 1 and rd["carry_ssr_kept"]["total"]["all"] == len(reg) + 1


def test_runner2_rows_one_per_name_day(r2):
    r = r2.rows.set_index(["date", "symbol"])
    assert not r.index.duplicated().any()
    assert r.loc[(D2, "RUNM"), "pmfail_event"] == 1 and r.loc[(D2, "RUNM"), "runner2_d2"] == 1
    assert r.loc[(D2, "RUNL"), "price_bucket"] == "lt5" and r.loc[(D2, "RUNA"), "price_bucket"] == "5to20"
    assert r.loc[(D2, "RUNP"), "price_bucket"] == "5to20"                         # from c(D1) = 5.80, never c(D0) = 4.00
    assert r.loc[(D2, "RUNC"), "price_bucket"] == "5to20" and r.loc[(D2, "RUNC"), "runner2_d2"] == 1
    assert r2.counts["runner2"]["links"]["runner2_d2_also_pmfail_event"] == 1
    # RUNA's D2 opens flat over c(D1): a nonevent candidate, but runner2_d2 is an earlier role
    assert (D2, "RUNA") not in {(f"{r2.days[t]:%Y-%m-%d}", r2.syms[s]) for (y, b), (tt, ss) in r2.pools["nonevent"].items() for t, s in zip(tt, ss)}


def _calib_world(n_caught, extra=None):
    """10 vendor-known 1:2 reverse splits (F / F' = 2, g = 2.0); volume halves from u on for the first n_caught; plus RUNV: a
    whole-ratio D1 open on 50x volume (g x v / med = 100), which only the price-only form of test M removes"""
    w, ca = r2_world()
    for j in range(10):
        s, u = f"RV{j}", nd("2016-09-01", 3 * j)
        w.add(s, px=30.0)
        iu = w.i(u)
        for f in ("o", "l", "c"):
            w.s[s][f][iu:] *= 2.0
        w.s[s]["fo"][iu:] = 2.0
        w.s[s]["fc"][iu:] = 2.0
        if j < n_caught:
            w.s[s]["v"][iu:] = 100_000.0
    w.add("RUNV").set("RUNV", D1, o=20.0, c=14.0, v=10_000_000.0)
    if extra:
        extra(w)
    return w.build(ca)


def test_test_m_calibration_decides_the_form():
    keep = _calib_world(10)
    m = keep.counts["test_m_calibration"]
    assert m["n"] == 10 and m["caught_by_volume_clause"] == 10 and keep.m_keeps_volume
    assert (D2, "RUNV") in keys(keep, "r_reg") and (D2, "RUNE") not in keys(keep, "r_reg")
    assert keep.counts["runner2"]["test_m_registered_form"].startswith("with_volume")
    drop = _calib_world(0)
    m = drop.counts["test_m_calibration"]
    assert m["n"] == 10 and m["caught_by_volume_clause"] == 0 and not drop.m_keeps_volume
    assert (D2, "RUNV") not in keys(drop, "r_reg") and (D2, "RUNV") in keys(drop, "r_loose")
    assert drop.counts["runner2"]["test_m_registered_form"].startswith("price_only")
    # both forms are counted whatever the calibration decides: RUNV is out under price only, in under the volume clause
    for res in (keep, drop):
        rd = res.counts["runner2"]["readings"]
        assert rd["test_m_with_volume"]["total"]["all"] == rd["whole_ratio_guard_without_volume"]["total"]["all"] + 1
    edge = _calib_world(9)                                                       # 9 of 10 = 0.90 exactly: the volume clause stays
    m = edge.counts["test_m_calibration"]
    assert m["n"] == 10 and m["caught_by_volume_clause"] == 9 and m["catch_rate"] == 0.9 and edge.m_keeps_volume


def test_widened_reading_never_reads_d2_volume():
    """S1 / S1c widen to D0-19 .. D2, test M only to D1: under the volume clause, M on D2 would read v(D2), the trade
    session's own full-day volume. RUNW is registered with o(D2) = 2.0 x c(D1); v(D2) must not move the reading."""
    def runw(vd2):
        return lambda w: w.add("RUNW").set("RUNW", D1, c=14.0).set("RUNW", D2, o=28.0, v=vd2)
    lo, hi = _calib_world(10, runw(100_000.0)), _calib_world(10, runw(2_000_000.0))
    assert lo.m_keeps_volume and hi.m_keeps_volume
    assert (D2, "RUNW") in keys(lo, "r_reg") and (D2, "RUNW") in keys(hi, "r_reg")
    assert (D2, "RUNW") in keys(lo, "mvol")                                      # M (volume form) does flag D2 itself ...
    key = "splits_widened_s1_s1c_d0m19_to_d2_m_d0m19_to_d1"
    a, b = (x.counts["runner2"]["readings"][key]["total"]["all"] for x in (lo, hi))
    assert a == b == lo.counts["runner2"]["registered"]["total"]["all"] - 1      # ... but only RUNKN (calendar on D0) leaves


def test_runner2_nonevent_pool_edges(r2):
    pool = {(f"{r2.days[t]:%Y-%m-%d}", r2.syms[s]) for (tt, ss) in r2.pools["runner2_nonevent"].values() for t, s in zip(tt, ss)}
    assert (D2, "FLN") in pool                                                   # c(D1) / c(D0) = 1.05: the top edge is inclusive
    assert (D2, "FLM") not in pool                                               # test M on D1 removes it from the pool too
    assert (D1, "FLM") in keys(r2, "M")


def test_test_m_window_and_whole_ratio_range():
    """test M's median = the 20 sessions BEFORE u (u-20 .. u-1). Volumes rise going back (v(u-k) = 100k + (k-1) x 10k), so that
    window's median is 195k, and n = 19, n = 21, u-21 .. u-2 and u-19 .. u each move it: MUP sits on g x v / med = 1.6 and
    MLO on 0.625 exactly, so any other window flips one of them. RS30: a 1:30 reverse split (k = 30 > split_like_gaps' 20)."""
    w = World()
    for s, vu in (("MUP", 156_000.0), ("MLO", 60_937.5), ("MUPX", 156_001.0)):
        w.add(s).set(s, T0, o=20.0, v=vu)
        for k in range(1, 22):
            w.set(s, T0, k=-k, v=100_000.0 + (k - 1) * 10_000.0)
    w.add("RS30").set("RS30", T0, o=300.0, v=200_000.0 / 30.0)
    w.add("FLAT")
    res = w.build()
    mv, mp = keys(res, "mvol"), keys(res, "mprice")
    assert (T0, "MUP") in mv and (T0, "MLO") in mv and (T0, "MUPX") not in mv and (T0, "MUPX") in mp
    assert (T0, "RS30") in mv and (T0, "RS30") in mp
    assert B.big_whole(np.array([30.0, 1 / 30.0, 1.3])).tolist() == [True, False, False]
    assert B.big_whole(np.array([30.0, 1 / 30.0, 1.3]), inverse=True).tolist() == [True, True, False]


# ------------------------------------------------------------------ roles, pools, draws
@pytest.fixture(scope="module")
def big():
    return _big_world().build()


def _big_world():
    """many pmfail and runner2 events in two WF years and both buckets, many flat name-days"""
    w = World()
    for j in range(13):                                              # 13 registered 5to20 PMFAIL events in 2016-17
        s = f"P{j:02d}"
        w.add(s).set(s, nd("2016-08-01", 2 * j), o=12.5)
    for j in range(4):                                               # 4 lt5 in 2016-17
        s = f"L{j:02d}"
        w.add(s, px=3.0, vol=1_000_000).set(s, nd("2016-09-01", 2 * j), o=3.75)
    for j in range(12):                                              # 12 5to20 in 2017-18
        s = f"Q{j:02d}"
        w.add(s).set(s, nd("2017-07-10", j), o=12.5)
    for j in range(12):                                              # 12 RUNNER2 5to20 events in 2016-17
        s = f"R{j:02d}"
        w.add(s).set(s, nd("2016-10-03", 3 * j), c=14.0)
    w.add("SSRZ").set("SSRZ", "2016-08-30", o=12.5).set("SSRZ", "2016-08-30", k=-1, l=9.0)   # carry SSR event
    w.add("FLATA").set("FLATA", "2016-12-01", o=9.5)               # O / P = 0.95: in the pool
    w.add("FLATB").set("FLATB", "2016-12-01", o=10.5)            # 1.05: out
    w.add("FLATS").set("FLATS", "2016-12-01", k=-1, l=9.0)       # flat open on a carry-SSR day: out
    for j in range(8):
        w.add(f"F{j:02d}")
    w.add("FL5", px=3.0, vol=1_000_000)
    return w


def _pool_keys(res, role):
    return {(WF_KEY(y, b)): sorted((f"{res.days[t]:%Y-%m-%d}", res.syms[s]) for t, s in zip(tt, ss))
            for (y, b), (tt, ss) in res.pools[role].items()}


def WF_KEY(y, b):
    return (B.WF_YEARS[y], B.BUCKETS[b])


def ref_role(pool_keys, n_by, seed):
    """section 16, literally: a fresh generator per role; strata wf_year ascending, lt5 then 5to20; pool sorted by (date, symbol);
    if len(pool) <= n take all, else idx = rng.choice(len(pool), size=n, replace=False); rows at sorted(idx)"""
    rng = np.random.default_rng(seed)
    out = []
    for y in B.WF_YEARS:
        for b in B.BUCKETS:
            pool = sorted(pool_keys.get((y, b), []))
            n = n_by[(y, b)]
            if len(pool) <= n:
                out += pool
            else:
                idx = rng.choice(len(pool), size=n, replace=False)
                out += [pool[i] for i in sorted(idx)]
    return out


def _role_rows(res, role):
    return sorted(map(tuple, res.rows.loc[res.rows[role] == 1, ["date", "symbol"]].to_numpy().tolist()))


def test_draws_follow_the_literal_procedure(big):
    n_pm = {WF_KEY(y, b): n for (y, b), n in big.n_by["pmfail"].items()}
    n_r2 = {WF_KEY(y, b): n for (y, b), n in big.n_by["runner2"].items()}
    assert n_pm[("2016-17", "5to20")] == 13 and n_pm[("2016-17", "lt5")] == 4 and n_pm[("2017-18", "5to20")] == 12
    assert n_r2[("2016-17", "5to20")] == 12
    ten = {k: 10 for k in n_pm}
    for role, n_by in (("nonevent", n_pm), ("runner2_nonevent", n_r2), ("quotes_pmfail", ten), ("quotes_runner2", ten)):
        want = ref_role(_pool_keys(big, role), n_by, B.SEEDS[role])
        assert _role_rows(big, role) == sorted(want), role
    assert len(_role_rows(big, "nonevent")) == 13 + 4 + 12
    assert len(_role_rows(big, "runner2_nonevent")) == 12
    q = big.rows[big.rows["quotes_pmfail"] == 1]
    assert (q.groupby(["wf_year", "price_bucket"]).size().to_dict() == {("2016-17", "5to20"): 10, ("2016-17", "lt5"): 4, ("2017-18", "5to20"): 10})
    assert B.SEEDS == {"nonevent": 20261006, "runner2_nonevent": 20261009, "quotes_pmfail": 20261007, "quotes_runner2": 20261008}


def test_draw_role_take_all_does_not_touch_the_generator():
    rng_pool = lambda n, t0: (np.arange(t0, t0 + n, dtype=np.int64), np.zeros(n, np.int64))
    pools = {(y, b): rng_pool(0, 0) for y in range(9) for b in range(2)}
    pools[(0, 0)] = rng_pool(3, 0)                                  # take all (3 <= 5): no draw
    pools[(0, 1)] = rng_pool(50, 100)                               # draw 5 of 50
    pools[(1, 0)] = rng_pool(6, 300)                                # len(pool) == n: take all, no draw either
    pools[(3, 0)] = rng_pool(40, 500)                               # draw 7 of 40
    n_by = {k: 0 for k in pools}
    n_by[(0, 0)], n_by[(0, 1)], n_by[(1, 0)], n_by[(3, 0)] = 5, 5, 6, 7
    t, s = B.draw_role(pools, n_by, 20261006)
    rng = np.random.default_rng(20261006)
    want = ([0, 1, 2] + [100 + i for i in sorted(rng.choice(50, size=5, replace=False))] + list(range(300, 306))
            + [500 + i for i in sorted(rng.choice(40, size=7, replace=False))])
    assert t.tolist() == want
    t2, _ = B.draw_role(pools, n_by, 20261006)
    assert t2.tolist() == want                                        # reproducible
    t3, _ = B.draw_role(pools, n_by, 20261007)
    assert t3.tolist() != want                                        # the seed matters
    # the pool is sorted by (date, symbol) before drawing, whatever order it arrives in
    pt, ps = np.array([5, 1, 3, 1]), np.array([0, 2, 0, 1])
    tt, ss = B.draw_stratum(pt, ps, 10, np.random.default_rng(1))
    assert list(zip(tt.tolist(), ss.tolist())) == [(1, 1), (1, 2), (3, 0), (5, 0)]


def test_seeds_reproduce_and_differ(big, monkeypatch):
    again = _big_world().build()
    assert again.rows.equals(big.rows)
    monkeypatch.setitem(B.SEEDS, "nonevent", 1)
    other = _big_world().build()
    assert _role_rows(other, "nonevent") != _role_rows(big, "nonevent")
    assert _role_rows(other, "quotes_pmfail") == _role_rows(big, "quotes_pmfail")


def test_nonevent_pools_exclude_earlier_roles(big):
    ne_pool = {k for v in _pool_keys(big, "nonevent").values() for k in v}
    r2ne_pool = {k for v in _pool_keys(big, "runner2_nonevent").values() for k in v}
    earlier = keys(big, "pm_event") | keys(big, "r_loose")
    assert ne_pool and not (ne_pool & earlier)
    assert ne_pool == keys(big, "pm_flat") - earlier
    assert r2ne_pool and not (r2ne_pool & (earlier | keys(big, "nonevent")))
    assert r2ne_pool == keys(big, "r_flat") - earlier - keys(big, "nonevent")
    assert ("2016-12-01", "FLATA") in ne_pool and ("2016-12-01", "FLATB") not in ne_pool and ("2016-12-01", "FLATS") not in ne_pool
    # D2 sessions of a run are runner2_d2 (an earlier role): never in either pool
    for d, s in keys(big, "r_loose"):
        assert (d, s) not in ne_pool and (d, s) not in r2ne_pool
    # a carry-SSR session fails a section-4 / section-2 filter: in neither pool
    assert ("2016-08-30", "SSRZ") not in r2ne_pool and ("2016-12-01", "FLATS") not in r2ne_pool
    # R00 runs on D1 = 2016-10-03: its D2 is runner2_d2 (earlier role); the session after has c(D1) / c(D0) = 10 / 14 (not flat)
    assert (nd("2016-10-03", 1), "R00") not in r2ne_pool and (nd("2016-10-03", 2), "R00") not in r2ne_pool
    assert (nd("2016-10-03", 3), "R00") in r2ne_pool or (nd("2016-10-03", 3), "R00") in keys(big, "nonevent")


def test_quotes_drawn_from_registered_events(big):
    assert {k for v in _pool_keys(big, "quotes_pmfail").values() for k in v} == keys(big, "pm_reg")
    assert {k for v in _pool_keys(big, "quotes_runner2").values() for k in v} == keys(big, "r_reg")
    qp, qr = keys(big, "quotes_pmfail"), keys(big, "quotes_runner2")
    assert qp and qp <= keys(big, "pm_reg") and ("2016-08-30", "SSRZ") not in qp
    assert ("2016-08-30", "SSRZ") in keys(big, "pm_event")          # the carry-SSR day is listed (pmfail_event), never quoted
    assert qr and qr <= keys(big, "r_reg") and len(qr) == 10
    rows = big.rows
    assert ((rows["quotes_pmfail"] == 1) <= (rows["pmfail_event"] == 1)).all()
    assert ((rows["quotes_runner2"] == 1) <= (rows["runner2_d2"] == 1)).all()


def test_role_order_and_columns(big):
    assert list(big.rows.columns) == list(B.COLUMNS)
    assert list(B.COLUMNS) == ["symbol", "date", "wf_year", "price_bucket", "pmfail_event", "runner2_d2", "nonevent",
                               "runner2_nonevent", "quotes_pmfail", "quotes_runner2"]
    r = big.rows
    assert not r.duplicated(["symbol", "date"]).any()
    assert (r[list(B.ROLES)].sum(axis=1) >= 1).all() and set(np.unique(r[list(B.ROLES)].to_numpy())) <= {0, 1}
    assert ((r["nonevent"] == 1) & ((r["pmfail_event"] == 1) | (r["runner2_d2"] == 1))).sum() == 0
    assert list(zip(r["date"], r["symbol"])) == sorted(zip(r["date"], r["symbol"]))
    assert set(r["wf_year"]) <= set(B.WF_YEARS) and set(r["price_bucket"]) <= {"lt5", "5to20"}
    assert (r["date"] >= "2016-07-01").all() and (r["date"] <= "2025-06-29").all()


# ------------------------------------------------------------------ the cut
def test_cut_at_2025_06_30():
    days = pd.bdate_range("2025-04-01", "2025-07-31")
    w = World(days)
    w.add("CUTA").set("CUTA", "2025-06-27", o=12.5)
    w.add("CUTB").set("CUTB", "2025-06-30", o=12.5)
    w.add("CUTC").set("CUTC", "2025-07-01", o=12.5)
    res = w.build()
    assert ("2025-06-27", "CUTA") in keys(res, "pm_event")
    assert res.days.max() < B.CUT and (res.rows["date"] < "2025-06-30").all()
    assert res.counts["inputs"]["raw_rows_dropped_at_cut"] == 3 * len(days[days >= "2025-06-30"])
    assert res.counts["pmfail"]["registered"]["by_year"]["2024-25"]["all"] == 1


def test_read_daily_cuts_at_read(tmp_path):
    df = pd.DataFrame({"symbol": ["A", "A", "A"], "date": pd.to_datetime(["2025-06-27", "2025-06-30", "2025-07-01"]),
                       "o": [1.0, 2.0, 3.0], "h": 1.0, "l": 1.0, "c": 1.0, "v": [1, 2, 3]})
    p = tmp_path / "d.parquet"
    df.to_parquet(p, index=False)
    got = B.read_daily(str(p), ("symbol", "date", "o", "c"))
    assert list(got["o"]) == [1.0] and list(got.columns) == ["symbol", "date", "o", "c"]


# ------------------------------------------------------------------ output files
def test_csv_and_sha_format(big, tmp_path):
    out = str(tmp_path / "namedays_r1.csv")
    p, line = B.write_outputs(big, out, {"sha256": {}})
    data = open(out, "rb").read()
    assert b"\r" not in data and data.endswith(b"\n") and not data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8")
    lines = text.split("\n")[:-1]
    assert lines[0] == "symbol,date,wf_year,price_bucket,pmfail_event,runner2_d2,nonevent,runner2_nonevent,quotes_pmfail,quotes_runner2"
    assert len(lines) == len(big.rows) + 1
    pat = re.compile(r"^[A-Z0-9_]+,\d{4}-\d{2}-\d{2},20\d\d-\d\d,(lt5|5to20)(,[01]){6}$")
    assert all(pat.match(x) for x in lines[1:])
    back = pd.read_csv(out, dtype={"symbol": str, "date": str})
    assert list(back.columns) == list(B.COLUMNS) and list(zip(back["date"], back["symbol"])) == sorted(zip(back["date"], back["symbol"]))
    sha = open(p["sha"], "rb").read()
    assert sha == f"{hashlib.sha256(data).hexdigest()}  namedays_r1.csv\n".encode()
    assert re.fullmatch(rb"[0-9a-f]{64}  namedays_r1\.csv\n", sha) and line == sha.decode().strip()
    assert os.path.basename(p["sha"]) == "namedays_r1.sha256" and os.path.basename(p["counts"]) == "namedays_r1_counts.json"
    cj = json.load(open(p["counts"]))
    assert cj["meta"]["csv_sha256"] == hashlib.sha256(data).hexdigest() and cj["rows"] == len(big.rows)
    v = cj["meta"]["versions"]                                                     # the draws re-derive only under the same numpy
    assert v["numpy"] == np.__version__ and v["pandas"] == pd.__version__ and v["python"] == sys.version and v["pyarrow"]
    # same bytes again: fine; different bytes: refused, the file untouched
    B.write_outputs(big, out, {"sha256": {}})
    other = big.rows.iloc[1:].reset_index(drop=True)
    with pytest.raises(SystemExit, match="different bytes"):
        B.write_outputs(SimpleNamespace(rows=other, counts=big.counts), out, {})
    assert open(out, "rb").read() == data


def test_main_dry_run_writes_nothing(tmp_path, monkeypatch):
    w, ca = r2_world()
    raw, sp = w.frames()
    monkeypatch.setattr(B, "verify_inputs", lambda *a, **k: {"sha256": {"daily_raw.parquet": "x" * 64}})
    monkeypatch.setattr(B, "read_daily", lambda path, cols: (raw if path == B.RAW_PATH else sp)[list(cols)].copy())
    monkeypatch.setattr(B, "read_calendar", lambda *a, **k: ca)
    out = tmp_path / "sub" / "namedays_r1.csv"
    B.main(["--dry-run", "--out", str(out)])
    assert not (tmp_path / "sub").exists() and not list(tmp_path.iterdir())
    res = B.main(["--out", str(out)])
    assert out.exists() and (tmp_path / "sub" / "namedays_r1.sha256").exists() and (tmp_path / "sub" / "namedays_r1_counts.json").exists()
    assert out.read_bytes() == B.csv_bytes(res.rows)


def test_verify_inputs_refuses_on_any_mismatch(tmp_path, monkeypatch):
    files = {}
    for n in ("daily_raw.parquet", "daily_split.parquet", "corporate_actions_wide.csv"):
        files[n] = tmp_path / n
        files[n].write_bytes(n.encode())
    sha = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in files.items()}
    monkeypatch.setattr(B, "SHA_RAW", sha["daily_raw.parquet"])
    monkeypatch.setattr(B, "SHA_SPLIT", sha["daily_split.parquet"])
    monkeypatch.setattr(B, "SHA_CA", sha["corporate_actions_wide.csv"])
    man, cman = tmp_path / "m.json", tmp_path / "cm.json"
    good = {"manifest_sha256": B.SHA_MANIFEST, "key_files": {"daily_raw.parquet": {"sha256": sha["daily_raw.parquet"]},
                                                              "daily_split.parquet": {"sha256": sha["daily_split.parquet"]}}}
    man.write_text(json.dumps(good))
    cman.write_text(json.dumps({"sha256": {"corporate_actions_wide.csv": sha["corporate_actions_wide.csv"]}, "start": "2016-06-01"}))
    args = (str(files["daily_raw.parquet"]), str(files["daily_split.parquet"]), str(man), str(files["corporate_actions_wide.csv"]), str(cman))
    info = B.verify_inputs(*args)
    assert info["sha256"] == sha
    files["daily_raw.parquet"].write_bytes(b"changed")
    with pytest.raises(SystemExit, match="daily_raw.parquet on disk"):
        B.verify_inputs(*args)
    files["daily_raw.parquet"].write_bytes(b"daily_raw.parquet")
    man.write_text(json.dumps({**good, "manifest_sha256": "0" * 64}))
    with pytest.raises(SystemExit, match="manifest_sha256"):
        B.verify_inputs(*args)
    man.write_text(json.dumps(good))
    cman.write_text(json.dumps({"sha256": {"corporate_actions_wide.csv": "0" * 64}}))
    with pytest.raises(SystemExit, match="calendar manifest"):
        B.verify_inputs(*args)
    cman.write_text(json.dumps({"sha256": {"corporate_actions_wide.csv": sha["corporate_actions_wide.csv"]}}))
    assert B.verify_inputs(*args)["sha256"] == sha                                # restored: passes again
    files["daily_split.parquet"].write_bytes(b"changed")                          # the split file on disk
    with pytest.raises(SystemExit, match="daily_split.parquet on disk"):
        B.verify_inputs(*args)
    files["daily_split.parquet"].write_bytes(b"daily_split.parquet")
    files["corporate_actions_wide.csv"].write_bytes(b"changed")                   # the calendar on disk
    with pytest.raises(SystemExit, match="corporate_actions_wide.csv hashes to"):
        B.verify_inputs(*args)
    files["corporate_actions_wide.csv"].write_bytes(b"corporate_actions_wide.csv")
    for name in ("daily_raw.parquet", "daily_split.parquet"):                     # one key_files entry in the manifest
        bad = json.loads(json.dumps(good))
        bad["key_files"][name]["sha256"] = "0" * 64
        man.write_text(json.dumps(bad))
        with pytest.raises(SystemExit, match=f"the manifest lists {name}"):
            B.verify_inputs(*args)
    man.write_text(json.dumps(good))
    assert B.verify_inputs(*args)["sha256"] == sha


def test_registered_constants_are_section_3():
    assert B.SHA_RAW == "fa42412d579ae673815bea25e1c14f9c87a93904af779ccffb03333c8e1bdccd"
    assert B.SHA_SPLIT == "083f8c23d1d62cf7bda99d5c9a6373130c336ac605f57db5eeac832504281f6d"
    assert B.SHA_MANIFEST == "380b05f2e0c4dfa32faabf2c86311f869d7371d3810a801bbf8a6c1f9ade4b78"
    assert B.SHA_CA == "e5bc8487daf94a6124823bc24b6c382e9fd00237acbab81457fa42ef3b0d83a5"
    assert B.OUT_DEFAULT == r"C:\EdgeLog\alpaca_cache\disc_gapper\namedays_r1.csv"
    assert abs(B.YEARS - 3285 / 365.25) < 1e-12 and B.WF_YEARS[0] == "2016-17" and B.WF_YEARS[-1] == "2024-25"
    assert B.KMAX == 50


def test_count_bar_reading(big):
    b = big.counts["count_bar"]["pmfail"]
    assert b["n"] == 13 + 4 + 12 and b["per_year"]["2016-17"] == 17 and b["per_year"]["2017-18"] == 12
    assert b["mean_ge_50"] is False and b["n_ge_100"] is False and "2018-19" in b["thin_years_under_25"]
    assert abs(b["n_per_year"] - 29 / B.YEARS) < 1e-12
