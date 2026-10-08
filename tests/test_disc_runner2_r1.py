"""tools/runner2_r1_stageA.py - RUNNER2 r1 Stage A (docs/PREREG_runner2_r1_2026-10-06.md, AMENDMENT 0).

SYNTHETIC data only: every bar, quote, manifest, book and null file is built in tmp_path; EDGELOG_HOME points there;
no file under C:\\EdgeLog is read and no socket is opened. Proved here:
  * the loader: Alpaca UTC bar-START stamps -> ET minutes across EST / EDT, seconds and wrong-date stamps refuse, v <= 0 and
    price <= 0 bars dropped and counted, identical duplicates dropped, conflicting duplicates refuse; the photograph refuses
    on the manifest / namedays / file sha, a missing FB/META probe, an incomplete pull, a date on or after the cut; 403 rows
    are 'refused', partial pages 'missing'; an iex URL labels the run IEX; merged multi-page bodies parse;
  * 5m bars (c = the LAST present close; empty 5m bars do not exist), VWAP (vw, else (h+l+c)/3; no premarket);
  * the trigger: the cross must come from a strictly EARLIER 5m bar; close times 09:45..14:00 only; c5 == VWAP is a cross,
    not below; first signal only, no re-arm; NOCROSS;
  * entry [B close, B close + 4]; no_fill_bar; resume bars (5 vs 4 empty minutes); E >= S; S excludes the entry bar; W
    unrounded; SSR at exactly 0.9 x c(D1), after B, premarket (the 04:00 reading); the legal fill;
  * stop readings L and N (open-through, level touch, next present bar across a gap, halt-jumped, none before 16:00), the
    15:54 last judged bar, the 15:55 exit at the first present bar, halted into the close (next open, nights, stress on
    no bar / a split flag / the cut), longs mirrored;
  * costs, locate and nights; spreads from marks (in-force rule, invalid marks, the bucket-of-20 rule, refused day priors);
  * N* (smallest crossing, none -> 500,000, a non-monotone maxDD), the 1% cap, ROC / t / Sortino / PF / years, R-sum;
  * the null half: default_rng(20261010), at most 21 attempts, the same bar for P and W, blocked == interleaved, the
    family summary (NaN -> -inf), read_null's refusals and copy;
  * the count gate (449 / 450), --counts never walks an exit, a gate miss does not stop --run, --run re-checks the filed
    counts, the verdict (PASS / RESEARCH ROW / FAIL), power.json carries lines only, outputs are written once.
"""
import hashlib
import json
import os
import socket
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
sys.path.insert(0, TOOLS)
import disc_runner2_r1_stageA as R  # noqa: E402

D = "2019-03-12"            # an ordinary EDT session
LIST_SHA = "ab" * 32


# ------------------------------------------------------------------ helpers
def flat(m0, m1, px, v=1000.0, vw=None):
    return [(m, px, px, px, px, v, px if vw is None else vw) for m in range(m0, m1)]


def mkday(rows, date=D):
    if not rows:
        return R.make_day(date, [], [], [], [], [], [], [])
    m, o, h, lo, c, v, vw = zip(*rows)
    return R.make_day(date, m, o, h, lo, c, v, vw)


def signal_rows(after=10.0, pre=10.5, hi=11.0, sig=10.5, end=R.RTH1):
    """09:30-09:39 at `hi` (cross above VWAP), 09:40-09:44 at `sig` (B = k 2, close 09:45), then `after` to `end`"""
    return (flat(240, 245, pre, v=100) + flat(570, 580, hi) + flat(580, 585, sig) + flat(585, end, after))


def mkev(sym="AAA", d2=D, c0=7.0, c1=10.0, adv=2e6, opens=None, flags=None, nxt=None, next_session="auto", **kw):
    d2 = pd.Timestamp(d2)
    nd = tuple(pd.bdate_range(d2 + pd.Timedelta(days=1), periods=10)) if nxt is None else tuple(pd.Timestamp(x) for x in nxt)
    op = tuple([10.0] * len(nd)) if opens is None else tuple(opens)
    fl = tuple([False] * len(nd)) if flags is None else tuple(flags)
    ns = (nd[0] if nd else None) if next_session == "auto" else next_session
    args = dict(symbol=sym, d2=d2, wf_year=R.wf_year_of(d2), bucket="5to20" if c1 >= 5 else "lt5", c0=c0, c1=c1, l1=c0,
                adv=adv, v2=1e6, o2=c1 * 1.1, nxt_dates=nd, nxt_open=op, nxt_flag=fl, next_session=ns)
    args.update(kw)
    return R.Event(**args)


def utc_iso(date, m):
    t = pd.Timestamp(f"{date} {m // 60:02d}:{m % 60:02d}", tz="America/New_York").tz_convert("UTC")
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def body_for(sym, date, rows):
    bars = [{"t": utc_iso(date, m), "o": o, "h": h, "l": lo, "c": c, "v": v, "n": 1, "vw": vw}
            for m, o, h, lo, c, v, vw in rows]
    return json.dumps({"bars": {sym: bars}, "next_page_token": None}).encode()


def probe_recs():
    return [{"kind": "probe", "endpoint": ep, "result": "SAME MAPPING"} for ep in R.PROBE_ENDPOINTS]


class Pull:
    """a synthetic pull directory in MANAGER's layout"""

    def __init__(self, root):
        self.root = str(root)
        os.makedirs(os.path.join(self.root, "bars"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "quotes"), exist_ok=True)
        self.recs = [{"kind": "run_header", "list_sha256": LIST_SHA}] + probe_recs()

    def bars(self, sym, date, rows=None, status=200, pages=1, write=True, url_feed="sip"):
        date = f"{pd.Timestamp(date):%Y-%m-%d}"
        p = os.path.join(self.root, "bars", f"{sym}_{date}.json")
        body = body_for(sym, date, rows or []) if status == 200 else b'{"message": "no"}'
        if status == 200 and write:
            with open(p, "wb") as f:
                f.write(body)
        self.recs.append({"kind": "bars", "symbol": sym, "date": date, "url": f"https://x/v2/stocks/bars?feed={url_feed}",
                          "status": status, "sha256": hashlib.sha256(body).hexdigest(), "file": p if status == 200 else None,
                          "pages": pages})

    def marks(self, sym, date, quotes=None, status=200):
        date = f"{pd.Timestamp(date):%Y-%m-%d}"
        p = os.path.join(self.root, "quotes", f"{sym}_{date}_runner2_marks.json")
        out = {"marks": {}}
        for mk in R.MARKS:
            q = (quotes or {}).get(mk)
            bodyd = {"quotes": {sym: [q] if q else []}, "next_page_token": None}
            out["marks"][mk] = bodyd
            self.recs.append({"kind": "quotes_runner2_mark", "symbol": sym, "date": date, "mark": mk,
                              "url": "https://x/v2/stocks/quotes?feed=sip", "status": status, "file": p})
        if status == 200:
            with open(p, "wb") as f:
                f.write(json.dumps(out).encode())

    def manifest(self):
        data = ("\n".join(json.dumps(r) for r in self.recs) + "\n").encode()
        with open(os.path.join(self.root, "manifest.jsonl"), "wb") as f:
            f.write(data)
        return hashlib.sha256(data).hexdigest()

    def photo(self, require_probe=True):
        return R.Photograph(self.root, self.manifest(), LIST_SHA, require_probe)


def quote(date, mk, bp, ap, sec_before=5):
    t = pd.Timestamp(f"{date} {mk}:00", tz="America/New_York") - pd.Timedelta(seconds=sec_before)
    return {"t": t.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "bp": bp, "ap": ap, "bs": 1, "as": 1}


# ================================================================== loader and stamps
def test_utc_start_stamps_map_to_et_minutes_across_dst():
    assert R.et_minutes(["2019-03-08T14:30:00Z"], "2019-03-08")[0] == 570          # EST
    assert R.et_minutes(["2019-03-11T13:30:00Z"], "2019-03-11")[0] == 570          # EDT
    assert R.et_minutes(["2019-03-11T14:30:00Z"], "2019-03-11")[0] == 630
    assert R.et_minutes(["2019-03-11T08:00:00Z"], "2019-03-11")[0] == 240          # 04:00 premarket


def test_seconds_and_wrong_date_refuse():
    with pytest.raises(SystemExit, match="seconds"):
        R.et_minutes(["2019-03-11T13:30:30Z"], "2019-03-11")
    with pytest.raises(SystemExit, match="ET date"):
        R.et_minutes(["2019-03-12T13:30:00Z"], "2019-03-11")


def test_zero_volume_and_bad_price_bars_are_dropped_and_counted():
    d = mkday([(570, 10, 10, 10, 10, 0, 10), (571, 10, 10, 10, 10, -1, 10), (572, 0, 10, 10, 10, 5, 10),
               (573, 10, 10, 10, 10, 5, 10), (573, 10, 10, 10, 10, 5, 10)])
    assert d.info["dropped_v_le_0"] == 2 and d.info["dropped_price_le_0"] == 1
    assert d.info["dropped_identical_duplicate"] == 1
    assert d.present.sum() == 1 and d.present[573 - 240]
    with pytest.raises(SystemExit, match="conflicting duplicate"):
        mkday([(573, 10, 10, 10, 10, 5, 10), (573, 10, 11, 10, 10, 5, 10)])


def test_photograph_verifies_then_parses(tmp_path):
    pu = Pull(tmp_path)
    pu.bars("AAA", D, flat(570, 575, 10.0))
    ph = pu.photo()
    st = ph.verify([("AAA", D)], [])
    assert st["bars"]["ok"] == 1 and st["feed"] == "sip"
    r = ph.bars("AAA", D)
    assert r.status == "ok" and r.day.present.sum() == 5 and r.day.present[570 - 240]


def test_photograph_refusals(tmp_path):
    pu = Pull(tmp_path)
    pu.bars("AAA", D, flat(570, 575, 10.0))
    sha = pu.manifest()
    with pytest.raises(SystemExit, match="MANAGER named"):
        R.Photograph(pu.root, "0" * 64, LIST_SHA).verify([("AAA", D)], [])
    with pytest.raises(SystemExit, match="cite namedays"):
        R.Photograph(pu.root, sha, "cd" * 32).verify([("AAA", D)], [])
    with pytest.raises(SystemExit, match="incomplete"):
        R.Photograph(pu.root, sha, LIST_SHA).verify([("AAA", D), ("BBB", D)], [])
    with pytest.raises(SystemExit, match="2025-06-30"):
        R.Photograph(pu.root, sha, LIST_SHA).verify([("AAA", "2025-06-30")], [])
    with open(os.path.join(pu.root, "bars", f"AAA_{D}.json"), "ab") as f:
        f.write(b" ")
    with pytest.raises(SystemExit, match="hashes to"):
        R.Photograph(pu.root, sha, LIST_SHA).verify([("AAA", D)], [])
    with pytest.raises(SystemExit, match="before the photograph"):
        R.Photograph(pu.root, sha, LIST_SHA).bars("AAA", D)


def test_photograph_probe_is_required(tmp_path):
    pu = Pull(tmp_path)
    pu.recs = [r for r in pu.recs if r.get("endpoint") != "1Min"]
    pu.bars("AAA", D, flat(570, 575, 10.0))
    with pytest.raises(SystemExit, match="FB/META probe.*1Min"):
        pu.photo().verify([("AAA", D)], [])
    assert pu.photo(require_probe=False).verify([("AAA", D)], [])["probe"]["1Min"] is False


def test_photograph_status_labels_and_iex(tmp_path):
    pu = Pull(tmp_path)
    pu.bars("AAA", D, status=403)
    pu.bars("BBB", D, status=500)
    pu.bars("CCC", D, flat(570, 575, 10.0), pages=2, write=False)          # a 200 page of a failed multi-page attempt
    pu.bars("DDD", D, [], url_feed="iex")
    ph = pu.photo()
    st = ph.verify([("AAA", D), ("BBB", D), ("CCC", D), ("DDD", D)], [])
    assert ph.status[("AAA", D)] == "refused" and ph.status[("BBB", D)] == "missing"
    assert ph.status[("CCC", D)] == "missing" and st["feed"] == "iex"
    assert ph.bars("DDD", D).status == "empty" and ph.bars("AAA", D).day is None


def test_merged_multipage_body_parses_and_is_stamped(tmp_path):
    pu = Pull(tmp_path)
    rows = flat(570, 580, 10.0)
    p = os.path.join(pu.root, "bars", f"AAA_{D}.json")
    merged = {"bars": {"AAA": json.loads(body_for("AAA", D, rows))["bars"]["AAA"]}, "pages": 2}
    with open(p, "wb") as f:
        f.write(json.dumps(merged).encode())
    for _ in range(2):
        pu.recs.append({"kind": "bars", "symbol": "AAA", "date": D, "url": "u?feed=sip", "status": 200, "sha256": "x",
                        "file": p, "pages": 2})
    ph = pu.photo()
    st = ph.verify([("AAA", D)], [])
    assert f"AAA_{D}.json" in st["unpaged_file_sha256"]
    assert ph.bars("AAA", D).day.present.sum() == 10


def test_module_imports_no_network_libraries():
    code = ("import sys; sys.path.insert(0, %r); import disc_runner2_r1_stageA; "
            "bad = [m for m in ('requests', 'alpaca_rate', 'alpaca_keys', 'import_alpaca_stocks') if m in sys.modules]; "
            "print(bad); sys.exit(1 if bad else 0)" % TOOLS)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_write_once(tmp_path):
    p = str(tmp_path / "x.json")
    R.write_once(p, b"a")
    R.write_once(p, b"a")
    with pytest.raises(SystemExit, match="different bytes"):
        R.write_once(p, b"b")


# ================================================================== 5m bars, VWAP, trigger
def test_5m_close_is_last_present_close_and_empty_bars_do_not_exist():
    rows = [(570, 10, 10.5, 9.9, 10.2, 100, 10.1), (571, 10.2, 10.3, 10.1, 10.25, 100, 10.2),
            (572, 10.25, 10.4, 10.2, 10.3, 100, 10.3)]                       # 09:33 and 09:34 missing
    d = mkday(rows + flat(585, 590, 11.0))
    b = R.bars5(d)
    assert [x.k for x in b] == [0, 3]
    assert b[0].c == 10.3 and b[0].o == 10 and b[0].h == 10.5 and b[0].l == 9.9 and b[0].last_m == 572
    assert b[0].close_t == 575


def test_vwap_uses_vw_else_typical_price_and_excludes_premarket():
    d = mkday([(300, 50, 50, 50, 50, 1e6, 50), (570, 10, 12, 8, 10, 100, -1), (571, 10, 10, 10, 10, 100, 20)])
    vw, nfb, nb = R.vwap_curve(d)
    assert nfb == 1 and nb == 2
    assert vw[570 - 240] == pytest.approx(10.0)                                # (12 + 8 + 10) / 3
    assert vw[571 - 240] == pytest.approx(15.0)


def test_trigger_needs_a_strictly_earlier_cross_and_the_window():
    # 09:30 bar closes below VWAP after trading above: no cross before it, and its close time 09:35 is outside the window
    d = mkday(flat(570, 575, 11.0, vw=12.0) + flat(575, 600, 9.0, vw=9.0))
    assert R.find_signal(R.bars5(d), R.vwap_curve(d)[0]) is None
    sig = R.find_signal(R.bars5(d), R.vwap_curve(d)[0], nocross=True)
    assert sig.k == 2 and sig.close_t == 585                                    # NOCROSS: first close below in the window
    d = mkday(signal_rows())
    b = R.find_signal(R.bars5(d), R.vwap_curve(d)[0])
    assert b.k == 2 and b.close_t == 585 and b.last_m == 584


def test_k1_below_is_not_a_signal_k2_is():
    d = mkday(flat(570, 575, 11.0) + flat(575, 580, 10.0) + flat(580, 585, 9.0) + flat(585, 960, 9.0))
    b = R.find_signal(R.bars5(d), R.vwap_curve(d)[0])
    assert b.k == 2                                                             # k 1 (close 09:40) closed below but is outside


def test_window_ends_at_the_bar_closing_1400():
    above = flat(570, 575, 11.0)
    # stays exactly at VWAP until the 13:55 bar (close 14:00) drops below
    d = mkday(above + flat(575, 835, 11.0) + flat(835, 840, 10.0) + flat(840, 960, 10.0))
    b = R.find_signal(R.bars5(d), R.vwap_curve(d)[0])
    assert b.close_t == 840 and b.k == 53
    d = mkday(above + flat(575, 840, 11.0) + flat(840, 960, 10.0))            # first close below at 14:05: no signal
    assert R.find_signal(R.bars5(d), R.vwap_curve(d)[0]) is None


def test_close_equal_to_vwap_is_a_cross_not_below():
    d = mkday(flat(570, 580, 10.0) + flat(580, 585, 9.0) + flat(585, 960, 9.0))
    b = R.find_signal(R.bars5(d), R.vwap_curve(d)[0])
    assert b.k == 2                                                             # k 0 / 1 closed == VWAP: seen_above set


def test_first_signal_only_blocked_signal_does_not_rearm():
    rows = signal_rows()
    rows = [r for r in rows if not (585 <= r[0] <= 589)] + flat(600, 601, 10.0)  # no bar in 09:45..09:49: no_fill_bar
    rows = sorted({r[0]: r for r in rows}.values())
    s = R.r2_day(mkday(rows), mkev())
    assert s.status == "no_fill_bar" and s.sig.k == 2


# ================================================================== entry, stops, SSR
def test_entry_window_is_close_to_close_plus_4():
    base = [r for r in signal_rows() if not (585 <= r[0] < 600)]
    s = R.r2_day(mkday(base + [(587, 10.4, 10.4, 10.4, 10.4, 1000, 10.4)]), mkev())
    assert s.status == "filled" and s.entry_m == 587 and s.E == 10.4
    s = R.r2_day(mkday(base + [(589, 10.4, 10.4, 10.4, 10.4, 1000, 10.4)]), mkev())
    assert s.entry_m == 589
    s = R.r2_day(mkday(base + [(590, 10.4, 10.4, 10.4, 10.4, 1000, 10.4)]), mkev())
    assert s.status == "no_fill_bar"


def test_resume_bar_five_vs_four_empty_minutes():
    d = mkday(flat(570, 580, 11.0) + flat(580, 581, 10.5) + flat(586, 960, 10.0))   # 09:41..09:45 empty (5): resume 09:46
    assert R.r2_day(d, mkev(), halt_k=5).status == "resume_bar"
    d = mkday(flat(570, 580, 11.0) + flat(580, 582, 10.5) + flat(586, 960, 10.0))   # 09:42..09:45 empty (4)
    s = R.r2_day(d, mkev(), halt_k=5)
    assert s.status == "filled" and s.entry_m == 586
    assert R.r2_day(d, mkev(), halt_k=4).status == "resume_bar"


def test_entry_at_or_through_stop_is_no_trade():
    rows = [r for r in signal_rows() if r[0] != 585] + [(585, 11.01, 11.01, 11.01, 11.01, 1000, 11.01)]
    s = R.r2_day(mkday(sorted(rows)), mkev())
    assert s.status == "E_ge_S" and s.S == pytest.approx(11.01)


def test_stop_levels_exclude_entry_bar_and_w_is_unrounded():
    rows = [r for r in signal_rows() if r[0] != 585] + [(585, 10.37, 12.0, 10.3, 10.4, 1000, 10.4)]
    s = R.r2_day(mkday(sorted(rows)), mkev())
    assert s.status == "filled" and s.E == 10.37 and s.S == pytest.approx(11.01)  # the entry bar's 12.00 high is not in S
    assert s.W == pytest.approx(10.37 + 1.5 * (11.01 - 10.37))                  # 11.33, not rounded to the cent
    rows = [r for r in signal_rows() if r[0] != 585] + [(585, 10.34, 10.34, 10.34, 10.34, 1000, 10.34)]
    s = R.r2_day(mkday(sorted(rows)), mkev())
    assert s.W == pytest.approx(10.34 + 1.5 * 0.67)


def test_ssr_at_exactly_ninety_percent_blocks_and_one_cent_above_does_not():
    rows = signal_rows()
    hit = [r if r[0] != 571 else (571, 11.0, 11.0, 9.0, 11.0, 1000, 11.0) for r in rows]
    s = R.r2_day(mkday(hit), mkev(c1=10.0))
    assert s.status == "ssr_active"
    near = [r if r[0] != 571 else (571, 11.0, 11.0, 9.01, 11.0, 1000, 11.0) for r in rows]
    assert R.r2_day(mkday(near), mkev(c1=10.0)).status == "filled"


def test_ssr_after_b_or_in_premarket_is_not_active_but_0400_reading_flags_premarket():
    rows = signal_rows()
    late = [r if r[0] != 585 else (585, 10.5, 10.5, 8.0, 10.0, 1000, 10.0) for r in rows]   # low 8.0 in the entry bar
    assert R.r2_day(mkday(late), mkev(c1=10.0)).status == "filled"
    pm = [r if r[0] != 240 else (240, 10.5, 10.5, 8.5, 10.5, 100, 10.5) for r in rows]
    s = R.r2_day(mkday(pm), mkev(c1=10.0))
    assert s.status == "filled" and s.ssr_0400 is True


def test_ssr_open_reading():
    rows = [r if r[0] != 570 else (570, 11.0, 11.0, 8.9, 11.0, 1000, 11.0) for r in signal_rows()]
    s = R.r2_day(mkday(rows), mkev(c1=10.0))
    assert s.ssr_open is True and s.status == "ssr_active"


def test_legal_fill():
    d = mkday(signal_rows())
    m, E = R.legal_fill(d, 585, 10.5, 11.01)
    assert m is None                                                            # highs 10.0 < limit 10.51 + 0.01
    rows = [r if r[0] != 587 else (587, 10.0, 10.52, 10.0, 10.0, 1000, 10.0) for r in signal_rows()]
    m, E = R.legal_fill(mkday(rows), 585, 10.5, 11.01)
    assert m == 587 and E == pytest.approx(10.51)
    rows = [r if r[0] != 590 else (590, 10.0, 12.0, 10.0, 10.0, 1000, 10.0) for r in signal_rows()]
    assert R.legal_fill(mkday(rows), 585, 10.5, 11.01) == (None, None)         # 09:50 is outside [ct, ct + 5)


# ================================================================== stop judging and exits
def test_reading_l_and_n():
    rows = flat(585, 960, 10.0)
    rows = [r if r[0] != 600 else (600, 10.0, 11.5, 10.0, 10.0, 1000, 10.0) for r in rows]  # touch 11.01 at 10:00
    rows = [r for r in rows if r[0] not in (601, 602)]                          # gap after the touch
    rows = [r if r[0] != 603 else (603, 12.0, 12.0, 12.0, 12.0, 1000, 12.0) for r in rows]
    d = mkday(rows)
    assert R.walk(d, 585, 11.01, -1, "L")[:3] == (11.01, 600, "stop_level")
    assert R.walk(d, 585, 11.01, -1, "N")[:3] == (12.0, 603, "stop_next")
    d = mkday([r if r[0] != 600 else (600, 11.2, 11.3, 11.0, 11.0, 1000, 11.0) for r in flat(585, 960, 10.0)])
    assert R.walk(d, 585, 11.01, -1, "L")[:3] == (11.2, 600, "stop_open")
    d = mkday([(585, 10.0, 11.05, 10.0, 10.0, 1000, 10.0)] + flat(586, 960, 10.0))
    assert R.walk(d, 585, 11.01, -1, "L")[:3] == (11.01, 585, "stop_level")     # the entry bar is judged


def test_reading_n_without_a_next_bar_is_halted_close():
    d = mkday(flat(585, 900, 10.0) + [(900, 10.0, 11.5, 10.0, 10.2, 1000, 10.0)])
    px, m, why, last = R.walk(d, 585, 11.01, -1, "N")
    assert why == "halted_close" and last == 10.2


def test_halt_jumped_stop_exits_at_resume_open_in_both_readings():
    d = mkday(flat(585, 700, 10.0) + flat(707, 960, 12.0))
    for rd in ("L", "N"):
        assert R.walk(d, 585, 11.01, -1, rd)[:3] == (12.0, 707, "stop_open")
    hi = R.halt_info(d, 5)
    x = R.exit_for(d, mkev(), 585, 11.01, -1, "L", hi)
    assert x.on_resume is True
    d = mkday(flat(585, 700, 10.0) + flat(704, 960, 12.0))                       # 4 empty minutes
    assert R.walk(d, 585, 11.01, -1, "L")[:3] == (12.0, 704, "stop_open")


def test_last_judged_bar_is_1554_and_exit_is_first_bar_in_1555_window():
    rows = [r if r[0] != 955 else (955, 10.0, 12.0, 10.0, 10.0, 1000, 10.0) for r in flat(585, 960, 10.0)]
    assert R.walk(mkday(rows), 585, 11.01, -1, "L")[:3] == (10.0, 955, "exit_1555")
    rows = [r for r in flat(585, 960, 10.0) if r[0] not in (955, 956)]
    rows = [r if r[0] != 957 else (957, 9.5, 9.5, 9.5, 9.5, 1000, 9.5) for r in rows]
    assert R.walk(mkday(rows), 585, 11.01, -1, "L")[:3] == (9.5, 957, "exit_1555")
    rows = [r if r[0] != 954 else (954, 10.0, 12.0, 10.0, 10.0, 1000, 10.0) for r in flat(585, 960, 10.0)]
    assert R.walk(mkday(rows), 585, 11.01, -1, "L")[2] == "stop_level"


def test_longs_mirror():
    d = mkday([r if r[0] != 600 else (600, 10.0, 10.0, 8.9, 10.0, 1000, 10.0) for r in flat(585, 960, 10.0)])
    assert R.walk(d, 585, 8.99, +1, "L")[:3] == (8.99, 600, "stop_level")
    d = mkday(flat(585, 950, 10.0))
    px, d2, nights, how = R.halted_close_exit(mkev(opens=[np.nan] * 10), 8.99, 10.0, +1)
    assert px == 8.99 and how == "stress_no_bar"


def test_halted_into_the_close():
    d = mkday(flat(585, 955, 10.0))                                             # nothing 15:55-15:59
    assert R.halt_info(d).halted_close
    ev = mkev(opens=[np.nan, 9.0] + [10.0] * 8)
    x = R.exit_for(d, ev, 585, 11.01, -1, "L")
    assert (x.reason, x.px, x.date, x.nights, x.priced_by) == ("halted_close", 9.0, ev.nxt_dates[1], 2, "next_open")
    ev = mkev(opens=[np.nan] * 10)
    x = R.exit_for(d, ev, 585, 11.01, -1, "L")
    assert (x.px, x.date, x.nights, x.priced_by) == (11.01, ev.nxt_dates[0], 1, "stress_no_bar")
    ev = mkev(opens=[np.nan, 9.0] + [10.0] * 8, flags=[True] + [False] * 9)
    x = R.exit_for(d, ev, 585, 11.01, -1, "L")
    assert x.priced_by == "stress_split" and x.px == 11.01
    ev = mkev(d2="2025-06-27", nxt=[], opens=[], flags=[], next_session=None, nxt_reaches_cut=True)
    x = R.exit_for(mkday(flat(585, 955, 10.5), "2025-06-27"), ev, 585, 11.01, -1, "L")
    assert x.date == pd.Timestamp("2025-06-27") and x.nights == 0 and x.px == 11.01 and x.priced_by == "stress_cut"
    # reading N: the touch bar closes above the stop and nothing follows -> max(stop, last pre-halt close)
    d = mkday(flat(585, 900, 10.0) + [(900, 10.0, 11.6, 10.0, 11.4, 1000, 11.0)])
    x = R.exit_for(d, mkev(opens=[np.nan] * 10), 585, 11.01, -1, "N")
    assert x.reason == "halted_close" and x.px == 11.4 and x.priced_by == "stress_no_bar"


# ================================================================== half days
def test_half_day_bars_after_1300_are_ignored_and_registered_half_day_raises():
    d = mkday(flat(570, 775, 10.0) + flat(780, 960, 10.0), "2016-11-25")
    assert d.rth1 == 780 and R.halt_info(d).halted_close
    assert all(b.close_t <= 780 for b in R.bars5(d))
    with pytest.raises(SystemExit, match="half day"):
        R.assert_no_half_day([mkev(d2="2016-11-25")])


# ================================================================== costs, spreads
def test_side_costs_and_locate():
    assert float(R.side_cost(1.0, 0.005, 0.01, False)) == pytest.approx(0.0085)
    assert float(R.side_cost(10.0, 0.0025, 0.005, False)) == pytest.approx(0.0285)
    assert float(R.side_cost(10.0, 0.0025, 0.005, True)) == pytest.approx(0.0635)
    u = float(R.unit_net(10.0, 10.0, -1, 0.0, 0.0, False, 2))
    assert u == pytest.approx(-2 * 0.0085 - 0.01 * 10 * 3)
    us = float(R.unit_net(10.0, 10.0, -1, 0.0, 0.0, True, 0))
    assert us == pytest.approx(-2 * 0.0185 - 0.02 * 10)
    assert float(R.unit_net(10.0, 11.0, +1, 0.0, 0.0, False, 5)) == pytest.approx(1.0 - 0.017)   # no locate on a long


def test_marks_in_force_rule_and_median():
    vals, desc = R.parse_marks({"marks": {"09:45": {"quotes": {"A": [quote(D, "09:45", 10.0, 10.2)]}},
                                          "10:00": {"quotes": {"A": [quote(D, "10:00", 10.0, 10.1, sec_before=61)]}},
                                          "10:30": {"quotes": {"A": [quote(D, "10:30", 10.0, 9.9)]}},
                                          "11:00": {"quotes": {"A": [quote(D, "11:00", 10.0, 10.4)]}, "note": "asc"}}}, "A", D)
    assert vals["10:00"] is None and desc is False                               # 61 s before the mark: not in [m-60s, m]
    assert R.mark_value(vals) == pytest.approx(np.median([0.2 / 20.2, 0.4 / 20.4]))   # 10:30 crossed: dropped


def test_desc_and_asc_fallback_give_the_same_value():
    q = quote(D, "09:45", 10.0, 10.2)
    a, _ = R.parse_marks({"marks": {"09:45": {"quotes": {"A": [q]}}}}, "A", D)
    b, _ = R.parse_marks({"marks": {"09:45": {"quotes": {"A": [q]}, "note": "asc window, last kept"}}}, "A", D)
    assert R.mark_value(a) == R.mark_value(b)


def test_bucket_rule_twenty_and_priors():
    vals = {"lt5": [(0.01 * (i + 1), False) for i in range(19)], "5to20": [(0.001 * (i + 1), False) for i in range(20)]}
    out = R.bucket_spreads(vals)
    assert out["lt5"]["h50"] == 0.005 and out["lt5"]["h75"] == 0.01 and out["lt5"]["source"].startswith("priors")
    assert out["5to20"]["h50"] == pytest.approx(np.percentile([0.001 * (i + 1) for i in range(20)], 50))
    assert out["5to20"]["h75"] == pytest.approx(0.01525)                         # linear
    vals["lt5"].append((R.PRIOR_H50["lt5"], True))                               # a refused day at its prior counts toward n
    out = R.bucket_spreads(vals)
    assert out["lt5"]["n"] == 20 and out["lt5"]["refused_days_at_prior"] == 1 and out["lt5"]["source"] == "measured"


# ================================================================== size and statistics
def test_shares_and_cap():
    assert R.shares_at(10000.0, 1e6, 3.0) == 3333
    assert R.shares_at(20000.0, 1e6, 10.0) == 1000                             # cap 0.01 x $1M = $10k binds
    assert R.shares_at(9.99, 1e6, 3.33) == 3                                    # floor with the 1e-9 guard


def test_nstar_smallest_crossing_and_none():
    E, adv, u, ix = np.array([10.0]), np.array([1e12]), np.array([-1.0]), np.array([0])
    ns = R.solve_nstar(E, adv, u, ix)
    assert ns.n == 300000.0 and ns.crossed and ns.maxdd == 30000.0
    ns = R.solve_nstar(E, adv, np.array([-0.001]), ix)
    assert ns.n == 500000.0 and not ns.crossed


def test_nstar_non_monotone_maxdd_returns_first_crossing():
    # day 0 and day 2: losers capped at $20k (-1 a share at $1); day 1: an uncapped gainer (+0.5). Below the cap
    # maxDD = 1.5 N (crosses $30k at N = 20,000); above it the gainer eats into the two capped losses, so maxDD FALLS
    # (27.5k at 25k, 20k from 40k on): a bisection would answer $500,000, the scan answers $20,000.
    E, adv = np.array([1.0, 1.0, 1.0]), np.array([2e6, 1e12, 2e6])
    u, ix = np.array([-1.0, 0.5, -1.0]), np.array([0, 1, 2])

    def dd_at(N):
        return R.maxdd(R.daily_series(R.shares_at(N, adv, E), u, ix, 3))
    assert dd_at(19500) < 30000 and dd_at(20000) == 30000 and dd_at(25000) < 30000 and dd_at(500000) < 30000
    ns = R.solve_nstar(E, adv, u, ix)
    assert ns.n == 20000.0 and ns.crossed and ns.maxdd == 30000.0


def test_statistics():
    x = np.array([-100.0, 50.0, 0.0, 0.0])
    assert R.maxdd(x) == 100.0                                                  # the peak starts at $0
    assert R.roc30(x) == pytest.approx(30 * (-50 / R.YEARS) / 30000)
    assert R.YEARS == pytest.approx(8.994, abs=5e-4)
    y = np.array([0.0, 40000.0, -35000.0, 0.0])
    assert R.roc30(y) == pytest.approx(30 * (5000 / R.YEARS) / 35000)
    assert R.roc_uncapped(np.zeros(3)) is None
    z = np.array([1.0, 0.0, 2.0, 0.0])
    assert R.tstat(z) == pytest.approx(z.mean() / (z.std(ddof=1) / 2))
    assert R.sortino(np.array([1.0, -1.0, 0.0, 0.0])) == pytest.approx(0.0)
    assert R.pf([3.0, -1.0, -1.0]) == pytest.approx(1.5)


def test_years_positive_and_no_trade_year():
    sess = pd.bdate_range("2016-07-01", "2018-06-29")
    d = np.zeros(len(sess))
    d[0] = 5.0
    n, per = R.years_positive(d, sess, [sess[0]])
    assert n == 1 and per["2016-17"] == 5.0 and per["2017-18"] == 0.0


def test_count_gate_449_and_450():
    g = R.count_gate({"2016-17": 449})
    assert round(g["n_per_year"], 2) == 49.92 and not g["pass"]
    g = R.count_gate({"2016-17": 450})
    assert round(g["n_per_year"], 2) == 50.03 and g["pass"]
    assert "2017-18" in g["thin_years_under_25"] and "2016-17" not in g["thin_years_under_25"]
    assert not R.count_gate({"2016-17": 99})["n_ge_100"]


def test_verdict():
    allp = {k: True for k in range(1, 13)}
    assert R.verdict(allp) == "PASS"
    assert R.verdict({**allp, 4: False}) == "RESEARCH ROW"
    assert R.verdict({**allp, 4: False, 7: False}) == "FAIL"
    assert R.verdict({**allp, 3: False}) == "FAIL"


# ================================================================== the book
def test_episodes_inclusive_rsum_and_append():
    idx = pd.DatetimeIndex(["2016-07-01", "2016-07-03", "2016-07-05", "2016-07-06"])
    m = R.episode_mask(idx, [(pd.Timestamp("2016-07-03"), pd.Timestamp("2016-07-05"))])
    assert m.tolist() == [False, True, True, False]
    B = R.Book(idx, np.ones(4), np.ones(4), {}, np.zeros(4), m, [], [], m)
    sess = pd.DatetimeIndex(["2016-07-01", "2016-07-04", "2016-07-05"])
    ext, leg, bm, ll, ir, app = R.to_book(np.array([1.0, 2.0, 3.0]), sess, B)
    assert app == 1 and len(ext) == 5 and bm[ext.get_loc(pd.Timestamp("2016-07-04"))] == 0.0
    assert R.rsum(leg, ir) == 3.0
    assert R.rsum_ex3(np.array([5.0, 4.0, 3.0, 2.0, 1.0]), np.ones(5, bool)) == 3.0


def test_book_parity_rounds_to_the_printed_digits():
    assert R.book_parity({"roc": 93.8056, "sort": 3.81650}, (93.81, 3.817), "x")
    with pytest.raises(SystemExit, match="PARITY"):
        R.book_parity({"roc": 93.80, "sort": 3.816}, R.BOOK_FACTS, "#463")


# ================================================================== the null half
def _ctx(elig, uP=None, uW=None, E=None, n_days=5):
    n = len(elig)
    return R.NullCtx(keys=[(D, f"S{i}") for i in range(n)], elig=[np.asarray(e, bool) for e in elig],
                     uP=uP or [np.full(len(e), -1.0) for e in elig], uW=uW or [np.full(len(e), -0.5) for e in elig],
                     E=E or [np.full(len(e), 10.0) for e in elig], ixP=[np.zeros(len(e)) for e in elig],
                     ixW=[np.ones(len(e)) for e in elig], adv=np.full(n, 1e12), n_days=n_days,
                     inR_day=np.array([True, False, False, False, False]), omega_sha="x")


def test_null_attempt_cap_is_21():
    el = np.zeros(30, bool)
    el[7] = True
    ctx = _ctx([el])
    for seed in range(40):
        rng = np.random.default_rng(seed)
        perm = np.random.default_rng(seed).permutation(30)
        _a, info = R.draw_once(rng, ctx)
        pos = int(np.flatnonzero(perm == 7)[0])
        assert info["trades"] == (1 if pos < 21 else 0)


def test_same_bar_serves_p_and_w():
    els = [np.ones(6, bool)]
    u = [np.arange(1.0, 7.0)]
    ctx = _ctx(els, uP=u, uW=[x.copy() for x in u])
    ctx.ixW = ctx.ixP
    rng = np.random.default_rng(1)
    for _ in range(10):
        a, _i = R.draw_once(rng, ctx)
        assert a[0, 0] == a[1, 0] and a[0, 2] == a[1, 2]


def test_null_half_seed_and_blocked_equals_interleaved():
    els = [np.array([True, False, True, True]), np.array([False, True]), np.array([True] * 5)]
    u = [np.array([-1.0, 0, 2.0, -3.0]), np.array([0, 1.0]), np.array([1.0, -2.0, 3.0, -1.0, 0.5])]
    ctx = _ctx(els, uP=u, uW=[x * 0.5 for x in u])
    blocked, _ = R.null_half(ctx, n=6)
    rng_r2, rng_pm = np.random.default_rng(R.SEED_NULL_R2), np.random.default_rng(R.SEED_NULL_PM)
    inter = []
    for _ in range(6):
        rng_pm.random(17)                                                       # PMFAIL's half draws in between
        inter.append(R.draw_once(rng_r2, ctx)[0])
    assert np.array_equal(blocked, np.array(inter), equal_nan=True)
    assert R.SEED_NULL_R2 == 20261010 and R.SEED_NULL_PM == 20261006
    ctx2 = _ctx(els + [np.array([True])], uP=u + [np.array([5.0])], uW=[x * 0.5 for x in u] + [np.array([1.0])])
    assert not np.array_equal(R.null_half(ctx2, n=6)[0], blocked)               # RUNNER2's Omega moves only its own half


def test_family_summary_max_and_nan():
    rng = np.random.default_rng(0)
    a = rng.normal(size=(500, 4, 3))
    a[0, 2, 1] = np.nan
    s = R.family_summary(a)
    b = np.where(np.isnan(a), -np.inf, a)
    assert s["max4"]["roc30"]["p95"] == pytest.approx(np.percentile(b.max(axis=1)[:, 0], 95))
    assert s["runner2_max2"]["t"]["p97.5"] == pytest.approx(np.percentile(b[:, 2:].max(axis=1)[:, 1], 97.5))
    assert s["pmfail_max2"]["rsum"]["p50"] == pytest.approx(np.percentile(b[:, :2].max(axis=1)[:, 2], 50))
    assert s["nan_cells"] == 1
    assert s["notion_b_roc30"]["max4"] == pytest.approx(s["max4"]["roc30"]["p95"] - s["max4"]["roc30"]["p50"])


def write_null(path, omega_sha, harness_sha=None, seeds=None, draws=500, legacy=False):
    """null.json in the PMFAIL harness's schema (mode_null): omega.sha256, runner2_harness_sha256_lf, summary"""
    hs = harness_sha or R.sha256_lf(os.path.abspath(R.__file__))
    nl = {"seeds": seeds or {"pmfail": 20261006, "runner2": 20261010}, "draws": draws, "percentile_method": "linear",
          "summary": R.family_summary(np.random.default_rng(3).normal(size=(500, 4, 3)) * [1.0, 1.0, 1000.0])}
    if legacy:
        nl.update({"omega": {"runner2_sha256": omega_sha}, "harness": {"runner2_sha256_lf": hs}})
        nl["summary"]["r2_max2"] = nl["summary"].pop("runner2_max2")
    else:
        nl.update({"omega": {"n": 3, "sha256": omega_sha}, "runner2_harness": "runner2_r1_stageA.py",
                   "runner2_harness_sha256_lf": hs})
    data = json.dumps(nl).encode()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()


def test_read_null_refusals(tmp_path):
    p = str(tmp_path / "null.json")
    sha = write_null(p, "om")
    got = R.read_null(p, sha, "om")
    assert got["sha256"] == sha and got["summary"]["max4"]["roc30"]["p95"] is not None
    with pytest.raises(SystemExit, match="posted sha256"):
        R.read_null(p, "0" * 64, "om")
    with pytest.raises(SystemExit, match="different RUNNER2 Omega"):
        R.read_null(p, sha, "other")
    sha = write_null(p, "om", harness_sha="f" * 64)
    with pytest.raises(SystemExit, match="different RUNNER2 harness"):
        R.read_null(p, sha, "om")
    sha = write_null(p, "om", seeds={"pmfail": 20261006, "runner2": 20261006})
    with pytest.raises(SystemExit, match="seeds"):
        R.read_null(p, sha, "om")
    sha = write_null(p, "om", draws=499)
    with pytest.raises(SystemExit, match="draws"):
        R.read_null(p, sha, "om")
    with pytest.raises(SystemExit, match="--null-sha"):
        R.read_null(p, None, "om")
    sha = write_null(p, "om", legacy=True)                                     # the alternate key spelling also reads
    assert R.read_null(p, sha, "om")["sha256"] == sha


def test_null_ctx_exposes_the_pmfail_interface():
    ctx = _ctx([np.ones(3, bool), np.ones(2, bool)])
    assert ctx.omega_sha256 == "x" and ctx.omega_n == 2
    arr, info = R.null_half(ctx, n=4)
    assert arr.shape == (4, 2, 3) and set(info) == {"trades", "no_null_trade", "nstar_P", "nstar_W"}
    assert all(len(v) == 4 for v in info.values())


def test_probe_log_is_accepted_and_stamped(tmp_path):
    pu = Pull(tmp_path / "p")
    pu.recs = [r for r in pu.recs if r.get("kind") != "probe"]
    pu.bars("AAA", D, flat(570, 575, 10.0))
    sha = pu.manifest()
    log = tmp_path / "probe.txt"
    log.write_text("FB/META 1Day SAME MAPPING\nFB/META 5Min SAME MAPPING\nFB/META 1Min feed=sip SAME MAPPING\n")
    with pytest.raises(SystemExit, match="quotes"):
        R.Photograph(pu.root, sha, LIST_SHA, probe_log=str(log)).verify([("AAA", D)], [])
    log.write_text(log.read_text() + "FB/META /v2/stocks/quotes feed=sip SAME MAPPING\n")
    st = R.Photograph(pu.root, sha, LIST_SHA, probe_log=str(log)).verify([("AAA", D)], [])
    assert st["probe_log_sha256"] == hashlib.sha256(log.read_bytes()).hexdigest() and all(st["probe"].values())


# ================================================================== the synthetic world, end to end
def world(tmp_path, n_events=36):
    """36 registered day-2 events on a one-year calendar: winners, stop-outs, halted closes, no signals, a missing pull;
    plus a carry-over SSR session, a band-on-c(D0)-only row, two placebo rows, quotes on six registered rows"""
    sess = pd.bdate_range("2016-07-01", "2017-06-30")
    sess = sess[~sess.strftime("%Y-%m-%d").isin(R.EARLY_CLOSE_DATES)]
    pu = Pull(tmp_path / "alpaca_cache" / "disc_gapper")
    events, nonev = [], []
    kinds = ["win", "win", "stop", "win", "halted", "nosig", "win", "missing", "ssr"]
    for i in range(n_events):
        d2 = sess[5 + 6 * i]
        kind = kinds[i % len(kinds)]
        sym = f"S{i:02d}"
        c1 = 3.0 if i % 2 else 10.0
        f = c1 / 10.0
        if kind == "win":                                       # entry at the 09:45 open 10.40, then lower into 15:55
            rows = [r if r[0] != 585 else (585, 10.4, 10.4, 10.4, 10.4, 1000, 10.4)
                    for r in signal_rows(after=9.6 + 0.1 * (i % 5))]
        elif kind == "stop":
            rows = signal_rows()
            rows = [r if r[0] != 700 else (700, 10.0, 11.5, 10.0, 10.0, 1000, 10.0) for r in rows]
        elif kind == "halted":
            rows = signal_rows(end=955)
        elif kind == "nosig":
            rows = flat(240, 245, 10.5, v=100) + flat(570, 960, 11.0)
        elif kind == "ssr":                                     # SSR before B; the legal limit fills on the 09:46 high
            rows = [r if r[0] != 571 else (571, 11.0, 11.0, 8.5, 11.0, 1000, 11.0) for r in signal_rows()]
            rows = [r if r[0] != 586 else (586, 10.0, 10.6, 10.0, 10.0, 1000, 10.0) for r in rows]
        else:
            rows = None
        if rows is not None:
            rows = [(m, o * f, h * f, lo * f, c * f, v, vw * f) for m, o, h, lo, c, v, vw in rows]
        k = sess.get_loc(d2)
        nd = tuple(sess[k + 1:k + 11])
        flags = {"rev_s1": i % 7 == 0, "rev_cal": False, "rev_m": False, "delisted": i % 5 == 0, "inactive": False,
                 "ambiguous": False, "shortable": i % 3 == 0, "easy_to_borrow": None, "reused": i == 4}
        ev = mkev(sym, d2, c0=c1 / 1.5, c1=c1, adv=5e6 if i % 4 else 1.2e6, nxt=nd, opens=[c1] * len(nd),
                  flags=[False] * len(nd), next_session=nd[0] if nd else None, quotes=(i % 6 == 0),
                  pmfail_event=(i % 8 == 0))
        ev.flags = flags
        events.append(ev)
        if rows is None:
            pu.bars(sym, d2, status=500)
        else:
            pu.bars(sym, d2, rows)
        if ev.quotes:
            pu.marks(sym, d2, {mk: quote(f"{d2:%Y-%m-%d}", mk, 9.99 * f, 10.01 * f) for mk in R.MARKS})
    # a carry-over SSR session (not registered) and a band-only row
    d2 = sess[3]
    carry = mkev("CARRY", d2, c0=10.0, c1=14.0, nxt=tuple(sess[4:14]), registered=False, band_d0_only=False,
                 carry_kept=True, carry=True)
    carry.flags = {}
    band = mkev("BAND", sess[4], c0=10.0, c1=21.0, nxt=tuple(sess[5:15]), registered=False, band_d0_only=True)
    band.flags = {}
    for e in (carry, band):
        pu.bars(e.symbol, e.d2, [(m, o * e.c1 / 10, h * e.c1 / 10, lo * e.c1 / 10, c * e.c1 / 10, v, vw * e.c1 / 10)
                                  for m, o, h, lo, c, v, vw in signal_rows()])
    events += [carry, band]
    for j in range(2):
        e = mkev(f"PL{j}", sess[100 + j], c0=10.0, c1=10.0, nxt=tuple(sess[101 + j:111 + j]), registered=False,
                 band_d0_only=False, carry_kept=False)
        e.flags = {}
        pu.bars(e.symbol, e.d2, signal_rows(after=10.2))
        nonev.append(e)
    events.sort(key=lambda e: e.key)
    photo = R.Photograph(pu.root, pu.manifest(), LIST_SHA)
    photo.verify([(e.symbol, f"{e.d2:%Y-%m-%d}") for e in events + nonev],
                 [(e.symbol, f"{e.d2:%Y-%m-%d}") for e in events if e.registered and e.quotes])
    rng = np.random.default_rng(11)
    bidx = sess.union(pd.DatetimeIndex(["2016-07-03", "2016-07-10"]))
    inR = np.zeros(len(bidx), bool)
    inR[20:60] = True
    ddm = np.zeros(len(bidx), bool)
    ddm[100:130] = True
    mtm = rng.normal(150, 1500, len(bidx))
    res_c = rng.normal(0, 300, len(bidx))
    book = R.Book(bidx, mtm, mtm + res_c, {f"L{i}": rng.normal(0, 500, len(bidx)) * (rng.random(len(bidx)) > 0.5)
                                           for i in range(4)}, res_c, inR, [(bidx[20], bidx[59])], [(bidx[100], bidx[129])], ddm)
    vix = pd.Series(rng.uniform(10, 30, 400), index=pd.bdate_range("2016-05-01", periods=400))
    env = R.Env(events, nonev, sess, photo, book, vix, {"synthetic": True}, {"synthetic_inputs": True}, 0)
    return env


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))

    class NoSocket(socket.socket):
        def __init__(self, *a, **k):
            raise AssertionError("a socket was opened")
    monkeypatch.setattr(socket, "socket", NoSocket)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("socket")))
    return tmp_path


def test_counts_never_walk_an_exit_and_file_the_gate(home, monkeypatch, capsys):
    env = world(home)

    def boom(*a, **k):
        raise AssertionError("an exit was computed in the count step")
    for name in ("walk", "halted_close_exit", "exit_for", "unit_net"):
        monkeypatch.setattr(R, name, boom)
    payload, sigs = R.mode_counts(env)
    out = R.out_dir()
    assert os.path.exists(os.path.join(out, "counts.json")) and os.path.exists(os.path.join(out, "schedule.csv"))
    assert not any(f.startswith(("trades", "daily")) for f in os.listdir(out))
    g = payload["count_gate"]
    assert not g["pass"] and g["n"] == sum(s.status == "filled" for s in sigs)
    sg = payload["signals"]["by_year"]["2016-17"]
    assert sg["no_bars"] == 4 and sg["no_signal"] == 4 and sg["ssr_active"] == 4
    assert payload["halts"]["fills_with_empty_exit_window_by_year"]["2016-17"] == 4
    assert payload["ssr_by_year"]["2016-17"]["carry_over_removed"] == 1
    assert payload["spreads"]["buckets"]["lt5"]["source"].startswith("priors")
    assert payload["omega"]["n"] == g["n"]
    assert "COUNT GATE" in capsys.readouterr().out


def test_full_synthetic_pipeline(home):
    env = world(home)
    payload, sigs = R.mode_counts(env)
    pw = R.mode_power(env)
    assert set(pw["lines"]) == {"vol_c", "own_dd_30k"}
    for v in pw["lines"].values():
        assert set(v) == {"sd", "line_5pct", "line_80pct", "draws", "days", "years"}
    assert set(pw) == {"stamp", "coinflip", "k", "appended_days", "lines"}
    with pytest.raises(SystemExit, match="null"):
        R.mode_run(env, "0" * 64)
    nsha = write_null(os.path.join(R.pm_dir(), "null.json"), payload["omega"]["sha256"])
    st = R.mode_run(env, nsha)
    for k in ("cells", "n_star", "checks", "verdict", "reports", "halves", "per_year", "cost_curve", "capacity",
              "episodes_R", "corr", "book_add", "overlap", "pmfail_link", "info", "shas", "null", "power"):
        assert k in st, k
    assert st["verdict"] in ("FAIL", "RESEARCH ROW")                           # the count gate missed; the run went on
    assert st["checks"]["4"]["pass"] is False and st["checks"]["4"]["value"]["n"] == payload["count_gate"]["n"]
    assert 0 < st["checks"]["3"]["value"]["pf"] < float("inf")                  # winners and losers both present
    out = R.out_dir()
    for f in ("trades_P.csv", "trades_W.csv", "trades_OPEN2.csv", "trades_NOCROSS.csv", "trades_SSR.csv", "daily_P.csv",
              "daily_W.csv", "event_path.csv", "stage_a.json"):
        assert os.path.exists(os.path.join(out, f)), f
    tp = pd.read_csv(os.path.join(out, "trades_P.csv"))
    assert list(tp.columns) == R.TRADE_COLS and len(tp) == payload["count_gate"]["n"]
    assert (tp["exit_reason"] == "halted_close").sum() == 4
    assert st["reports"]["SSR_legal_fill"]["n"] == 4 and st["reports"]["placebo"]["n"] == 2
    ts = pd.read_csv(os.path.join(out, "trades_SSR.csv"))
    assert len(ts) == 4 and (ts["entry_time"] == "09:46").all()
    fil = json.load(open(os.path.join(out, "stage_a.json")))
    assert fil["null"]["sha256"] == nsha
    # the null context PMFAIL imports: Omega equals the filed one, candidate bars = 5m closes 09:45..14:00
    ctx = R.null_context(env)
    assert ctx.omega_sha256 == payload["omega"]["sha256"] == payload["omega_sha256"]
    assert ctx.omega_n == payload["omega"]["n"]
    assert all(len(e) == 52 for e in ctx.elig)                                  # 5m bars closing 09:45 .. 14:00
    arr, info = R.null_half(ctx, n=3)
    assert arr.shape == (3, 2, 3) and len(info["trades"]) == 3
    sc = pd.read_csv(os.path.join(out, "schedule.csv"))
    assert {"symbol", "d2"} <= set(sc.columns) and len(sc) == payload["omega"]["n"]


def test_run_refuses_when_filed_counts_were_edited(home):
    env = world(home)
    payload, _ = R.mode_counts(env)
    R.mode_power(env)
    p = os.path.join(R.out_dir(), "counts.json")
    d = json.load(open(p))
    d["count_gate"]["n"] += 1
    with open(p, "w") as f:
        json.dump(d, f)
    nsha = write_null(os.path.join(R.pm_dir(), "null.json"), payload["omega"]["sha256"])
    with pytest.raises(SystemExit, match="recomputed counts differ"):
        R.mode_run(env, nsha)


def test_power_refuses_without_counts_and_on_a_moved_stamp(home):
    env = world(home)
    with pytest.raises(SystemExit, match="not on file"):
        R.mode_power(env)
    R.mode_counts(env)
    env.input_stamp = {"moved": True}
    with pytest.raises(SystemExit, match="stamp differs"):
        R.mode_power(env)
