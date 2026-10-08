"""PMFAIL r1 Stage A harness (tools/pmfail_r1_stageA.py; docs/PREREG_pmfail_r1_2026-10-06.md with AMENDMENT 0).

SYNTHETIC data only: no intraday bar, quote, daily cache, book file or manifest under C:\\EdgeLog is read; EDGELOG_HOME
points at tmp_path; sockets are blocked around every mode. RUNNER2's per-draw routine is a stub module. Proved here:
  * the photograph: manifest sha, file sha, list sha, the FB/META probe, the cut, status / feed labels, page layouts;
    stamps (start-stamped UTC -> ET minute, EST and EDT), nonzero seconds / wrong date / conflicting duplicates refuse,
    v <= 0 and price <= 0 bars dropped and counted; the prereg LF sha check; write-once files; no network library;
  * PMH (04:00-09:29 only), 'traded above' strict, the first 5m close below in the 09:35..10:55 window, the 5m close from
    the last present 1m bar, no re-arm; the entry at the next present 1m open in [end, end + 5), the resume-bar skip at 5
    and 4 minutes, entry >= S1, S1 / S2 (ceil to the cent);
  * the stop walk under readings L and N, halt-jumped stops, the 15:55 exit, longs mirrored; Rule 201 (inclusive 0.9 P,
    regular prints only, the 04:00 reading) and the legal fill; halted into the close (next daily open, stress prices,
    booking, nights, flags); half days;
  * shares and the 1% cap, the N* scan (first crossing, also when maxDD(N) is not monotone), costs, locate, spreads (NBBO
    in force per second, bucket priors), the statistics, the count gate, the verdict;
  * the four-cell family null (PMFAIL's procedure, independence from RUNNER2's half, max / NaN / percentiles) and the
    null-file check RUNNER2 uses; the whole --counts / --overlap / --power / --null / --run chain on a synthetic world.
"""
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import types
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
sys.path.insert(0, TOOLS)
import pmfail_r1_stageA as PM  # noqa: E402

TS = pd.Timestamp
D0 = TS("2019-03-12")          # a Tuesday after the 2019 DST switch (EDT)
HALF = TS("2016-11-25")        # an EARLY_CLOSE_DATES half day
NAN = float("nan")


# ================================================================== builders
def mk(d):
    rows = []
    for m in sorted(d):
        t = d[m]
        o, h, l, c = t[:4]
        v = t[4] if len(t) > 4 else 1000.0
        rows.append((m, o, h, l, c, v, NAN))
    return pd.DataFrame(rows, columns=["m", "o", "h", "l", "c", "v", "vw"])


def flat(d, m0, m1, px, v=1000.0):
    for m in range(m0, m1):
        d[m] = (px, px, px, px, v)
    return d


def base(pmh=6.0):
    """P = 5.00; premarket at 5.50 with one 6.00 high (PMH); 09:30 trades to 6.20; the 09:35 bar closes 5.95 (< PMH):
    signal k = 1, end 09:40, entry 09:40 open 5.90, HOD 6.20 -> S1 6.21, S2 6.37; flat 5.90 to the close"""
    d = {}
    flat(d, 240, 570, 5.5)
    d[300] = (5.5, pmh, 5.5, 5.5)
    d[570] = (5.9, 6.2, 5.85, 6.1)
    flat(d, 571, 575, 6.1)
    flat(d, 575, 580, 5.95)
    flat(d, 580, 960, 5.9)
    return d


def sig(d, P=5.0, date=D0, k=5):
    return PM.pm_signal(PM.Day(mk(d), date), P, k)


def evns(date=D0, nxt=None, t_next="auto", P=5.0, adv=1e7, bucket="5to20", symbol="XYZ", role="reg", flags=None):
    date = TS(date)
    if nxt is None:
        days = pd.bdate_range(date + pd.Timedelta(days=1), periods=10)
        nxt = [(d, 6.0, False) for d in days]
    if t_next == "auto":
        t_next = nxt[0][0] if nxt else None
    return SimpleNamespace(symbol=symbol, date=date, ti=0, yi=PM.wf_year_index(date), wf_year=None, role=role,
                           bucket=bucket, P=P, adv=adv, O_day=P * 1.25, V_day=1e6, nxt=list(nxt), t_next=t_next,
                           nxt_sc=[bool(f) for _, _, f in nxt], nxt_m=[False for _ in nxt],
                           flags=flags or {}, F_prev=1.0, quotes=False)


# ================================================================== stamps, loader, photograph
def _rec(t, o=5.0, h=5.1, l=4.9, c=5.0, v=100, **kw):
    r = {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v, "n": 3, "vw": 5.0}
    r.update(kw)
    return r


def test_start_stamps_convert_to_et_minutes_in_est_and_edt():
    df, _ = PM.frame_1m([_rec("2019-03-08T14:30:00Z")], "2019-03-08")         # EST: 14:30Z = 09:30
    assert df["m"].tolist() == [570]
    df, _ = PM.frame_1m([_rec("2019-03-11T13:30:00Z"), _rec("2019-03-11T14:30:00Z")], "2019-03-11")   # EDT
    assert df["m"].tolist() == [570, 630]
    df, _ = PM.frame_1m([_rec("2019-03-11T08:00:00Z")], "2019-03-11")          # 04:00 ET, the first premarket minute
    assert df["m"].tolist() == [240]


def test_bad_stamps_refuse_and_bad_bars_are_dropped_and_counted():
    with pytest.raises(SystemExit, match="nonzero seconds"):
        PM.frame_1m([_rec("2019-03-11T13:30:05Z")], "2019-03-11")
    with pytest.raises(SystemExit, match="ET date"):
        PM.frame_1m([_rec("2019-03-12T13:30:00Z")], "2019-03-11")
    with pytest.raises(SystemExit, match="two different bars"):
        PM.frame_1m([_rec("2019-03-11T13:30:00Z"), _rec("2019-03-11T13:30:00Z", c=5.05)], "2019-03-11")
    with pytest.raises(SystemExit, match="on or after"):
        PM.frame_1m([_rec("2025-06-30T13:30:00Z")], "2025-06-30")
    recs = [_rec("2019-03-11T13:30:00Z"), _rec("2019-03-11T13:30:00Z"), _rec("2019-03-11T13:31:00Z", v=0),
            _rec("2019-03-11T13:32:00Z", l=0.0), _rec("2019-03-11T13:33:00Z")]
    df, dq = PM.frame_1m(recs, "2019-03-11")
    assert df["m"].tolist() == [570, 573]
    assert dq["dropped_dup_identical"] == 1 and dq["dropped_v_le_0"] == 1 and dq["dropped_price_le_0"] == 1


def _bars_page(sym, recs, multi=True):
    return [{"bars": {sym: recs} if multi else recs, "next_page_token": None}]


def write_photo(tmp, rows, probe=True, header_sha=PM.NAMEDAYS_SHA, extra_lines=()):
    """rows: (kind, symbol, date, page object or None, status, feed[, mark]) -> (manifest path, sha256 of its bytes)"""
    root = tmp / "pull"
    (root / "bars").mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"kind": "run_header", "list_sha256": header_sha, "spec": "synthetic"})]
    if probe:
        lines.append(json.dumps({"kind": "probe_fbmeta", "line": "FB/META 1Min feed=sip: SAME MAPPING"}))
        lines.append(json.dumps({"kind": "probe_fbmeta", "line": "FB/META quotes feed=sip: SAME MAPPING"}))
    for i, row in enumerate(rows):
        kind, sym, date, obj, status, feed = row[:6]
        o = {"kind": kind, "symbol": sym, "date": date, "status": status,
             "url": f"https://data.alpaca.markets/v2/stocks/bars?symbols={sym}&feed={feed}&timeframe=1Min"}
        if obj is not None:
            fn = f"bars/{sym}_{date}_{kind}_{i}.json"
            data = json.dumps(obj).encode("utf-8")
            (root / fn).write_bytes(data)
            o.update({"file": fn, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        if len(row) > 6:
            o["mark"] = row[6]
        lines.append(json.dumps(o))
    lines.extend(extra_lines)
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    p = root / "manifest.jsonl"
    p.write_bytes(raw)
    return str(p), hashlib.sha256(raw).hexdigest()


def test_photograph_verifies_and_serves_bars(tmp_path):
    recs = [_rec("2019-03-12T13:30:00Z", o=5.9, h=6.2, l=5.85, c=6.1), _rec("2019-03-12T08:00:00Z")]
    p, sha = write_photo(tmp_path, [("bars", "XYZ", "2019-03-12", _bars_page("XYZ", recs), 200, "sip"),
                                    ("bars", "ABC", "2019-03-12", {"bars": {}, "next_page_token": None}, 200, "sip"),
                                    ("bars", "IEXN", "2019-03-12", _bars_page("IEXN", recs, multi=False), 200, "iex"),
                                    ("bars", "DENY", "2019-03-12", None, 403, "sip"),
                                    ("bars", "FAIL", "2019-03-12", None, 500, "sip")])
    ph = PM.Photograph(p, sha)
    v = ph.verify()
    assert v["files_verified"] == 3 and v["status_by_kind"]["bars"] == {"200": 3, "403": 1, "other": 1}
    b = ph.bars("XYZ", "2019-03-12")
    assert b.status == "ok" and b.feed == "sip" and b.df["m"].tolist() == [240, 570]
    assert b.df.set_index("m").loc[570, "h"] == 6.2
    assert ph.bars("ABC", "2019-03-12").status == "empty"
    assert ph.bars("IEXN", "2019-03-12").feed == "iex"
    assert ph.bars("DENY", "2019-03-12").status == "refused"
    assert ph.bars("FAIL", "2019-03-12").status == "missing"
    assert ph.bars("NOPE", "2019-03-12").status == "missing"
    # the s.11 fallback: a refused sip request, then the iex answer for the same name-day -> served, labelled IEX
    p, sha = write_photo(tmp_path / "fb", [("bars", "XYZ", "2019-03-12", None, 403, "sip"),
                                          ("bars", "XYZ", "2019-03-12", _bars_page("XYZ", recs), 200, "iex")])
    ph = PM.Photograph(p, sha)
    ph.verify()
    b = ph.bars("XYZ", "2019-03-12")
    assert b.status == "ok" and b.feed == "iex"
    p, sha = write_photo(tmp_path / "two", [("bars", "XYZ", "2019-03-12", _bars_page("XYZ", recs), 200, "sip"),
                                           ("bars", "XYZ", "2019-03-12", _bars_page("XYZ", recs), 200, "iex")])
    with pytest.raises(SystemExit, match="several files or feeds"):
        PM.Photograph(p, sha).verify()


def test_photograph_refusals(tmp_path):
    recs = [_rec("2019-03-12T13:30:00Z")]
    p, sha = write_photo(tmp_path / "a", [("bars", "XYZ", "2019-03-12", _bars_page("XYZ", recs), 200, "sip")])
    with pytest.raises(SystemExit, match="MANAGER named"):
        PM.Photograph(p, "0" * 64).verify()
    with open(os.path.join(os.path.dirname(p), "bars", os.listdir(os.path.join(os.path.dirname(p), "bars"))[0]), "ab") as f:
        f.write(b" ")
    with pytest.raises(SystemExit, match="bytes|sha256"):
        PM.Photograph(p, sha).verify()
    p, sha = write_photo(tmp_path / "b", [("bars", "XYZ", "2019-03-12", _bars_page("XYZ", recs), 200, "sip")], header_sha="1" * 64)
    with pytest.raises(SystemExit, match="list sha256"):
        PM.Photograph(p, sha).verify()
    p, sha = write_photo(tmp_path / "c", [("bars", "XYZ", "2019-03-12", _bars_page("XYZ", recs), 200, "sip")], probe=False)
    with pytest.raises(SystemExit, match="SAME MAPPING"):
        PM.Photograph(p, sha).verify()
    log = tmp_path / "probe.txt"
    log.write_text("FB/META 1Min sip: SAME MAPPING\nFB/META quotes sip: SAME MAPPING\n", encoding="utf-8")
    assert PM.Photograph(p, sha, probe_log=str(log)).verify()["probe_log_sha256"]
    p, sha = write_photo(tmp_path / "d", [("bars", "XYZ", "2025-06-30", _bars_page("XYZ", recs), 200, "sip")])
    with pytest.raises(SystemExit, match="on or after"):
        PM.Photograph(p, sha).verify()
    p, sha = write_photo(tmp_path / "e", [("bars", "XYZ", "2019-03-12", {"weird": []}, 200, "sip")])
    ph = PM.Photograph(p, sha)
    ph.verify()
    with pytest.raises(SystemExit, match="unknown page layout"):
        ph.bars("XYZ", "2019-03-12")


def test_paged_quotes_are_digested_and_a_bars_file_must_be_pinned(tmp_path):
    """the wrapper's real layout: one manifest row per page, every row naming the request's one file (its own
    serialisation of the pages); bars: one row whose bytes / sha256 are the file's"""
    root = tmp_path / "pull"
    (root / "quotes").mkdir(parents=True)
    (root / "bars").mkdir()
    recs = [_rec("2019-03-12T13:30:00Z")]
    bars = json.dumps(_bars_page("XYZ", recs)[0]).encode()
    (root / "bars" / "XYZ.json").write_bytes(bars)
    pages = [{"quotes": {"XYZ": [{"t": "2019-03-12T13:40:00Z", "bp": 5.0, "ap": 5.02}]}, "next_page_token": "a"},
             {"quotes": {"XYZ": [{"t": "2019-03-12T13:41:00Z", "bp": 5.0, "ap": 5.04}]}, "next_page_token": None}]
    qfile = root / "quotes" / "XYZ_am.json"
    qfile.write_bytes(json.dumps(pages, indent=1).encode())
    url = "https://data.alpaca.markets/v2/stocks/quotes?symbols=XYZ&feed=sip&sort=asc"
    lines = [json.dumps({"kind": "run_header", "list_sha256": PM.NAMEDAYS_SHA}),
             json.dumps({"kind": "probe", "line": "1Min SAME MAPPING"}), json.dumps({"kind": "probe", "line": "quotes SAME MAPPING"}),
             json.dumps({"kind": "bars", "symbol": "XYZ", "date": "2019-03-12", "status": 200, "url": url.replace("quotes", "bars"),
                         "file": str(root / "bars" / "XYZ.json").replace("\\", "/"), "bytes": len(bars),
                         "sha256": hashlib.sha256(bars).hexdigest(), "pages": 1})]
    for i, pg in enumerate(pages):
        b = json.dumps(pg).encode()
        lines.append(json.dumps({"kind": "quotes_pmfail_am", "symbol": "XYZ", "date": "2019-03-12", "status": 200,
                                 "url": url + ("&page_token=a" if i else ""), "file": str(qfile).replace("\\", "/"),
                                 "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "pages": 2}))
    raw = ("\n".join(lines) + "\n").encode()
    (root / "manifest.jsonl").write_bytes(raw)
    ph = PM.Photograph(str(root / "manifest.jsonl"), hashlib.sha256(raw).hexdigest())
    v = ph.verify()
    assert v["files_pinned_by_row"] == 1 and v["files_unpinned_hashed"] == 1 and v["requests_with_several_page_rows"] == 1
    assert v["unpinned_digest"] == hashlib.sha256(f"{hashlib.sha256(qfile.read_bytes()).hexdigest()}  quotes/XYZ_am.json\n".encode()).hexdigest()
    q = ph.quotes("XYZ", "2019-03-12", "quotes_pmfail_am")
    assert q.status == "ok" and q.df["ap"].tolist() == [5.02, 5.04]
    # a changed quote file moves the digest, and a later step filed on the old one refuses
    inp = SimpleNamespace(shas={"x": "y"})
    stamp_old = PM.core_stamp(inp, ph)
    qfile.write_bytes(json.dumps(pages).encode())
    ph2 = PM.Photograph(str(root / "manifest.jsonl"), hashlib.sha256(raw).hexdigest())
    assert ph2.verify()["unpinned_digest"] != v["unpinned_digest"]
    od = tmp_path / "home" / "_anatomy_cache" / "disc_pmfail_r1"
    od.mkdir(parents=True)
    (od / "counts.json").write_text(json.dumps({"stamp": stamp_old}))
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv("EDGELOG_HOME", str(tmp_path / "home"))
        assert PM.require("counts", inp, ph)
        with pytest.raises(SystemExit, match="unpinned digest"):
            PM.require("counts", inp, ph2)
    finally:
        mp.undo()
    # a bars file of the right size but other bytes, and a bars file the row does not describe, both refuse
    (root / "bars" / "XYZ.json").write_bytes(bars.replace(b"5.1", b"5.2"))
    with pytest.raises(SystemExit, match="sha256 differs"):
        PM.Photograph(str(root / "manifest.jsonl"), hashlib.sha256(raw).hexdigest()).verify()
    (root / "bars" / "XYZ.json").write_bytes(bars + b"\n")
    with pytest.raises(SystemExit, match="does not pin"):
        PM.Photograph(str(root / "manifest.jsonl"), hashlib.sha256(raw).hexdigest()).verify()


def test_one_page_quotes_file_of_the_same_size_is_digested_not_pinned(tmp_path):
    """the real pull (NRXP 2021-07-23 close): the served empty page and the wrapper's re-serialisation are both 36
    bytes with different sha256 - a quotes file is never pinned by its row, whatever its size"""
    root = tmp_path / "pull"
    (root / "quotes").mkdir(parents=True)
    served = b'{"next_page_token":null,"quotes":{}}'
    saved = b'{"quotes": {"NRXP": []}, "pages": 1}'
    assert len(served) == len(saved) == 36
    qfile = root / "quotes" / "NRXP_close.json"
    qfile.write_bytes(saved)
    lines = [json.dumps({"kind": "run_header", "list_sha256": PM.NAMEDAYS_SHA}),
             json.dumps({"kind": "probe", "line": "1Min SAME MAPPING"}), json.dumps({"kind": "probe", "line": "quotes SAME MAPPING"}),
             json.dumps({"kind": "quotes_pmfail_close", "symbol": "NRXP", "date": "2021-07-23", "status": 200,
                         "url": "https://data.alpaca.markets/v2/stocks/quotes?symbols=NRXP&feed=sip&sort=asc",
                         "file": str(qfile).replace("\\", "/"), "bytes": len(served),
                         "sha256": hashlib.sha256(served).hexdigest(), "pages": 1})]
    raw = ("\n".join(lines) + "\n").encode()
    (root / "manifest.jsonl").write_bytes(raw)
    ph = PM.Photograph(str(root / "manifest.jsonl"), hashlib.sha256(raw).hexdigest())
    v = ph.verify()
    assert v["files_pinned_by_row"] == 0 and v["files_unpinned_hashed"] == 1
    assert ph.quotes("NRXP", "2021-07-23", "quotes_pmfail_close").status == "empty"


def test_runner2_marks_file_shared_by_marks(tmp_path):
    q = lambda bp, ap: {"quotes": {"XYZ": [{"t": "2019-03-12T13:45:00Z", "bp": bp, "ap": ap}]}}
    obj = {"09:45": q(5.0, 5.02), "10:00": q(5.1, 5.12)}
    p, sha = write_photo(tmp_path, [("quotes_runner2_mark", "XYZ", "2019-03-12", obj, 200, "sip", "09:45"),
                                    ("quotes_runner2_mark", "XYZ", "2019-03-12", obj, 200, "sip", "10:00")])
    ph = PM.Photograph(p, sha)
    ph.verify()
    mk_ = ph.marks("XYZ", "2019-03-12", marks=("09:45", "10:00", "10:30"))
    assert mk_["09:45"].df["bp"].tolist() == [5.0] and mk_["10:00"].df["ap"].tolist() == [5.12]
    assert mk_["10:30"].status == "missing"


def test_prereg_lf_sha_check(tmp_path, monkeypatch):
    for name in PM.PREREG_NAMES.values():
        (tmp_path / name).write_bytes(b"amended text\r\n")
    with pytest.raises(SystemExit, match="REFUSED"):
        PM.check_preregs(str(tmp_path))
    good = hashlib.sha256(b"amended text\n").hexdigest()
    monkeypatch.setattr(PM, "PREREG_SHA_LF", {k: good for k in PM.PREREG_NAMES})
    assert PM.check_preregs(str(tmp_path)) == {k: good for k in PM.PREREG_NAMES}


def test_write_once(tmp_path):
    p = str(tmp_path / "x" / "counts.json")
    PM.write_once(p, b"a")
    PM.write_once(p, b"a")
    with pytest.raises(SystemExit, match="never overwritten"):
        PM.write_once(p, b"b")
    assert open(p, "rb").read() == b"a"


def test_module_imports_no_network_library():
    code = ("import sys; sys.path.insert(0, %r); import pmfail_r1_stageA; "
            "print(sorted(m for m in ('requests', 'urllib3', 'augur_engine.alpaca_rate', 'augur_engine.alpaca_keys', "
            "'import_alpaca_stocks') if m in sys.modules))" % os.path.abspath(TOOLS))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"
    import ast
    names = set()
    for node in ast.walk(ast.parse(open(PM.__file__, encoding="utf-8").read())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names |= {a.name for a in node.names}
    bad = {n for n in names if re.search(r"(^|\.)(requests|urllib3|alpaca_rate|alpaca_keys|import_alpaca_stocks|socket)$", n)}
    assert not bad
    assert PM.EARLY_CLOSE_DATES and "2016-11-25" in PM.EARLY_CLOSE_DATES


# ================================================================== PMH and 'traded above'
def test_pmh_is_the_premarket_high_only():
    d = base()
    d[570] = (5.9, 9.0, 5.85, 6.1)                     # the 09:30 bar never enters PMH
    s = sig(d)
    assert s.pmh == 6.0 and s.k == 1 and s.S1 == pytest.approx(9.01)
    d2 = {m: v for m, v in base().items() if m >= 570}
    assert sig(d2).skip == "no_pmh"


def test_traded_above_is_strict_and_counts_inside_the_signal_bar():
    d = base()
    d[570] = (5.9, 6.0, 5.85, 5.95)
    flat(d, 571, 575, 5.95)
    assert sig(d).skip == "no_signal"                  # a high equal to PMH is not above
    d[570] = (5.9, 6.0001, 5.85, 5.95)
    s = sig(d)
    assert s.k == 1 and s.skip is None
    d = base()
    d[570] = (5.9, 5.9, 5.85, 5.9)
    flat(d, 571, 575, 5.9)
    d[576] = (5.95, 6.2, 5.95, 5.95)                   # above INSIDE the 09:35 bar: counts
    s = sig(d)
    assert s.k == 1 and s.end == 580
    d = base()
    d[570] = (5.9, 5.9, 5.85, 5.9)
    flat(d, 571, 575, 5.9)
    d[581] = (5.9, 6.2, 5.9, 5.9)                      # above only AFTER the 09:35 bar: the 09:40 bar signals
    s = sig(d)
    assert s.k == 2 and s.end == 585 and s.m_entry == 585


# ================================================================== the first 5m close below
def test_the_0930_bar_is_not_in_the_window():
    d = base()
    flat(d, 571, 575, 5.95)                            # the 09:30 5m bar traded above and closed below
    s = sig(d)
    assert s.k == 1 and s.end == 580 and s.m_entry == 580 and s.E == 5.9


def test_window_ends_with_the_1055_bar_and_equal_close_is_not_below():
    d = base()
    flat(d, 571, 655, 6.1)
    flat(d, 655, 660, 5.95)
    flat(d, 660, 960, 5.9)
    s = sig(d)
    assert s.k == 17 and s.end == 660
    d = base()
    flat(d, 571, 660, 6.1)
    flat(d, 660, 960, 5.9)                             # first close below is the 11:00 bar: outside
    assert sig(d).skip == "no_signal"
    d = base()
    flat(d, 575, 960, 6.0)                             # closes equal to PMH are not below
    assert sig(d).skip == "no_signal"


def test_5m_close_is_the_last_present_1m_close_and_empty_bars_do_not_exist():
    d = base()
    d[575], d[576], d[577], d[578] = (5.97,) * 4, (5.96,) * 4, (5.98,) * 4, (5.94,) * 4
    del d[579]
    b = PM.Day(mk(d), D0).bar5(1)
    assert b.c == 5.94 and b.last_m == 578 and b.o == 5.97
    for m in range(575, 579):
        d.pop(m)
    day = PM.Day(mk(d), D0)
    assert day.bar5(1) is None
    s = PM.pm_signal(day, 5.0)
    assert s.k == 2 and s.end == 585


def test_a_blocked_first_signal_never_rearms():
    d = base()
    for m in range(580, 585):
        d.pop(m)                                       # no bar in [09:40, 09:45): the bar at end + 5 is ignored
    s = sig(d)
    assert s.k == 1 and s.skip == "no_fill_bar"


# ================================================================== entry at the next 1m open
def test_entry_is_the_first_present_bar_within_five_minutes():
    d = base()
    d.pop(580)
    d.pop(581)
    d[582] = (5.88, 5.9, 5.85, 5.9)
    s = sig(d)
    assert s.skip is None and s.m_entry == 582 and s.E == 5.88


def test_resume_bar_entries_at_5_and_4_minutes():
    d = base()
    for m in range(576, 581):
        d.pop(m)                                       # 09:36..09:40 empty (5 minutes): the 09:41 bar resumes
    s = sig(d)
    assert s.k == 1 and s.m_entry == 581 and s.skip == "resume_bar"
    d = base()
    for m in range(576, 580):
        d.pop(m)                                       # 4 empty minutes: trades under the rule, skips at 4
    assert sig(d).skip is None and sig(d).m_entry == 580
    assert sig(d, k=4).skip == "resume_bar"
    d = base()
    for m in range(570, 578):
        d.pop(m)                                       # a run from 09:30 (delayed open) counts
    assert PM.Day(mk(d), D0).is_resume(578)


def test_entry_through_s1_and_s1_excludes_the_entry_bar():
    d = base()
    d[580] = (6.21, 6.3, 6.2, 6.25)
    s = sig(d)
    assert s.S1 == pytest.approx(6.21) and s.skip == "entry_ge_S1"
    d[580] = (6.2, 7.0, 6.2, 6.25)                     # the entry bar's own high never enters S1
    s = sig(d)
    assert s.skip is None and s.S1 == pytest.approx(6.21)


def test_neighbour_stop_rounds_up_to_the_cent():
    assert PM.ceil_cent(10.0 + 1.5 * (10.37 - 10.0)) == 10.56
    assert PM.ceil_cent(10.0 + 1.5 * (10.34 - 10.0)) == 10.51
    s = sig(base())
    assert s.S2 == 6.37 and s.hod == 6.2


# ================================================================== stop judging
def _walk(d, stop=6.21, side=-1, reading="L", m=580, date=D0, **kw):
    return PM.walk(PM.Day(mk(d), date), m, stop, side, reading, **kw)


def test_reading_L():
    d = base()
    d[600] = (6.3, 6.4, 6.3, 6.35)
    ex = _walk(d)
    assert (ex.px, ex.m, ex.reason) == (6.3, 600, "stop_open")
    d = base()
    d[600] = (5.9, 6.25, 5.9, 5.9)
    ex = _walk(d)
    assert (ex.px, ex.m, ex.reason) == (6.21, 600, "stop_level")
    d = base()
    d[580] = (5.9, 6.3, 5.8, 5.9)                      # the entry bar is judged too
    ex = _walk(d)
    assert (ex.m, ex.reason) == (580, "stop_level")


def test_reading_N():
    d = base()
    d[600] = (5.9, 6.25, 5.9, 5.9)
    for m in (601, 602, 603):
        d.pop(m)
    d[604] = (6.5, 6.6, 6.4, 6.5)
    ex = _walk(d, reading="N")
    assert (ex.px, ex.m, ex.reason) == (6.5, 604, "stop_next")
    d = base()
    d[954] = (5.9, 6.25, 5.9, 6.0)
    for m in range(955, 960):
        d.pop(m)
    ex = _walk(d, reading="N")
    assert ex.reason == "halted_close" and ex.px is None and ex.last_close == 6.0


def test_a_halt_jumped_stop_exits_at_the_resume_open_in_both_readings():
    for run in (7, 4):
        d = base()
        for m in range(601, 601 + run):
            d.pop(m)
        d[601 + run] = (6.5, 6.6, 6.4, 6.5)
        day = PM.Day(mk(d), D0)
        for rd in "LN":
            ex = PM.walk(day, 580, 6.21, -1, rd)
            assert (ex.px, ex.m, ex.reason) == (6.5, 601 + run, "stop_open")
        assert day.is_resume(601 + run, 5) == (run >= 5) and day.is_resume(601 + run, 4)


def test_the_1555_bar_is_the_exit_not_a_stop_and_longs_mirror():
    d = base()
    d[955] = (5.9, 6.3, 5.9, 6.0)
    ex = _walk(d)
    assert (ex.px, ex.m, ex.reason) == (5.9, 955, "exit_1555")
    d = base()
    d.pop(955)
    d.pop(956)
    d[957] = (5.8, 5.8, 5.8, 5.8)
    ex = _walk(d)
    assert (ex.px, ex.m, ex.reason) == (5.8, 957, "exit_1555")
    d = base()
    d[700] = (5.9, 5.9, 5.4, 5.6)
    ex = _walk(d, stop=5.5, side=+1)
    assert (ex.px, ex.m, ex.reason) == (5.5, 700, "stop_level")
    d[700] = (5.3, 5.9, 5.2, 5.6)
    ex = _walk(d, stop=5.5, side=+1)
    assert (ex.px, ex.reason) == (5.3, "stop_open")


# ================================================================== Rule 201
def test_ssr_same_day_threshold_is_inclusive():
    d = base()
    d[571] = (6.1, 6.1, 4.5, 6.1)                      # exactly 0.9 x P at 09:31
    assert sig(d, P=5.0).skip == "ssr_active"
    d[571] = (6.1, 6.1, 4.51, 6.1)
    assert sig(d, P=5.0).skip is None


def test_ssr_reads_regular_prints_through_the_signal_bar_only():
    d = base()
    d[580] = (5.9, 5.9, 4.4, 5.9)                      # after the signal bar's last minute: not active
    s = sig(d)
    assert s.skip is None and s.ssr_same is False
    d = base()
    d[300] = (5.5, 6.0, 4.4, 5.5)                      # a premarket low: not active; the 04:00 reading marks it
    s = sig(d)
    assert s.skip is None and s.ssr_same is False and s.ssr_0400 is True


def test_rule201_legal_fill():
    d = base()
    d[571] = (6.1, 6.1, 4.5, 6.1)
    d[580] = (5.9, 5.97, 5.85, 5.9)                    # high reaches limit + 0.01 = 5.97: filled at 5.96
    day = PM.Day(mk(d), D0)
    s = PM.pm_signal(day, 5.0)
    assert s.skip == "ssr_active" and s.c5 == 5.95
    t = PM.ssr_legal(day, evns(), s, "primary")
    assert t.E == pytest.approx(5.96) and t.reason == "exit_1555" and t.X == 5.9 and t.m_entry == 580
    tn = PM.ssr_legal(day, evns(), s, "neighbour")
    assert tn.stop == PM.ceil_cent(5.96 + 1.5 * (6.21 - 5.96))
    d[580] = (5.9, 5.965, 5.85, 5.9)
    assert PM.ssr_legal(PM.Day(mk(d), D0), evns(), s, "primary") is None
    d[580] = (5.9, 6.3, 5.85, 5.9)                     # the fill bar's own high counts against the stop
    t = PM.ssr_legal(PM.Day(mk(d), D0), evns(), s, "primary")
    assert t.X == pytest.approx(6.21) and t.m_exit == 580 and t.reason == "stop_level"


# ================================================================== the exit and halted into the close
def test_halted_close_exits_at_the_next_daily_open_with_nights_counted():
    days = list(pd.bdate_range("2019-03-13", periods=10))
    ev = evns(nxt=[(days[0], NAN, False), (days[1], 6.4, False)] + [(d, 6.0, False) for d in days[2:]])
    px, bd, nights, how = PM.halted_close_exit(ev, 6.21, 5.9, -1)
    assert (px, bd, nights, how) == (6.4, days[1], 2, "next_open")
    g, cp, cs, lp, ls = PM.unit_parts([5.9], [6.4], [-1], [nights], [0.0025], [0.005])
    assert lp[0] == pytest.approx(0.01 * 5.9 * 3) and ls[0] == pytest.approx(0.02 * 5.9 * 3)
    d = base()
    for m in range(955, 960):
        d.pop(m)
    t = PM.resolve(PM.Day(mk(d), D0), ev, 580, 5.9, 6.21, -1, "L")
    assert t.halted and t.book_date == days[1] and t.nights == 2 and t.X == 6.4


def test_halted_close_stress_prices_and_booking():
    days = list(pd.bdate_range("2019-03-13", periods=10))
    ev = evns(nxt=[(d, NAN, False) for d in days])
    assert PM.halted_close_exit(ev, 6.21, 5.9, -1) == (6.21, days[0], 1, "stress_no_bar")
    assert PM.halted_close_exit(ev, 6.21, 6.5, -1)[0] == 6.5
    assert PM.halted_close_exit(ev, 5.5, 5.9, +1)[0] == 5.5          # a long: min(stop, last close)
    ev = evns(nxt=[(days[0], NAN, True), (days[1], 6.4, False)] + [(d, 6.0, False) for d in days[2:]])
    assert PM.halted_close_exit(ev, 6.21, 5.9, -1) == (6.21, days[0], 1, "stress_flag")
    ev = evns(nxt=[(days[0], 6.4, True)] + [(d, 6.0, False) for d in days[1:]])
    assert PM.halted_close_exit(ev, 6.21, 5.9, -1)[3] == "stress_flag"          # a flag ON the exit session
    ev = evns(date="2025-06-25", nxt=[(TS("2025-06-26"), NAN, False), (TS("2025-06-27"), NAN, False)])
    assert PM.halted_close_exit(ev, 6.21, 5.9, -1) == (6.21, TS("2025-06-26"), 1, "stress_cut")
    ev = evns(date="2025-06-27", nxt=[], t_next=None)
    assert PM.halted_close_exit(ev, 6.21, 5.9, -1) == (6.21, TS("2025-06-27"), 0, "stress_cut")
    assert PM.halted_close_exit(ev, float("inf"), 5.9, -1)[0] == 5.9     # a stopless control: the last close


def test_half_day_session_ends_at_1300():
    d = base()
    d[774] = (5.9, 6.3, 5.9, 5.9)
    d[800] = (9.0, 99.0, 9.0, 9.0)                     # an extended-hours print: belongs to no session
    day = PM.Day(mk(d), HALF)
    assert day.rth1 == 780
    ex = PM.walk(day, 580, 6.21, -1, "L")
    assert (ex.m, ex.reason) == (774, "stop_level")
    d = base()
    d[775] = (5.9, 6.3, 5.9, 5.9)                      # 12:55 is the exit bar, not a stop
    ex = PM.walk(PM.Day(mk(d), HALF), 580, 6.21, -1, "L")
    assert (ex.px, ex.m, ex.reason) == (5.9, 775, "exit_1555")
    d = base()
    for m in range(775, 780):
        d.pop(m)
    day = PM.Day(mk(d), HALF)
    ex = PM.walk(day, 580, 6.21, -1, "L")
    assert ex.reason == "halted_close" and ex.last_close == 5.9
    assert day.halt_runs(5) == [(775, 5, None)] and day.exit_window_empty()


# ================================================================== size N* and the 1% cap
def test_shares_and_the_cap():
    assert PM.shares_at(10000, 1e6, 7.0) == math.floor(10000 / 7.0)
    assert PM.shares_at(20000, 1e6, 7.0) == math.floor(10000 / 7.0)        # 1% of $1M = $10k
    assert PM.shares_at(5000, 1e6, 3.0) == 1666
    assert PM.shares_at(10000, 1e6, 0.1) == 100000                           # floor with the 1e-9 guard


def test_nstar_is_the_smallest_grid_point_reaching_30k():
    E, adv, sess = np.full(3, 10.0), np.full(3, 1e9), np.arange(3)
    N, sh, dd = PM.solve_nstar(E, adv, np.full(3, -1.0), sess)               # DD = 3 x N / 10
    assert N == 100000 and dd == pytest.approx(30000) and (sh == 10000).all()
    N, sh, dd = PM.solve_nstar(E, adv, np.full(3, -0.001), sess)
    assert N == 500000 and dd < 30000


def test_nstar_scan_takes_the_first_crossing_when_dd_is_not_monotone():
    E = np.array([10.0, 10.0, 10.0])
    adv = np.array([1e6, 1e9, 1e6])                    # days 0 and 2 capped at $10k notional
    unit = np.array([-16.0, 0.1, -16.0])
    sess = np.arange(3)
    dds = []
    for N in PM.GRID:
        sh = PM.shares_at(N, adv, E)
        dds.append(PM.maxdd_of(np.bincount(sess, weights=sh * unit, minlength=3)))
    dds = np.array(dds)
    first = PM.GRID[np.flatnonzero(dds >= 30000)[0]]
    assert first == 9500 and (dds[PM.GRID > 200000] < 30000).all()          # rises, then falls back under
    N, sh, dd = PM.solve_nstar(E, adv, unit, sess)
    assert N == first


# ================================================================== costs, locate, spreads
def test_side_cost_examples():
    assert PM.side_cost(1.0, 0.005) == pytest.approx(0.0085)
    assert PM.side_cost(10.0, 0.0025) == pytest.approx(0.0285)
    assert PM.side_cost(10.0, 0.005, stress=True) == pytest.approx(0.0635)


def test_locate_on_shorts_only_and_per_night():
    g, cp, cs, lp, ls = PM.unit_parts([10.0, 10.0], [9.0, 11.0], [-1, +1], [2, 0], [0.0025] * 2, [0.005] * 2)
    assert g.tolist() == [1.0, 1.0]
    assert lp.tolist() == pytest.approx([0.3, 0.0]) and ls.tolist() == pytest.approx([0.6, 0.0])
    assert cp[0] == pytest.approx(0.0285 + (0.0225 + 0.0035))


def test_spread_is_the_nbbo_in_force_each_second():
    t0 = PM.et_ns(D0, 9, 40, 0)
    s = 1_000_000_000
    q = PM.frame_quotes([{"t": TS(t0 - 5 * s, tz="UTC").isoformat(), "bp": 9.98, "ap": 10.02},
                         {"t": TS(t0 + 10 * s + s // 2, tz="UTC").isoformat(), "bp": 9.9, "ap": 10.1},
                         {"t": TS(t0 + 20 * s, tz="UTC").isoformat(), "bp": 0.0, "ap": 10.1}])
    v = PM.spread_window(q, D0, (9, 40, 0), (9, 40, 30))
    assert v == pytest.approx(0.002)                   # 11 seconds at 0.002, 9 at 0.01, 11 invalid (bid 0)
    q2 = PM.frame_quotes([{"t": TS(t0 + 5 * s, tz="UTC").isoformat(), "bp": 9.9, "ap": 10.1}])
    assert PM.spread_window(q2, D0, (9, 40, 0), (9, 40, 30)) == pytest.approx(0.01)   # seconds before it skipped
    tie = PM.frame_quotes([{"t": TS(t0, tz="UTC").isoformat(), "bp": 9.0, "ap": 11.0},
                           {"t": TS(t0, tz="UTC").isoformat(), "bp": 9.99, "ap": 10.01}])
    assert PM.spread_window(tie, D0, (9, 40, 0), (9, 40, 0)) == pytest.approx(0.001)  # ties: the served order
    assert PM.spread_window(q, D0, (9, 39, 0), (9, 39, 10)) is None


def test_bucket_spreads_priors_and_refused_days():
    out = PM.bucket_spreads({"lt5": [0.01] * 19}, {})
    assert out["lt5"]["source"] == "priors" and out["lt5"]["h50"] == 0.005 and out["lt5"]["h75"] == 0.01
    assert out["5to20"]["h50"] == 0.0025 and out["5to20"]["h75"] == 0.005
    vals = list(np.linspace(0.001, 0.02, 20))
    out = PM.bucket_spreads({"lt5": vals}, {})
    assert out["lt5"]["source"] == "quotes" and out["lt5"]["h50"] == pytest.approx(np.percentile(vals, 50))
    assert out["lt5"]["h75"] == pytest.approx(np.percentile(vals, 75))
    out = PM.bucket_spreads({"lt5": [0.01] * 19}, {"lt5": 1})                  # the refused day counts toward n
    assert out["lt5"]["source"] == "quotes" and out["lt5"]["n"] == 20 and out["lt5"]["refused_take_prior"] == 1


# ================================================================== statistics
def test_roc_t_sortino_pf_and_the_zero_peak():
    d = np.zeros(10)
    d[0], d[5] = -100.0, 1000.0
    st = PM.series_stats(d, np.zeros(10, bool))
    assert st["maxdd"] == 100.0                        # the peak starts at $0: a first-day loss counts
    assert st["roc30"] == pytest.approx(30 * (900 / PM.YEARS) / 30000)
    assert st["t"] == pytest.approx(d.mean() / d.std(ddof=1) * math.sqrt(10))
    assert st["sortino"] == pytest.approx(d.mean() / math.sqrt(np.mean(np.minimum(d, 0) ** 2)) * math.sqrt(252))
    assert PM.YEARS == pytest.approx(8.9938, abs=1e-4)
    assert PM.pf_of([10, -5, 5]) == 3.0
    big = np.zeros(10)
    big[3] = -40000.0
    assert PM.series_stats(big, np.zeros(10, bool))["roc30"] == pytest.approx(30 * (-40000 / PM.YEARS) / 40000)


def test_r_sum_and_without_its_3_best_days():
    d = np.array([5.0, -1.0, 3.0, 10.0, 2.0, 7.0])
    inR = np.array([True, True, True, True, True, False])
    s, ex3 = PM.r_sums(d, inR, n_r=5)
    assert s == 19.0 and ex3 == 1.0
    s, ex3 = PM.r_sums(d, inR)                         # padded to 762 R days with zeros
    assert s == 19.0 and ex3 == pytest.approx(19.0 - 10 - 5 - 3)


def test_scale_free_at_5k_and_years_positive():
    E, unit, sess = np.array([10.0, 10.0]), np.array([-1.0, 2.0]), np.array([0, 1])
    assert PM.scale_free(E, unit, sess, 3) == pytest.approx(30 * (500 / PM.YEARS) / 500)
    wf = pd.bdate_range("2016-07-01", "2025-06-27")
    d = np.zeros(len(wf))
    d[0] = 10.0                                        # 2016-17 positive
    d[wf.get_loc(TS("2018-07-02"))] = -5.0             # 2018-19 negative
    pos, net, trades = PM.years_positive(d, wf, [TS("2016-07-01"), TS("2018-07-02")])
    assert pos == 1 and trades["2017-18"] == 0 and net["2016-17"] == 10.0


def test_count_gate_is_the_nine_year_mean():
    per = {y: 50 for y in PM.WF_YEARS}
    per[PM.WF_YEARS[0]] = 49                           # n = 449: 49.92 a year
    g = PM.count_gate(per)
    assert g["n"] == 449 and round(g["n_per_year"], 2) == 49.92 and not g["pass"]
    per[PM.WF_YEARS[0]] = 50                           # n = 450: 50.03
    g = PM.count_gate(per)
    assert round(g["n_per_year"], 2) == 50.03 and g["pass"] and g["thin_years_under_25"] == []
    per = {y: 0 for y in PM.WF_YEARS}
    per[PM.WF_YEARS[4]] = 500
    g = PM.count_gate(per)
    assert g["pass"] and len(g["thin_years_under_25"]) == 8
    assert not PM.count_gate({PM.WF_YEARS[0]: 99})["n_ge_100"]


def test_verdict():
    bars = {f"{i}_x": True for i in range(1, 11)}
    bars["3_count"] = bars.pop("3_x")
    assert PM.verdict(bars, "3_count") == "PASS"
    assert PM.verdict({**bars, "3_count": False}, "3_count") == "RESEARCH ROW"
    assert PM.verdict({**bars, "3_count": False, "9_x": False}, "3_count") == "FAIL"
    assert PM.verdict({**bars, "9_x": False}, "3_count") == "FAIL"


# ================================================================== the family null
def test_null_candidates_drop_resume_ssr_and_entry_through_s1():
    ev = evns()
    cands = PM.null_candidates(PM.Day(mk(base()), D0), ev, 6.0)
    assert [c["k"] for c in cands] == list(range(1, 18))   # no failed-PMH condition: every window bar is eligible
    d = base()
    d[600] = (5.9, 5.9, 4.5, 5.9)
    assert [c["k"] for c in PM.null_candidates(PM.Day(mk(d), D0), ev, 6.0)] == list(range(1, 6))
    d = base()
    for m in range(586, 591):
        d.pop(m)
    ks = [c["k"] for c in PM.null_candidates(PM.Day(mk(d), D0), ev, 6.0)]
    assert 3 not in ks and 2 in ks and 4 in ks
    d = base()
    d[585] = (6.21, 6.21, 6.21, 6.21)
    ks = [c["k"] for c in PM.null_candidates(PM.Day(mk(d), D0), ev, 6.0)]
    assert 2 not in ks
    c = PM.null_candidates(PM.Day(mk(base()), D0), ev, 6.0)[0]
    assert c["S1"] == pytest.approx(6.21) and c["S2"] == 6.37 and c["X1"] == 5.9


def _ctx(pool_sizes, n_y, cands=3):
    pools, start, cnt, E = {}, {}, {}, []
    off = 0
    for yi in range(len(PM.WF_YEARS)):
        pools[yi] = []
        for j in range(pool_sizes.get(yi, 0)):
            r = SimpleNamespace(name=(yi, j))
            pools[yi].append(r)
            start[id(r)], cnt[id(r)] = off, cands
            for k in range(cands):
                E.append(1000.0 * yi + 10.0 * j + k + 1.0)
                off += 1
    n = len(E)
    rng = np.random.default_rng(1)
    u = rng.normal(0, 1, n)
    bi = np.arange(n) % 50
    return SimpleNamespace(pools=pools, start=start, cnt=cnt, E=np.array(E), adv=np.full(n, 1e9), u=(u, -u),
                           bi=(bi, bi), n_y=n_y, n_cal=60, inR_cal=np.zeros(60, bool))


def test_pmfail_half_follows_the_registered_draw_and_counts_shortfalls(monkeypatch):
    ctx = _ctx({0: 5, 1: 2}, {0: 2, 1: 3})
    seen = []
    real = PM.solve_nstar

    def spy(E, adv, unit, sess, **kw):
        seen.append(np.asarray(E).copy())
        return real(E, adv, unit, sess, **kw)
    monkeypatch.setattr(PM, "solve_nstar", spy)
    out, info = PM.pm_null_half(ctx, n=3, seed=PM.SEED_PM)
    rng = np.random.default_rng(20261006)
    want = []
    for _ in range(3):
        g = []
        idx = np.sort(rng.choice(5, size=2, replace=False))
        for j in idx:
            g.append(10.0 * j + int(rng.integers(3)) + 1.0)
        for j in range(2):                              # year 1: pool 2 < n_y 3 -> take all, no choice call
            g.append(1000.0 + 10.0 * j + int(rng.integers(3)) + 1.0)
        want.append(g)
    assert [s.tolist() for s in seen[::2]] == want and [s.tolist() for s in seen[1::2]] == want
    assert info["shortfall"] == [1, 1, 1] and info["n_trades"] == [4, 4, 4]
    out10, _ = PM.pm_null_half(ctx, n=10, seed=PM.SEED_PM)
    out3, _ = PM.pm_null_half(ctx, n=3, seed=PM.SEED_PM)
    assert np.array_equal(out10[:3], out3, equal_nan=True)   # draw i never depends on later draws (block = interleave)


def test_null_summary_max_nan_and_percentiles():
    rng = np.random.default_rng(3)
    four = rng.normal(0, 1, (40, 4, 3))
    four[0, :, 0] = [np.nan, 1.0, 2.0, np.nan]
    four[1, :, 1] = np.nan
    summ, max4, pm2, r22 = PM.null_summary(four)
    assert max4[0, 0] == 2.0 and pm2[0, 0] == 1.0 and r22[0, 0] == 2.0
    assert max4[1, 1] == -np.inf and summ["nan_cells"] == 6
    f = np.where(np.isnan(four), -np.inf, four)
    assert summ["max4"]["rsum"]["p95"] == pytest.approx(np.percentile(f.max(axis=1)[:, 2], 95))
    assert summ["pmfail_max2"]["roc30"]["p97.5"] == pytest.approx(np.percentile(f[:, :2].max(axis=1)[:, 0], 97.5))
    assert summ["notion_b_roc30"]["max4"] == pytest.approx(summ["max4"]["roc30"]["p95"] - summ["max4"]["roc30"]["p50"])


# ================================================================== the book file loader
def test_load_book_parity_and_inclusive_episodes(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    p = PM.input_paths()
    idx = pd.bdate_range("2016-07-01", "2016-09-30")
    rng = np.random.default_rng(5)
    mtm = rng.normal(30, 200, len(idx))
    for k in ("book463_daily.csv", "line.csv", "residual_days.csv", "a2.json", "episodes.csv"):
        os.makedirs(os.path.dirname(p[k]), exist_ok=True)
    bk = pd.DataFrame({"date": idx, **{f"L{i}_mtm": mtm / 4 for i in range(4)}, "mtm": mtm})
    pd.concat([bk, pd.DataFrame({"date": [TS("2025-07-01")], **{f"L{i}_mtm": [9e9] for i in range(4)}, "mtm": [9e9]})]) \
        .to_csv(p["book463_daily.csv"], index=False)
    res = rng.normal(0, 50, len(idx))
    pd.DataFrame({"date": idx, "line": mtm + res, "book": mtm, "res_c": res}).to_csv(p["line.csv"], index=False)
    inR = np.zeros(len(idx), bool)
    inR[5:10] = True
    inR[20:22] = True
    pd.DataFrame({"date": idx, "in_R": inR}).to_csv(p["residual_days.csv"], index=False)
    json.dump({"line_episodes": [[str(idx[5].date()), str(idx[9].date())], [str(idx[20].date()), str(idx[21].date())]]},
              open(p["a2.json"], "w"))
    pd.DataFrame({"start": [idx[2].date()], "end": [idx[6].date()]}).to_csv(p["episodes.csv"], index=False)
    st = PM.r11_stats(mtm, idx)
    sl = PM.r11_stats(mtm + res, idx)
    monkeypatch.setattr(PM, "BOOK_FACTS", (st["roc"], st["sort"]))
    monkeypatch.setattr(PM, "LINE_FACTS", (sl["roc"], sl["sort"]))
    monkeypatch.setattr(PM, "R_DAYS", 7)
    monkeypatch.setattr(PM, "R_EPIS", 2)
    monkeypatch.setattr(PM, "DD_EPIS", 1)
    monkeypatch.setattr(PM, "DD_DAYS", 5)              # inclusive [start, end]: 5 sessions (half-open would be 4)
    b = PM.load_book()
    assert len(b.index) == len(idx) and int(b.inR.sum()) == 7 and int(b.dd_days.sum()) == 5
    monkeypatch.setattr(PM, "BOOK_FACTS", (st["roc"] + 0.01, st["sort"]))
    with pytest.raises(SystemExit, match="BOOK #463 parity"):
        PM.load_book()


# ================================================================== the daily context (pure on frames)
def _ctx_frames():
    days = pd.bdate_range("2019-01-02", periods=60)
    rows, srows = [], []
    for sym in ("AAA", "BBB"):
        for i, d in enumerate(days):
            if sym == "BBB" and i == 50:
                continue                                       # BBB has no bar on session 50
            px = 1.0 if (sym == "AAA" and i < 10) else 10.0  # AAA: a 1-for-10 reverse split on session 10
            if sym == "BBB":
                px = 4.0 + 0.01 * i
            fac = 0.1 if (sym == "AAA" and i < 10) else 1.0    # F = raw / split-adjusted
            rows.append((sym, d, px, px * 0.98, px, 200_000.0 + i))
            srows.append((sym, d, px / fac, px / fac))
    raw = pd.DataFrame(rows, columns=["symbol", "date", "o", "l", "c", "v"])
    split = pd.DataFrame(srows, columns=["symbol", "date", "o", "c"])
    T = len(days)
    syms_full = ["AAA", "BBB", "ZZZ"]
    masks = {k: np.zeros((T, 3), bool) for k in ("S1", "CAL", "M", "s3p", "s3v")}
    masks["S1"][10, 0] = True
    masks["M"][45, 1] = True                                   # a test-M flag on BBB, session 45
    masks["s3p"][40, 0] = True
    calrev = np.zeros((T, 3), bool)
    assets = pd.DataFrame({"symbol": ["AAA", "BBB", "BBB"], "status": ["active", "active", "inactive"],
                           "shortable": ["True", "True", "False"]})
    return days, raw, split, syms_full, masks, calrev, assets


def test_build_context_reads_prior_sessions_and_flags():
    days, raw, split, syms_full, masks, calrev, assets = _ctx_frames()
    last_bar = {"AAA": TS("2026-06-30"), "BBB": TS("2024-01-05")}
    evs, fctx = PM.build_context(raw, split, days, syms_full, masks, calrev, last_bar, assets,
                                 [(40, "AAA"), (44, "BBB"), (5, "BBB")], ["reg", "reg", "nonevent"])
    a, b, c = evs
    assert a.P == 10.0 and a.bucket == "5to20" and b.bucket == "lt5"
    want_adv = float(np.mean([10.0 * (200_000.0 + i) for i in range(20, 40)]))
    assert a.adv == pytest.approx(want_adv) and math.isnan(c.adv)              # fewer than 20 prior sessions
    assert a.flags["revsplit60"] and a.flags["rs_sources"] == {"s1": True, "cal": False, "m": False}
    assert a.flags["s3p"] and not a.flags["delisted"] and b.flags["delisted"]
    assert a.flags["shortable_active"] is True and not a.flags["reused"]
    assert b.flags["mixed"] and b.flags["shortable_active"] is None and b.flags["reused"]
    assert [x[0] for x in b.nxt] == list(days[45:55]) and b.t_next == days[45]
    assert math.isnan(b.nxt[5][1]) and b.nxt[0][2] is True                  # no bar on session 50; the M flag on 45
    assert a.F_prev == 1.0 and fctx["F"][5, 0] == pytest.approx(0.1)
    masks["S1"][10, 0] = False
    with pytest.raises(SystemExit, match="S1"):
        PM.build_context(raw, split, days, syms_full, masks, calrev, last_bar, assets, [(40, "AAA")], ["reg"])


def test_lowfloat_buckets_rebase_by_the_split_factor(tmp_path):
    days, raw, split, syms_full, masks, calrev, assets = _ctx_frames()
    evs, fctx = PM.build_context(raw, split, days, syms_full, masks, calrev, {}, assets,
                                 [(40, "AAA"), (44, "BBB")], ["reg", "reg"])
    af = tmp_path / "asfiled.csv"
    pd.DataFrame({"cik": ["0000000001", "0000000001", "0000000001"], "symbols": ["AAA", "AAA", "AAA"],
                  "concept": ["dei:EntityCommonStockSharesOutstanding", "dei:EntityCommonStockSharesOutstanding",
                              "us-gaap:CommonStockSharesOutstanding"],
                  "unit": "shares", "val": ["150000000", "999", "1"], "start": "", "end": "", "accn": "", "fy": "", "fp": "",
                  "form": "10-Q", "filed": ["2019-01-04", "2019-03-29", "2019-01-07"], "frame": ""}).to_csv(af, index=False)
    fr = tmp_path / "frames.csv"
    pd.DataFrame({"concept": ["us-gaap:CommonStockSharesOutstanding"], "frame": [""], "kind": ["instant"], "cik": ["2"],
                  "entity": ["B"], "start": [""], "end": [""], "val": ["30000000"], "accn": [""], "form": ["10-K"],
                  "filed": ["2018-12-03"], "ticker_now": ["BBB"]}).to_csv(fr, index=False)
    info = PM.lowfloat_buckets(evs, str(af), str(fr), fctx)
    # AAA: dei 150M filed 2019-01-04 (before the 1-for-10 split): 150M x F(filed) 0.1 / F(t) 1.0 = 15M -> under 20M;
    # the later filing (2019-03-29, after t) and the us-gaap fact (dei first) are never read
    assert evs[0].flags["lowfloat"] == "lt20m"
    assert evs[1].flags["lowfloat"] == "ge20m" and info["not_rebased"] == 1     # frames by ticker_now; filed before the cache


def test_read_listed_cuts_and_filters_the_parquet(tmp_path):
    p = tmp_path / "daily.parquet"
    df = pd.DataFrame({"symbol": ["AAA", "BBB", "AAA", "NA"], "date": pd.to_datetime(["2025-06-27", "2025-06-27", "2025-06-30", "2025-06-27"]),
                       "o": [1.0, 2.0, 3.0, 4.0], "c": [1.0, 2.0, 3.0, 4.0]})
    df.to_parquet(p, index=False)
    got = PM.read_listed(str(p), ["symbol", "date", "o"], ["AAA", "NA"])
    assert sorted(got["symbol"]) == ["AAA", "NA"] and got["date"].max() < PM.CUT
    assert PM.last_bar_dates(str(p), ["AAA", "BBB"]) == {"AAA": TS("2025-06-30"), "BBB": TS("2025-06-27")}


# ================================================================== the whole chain on a synthetic world
def gen_day(rng, P, halt=False):
    d = {}
    px = P * 1.22
    for m in range(240, 570):
        if rng.random() < 0.5:
            c = px * (1 + rng.normal(0, 0.004))
            d[m] = (px, max(px, c) * 1.002, min(px, c) * 0.998, c, float(rng.integers(100, 3000)))
            px = c
    pre_h = max(v[1] for v in d.values()) if d else P * 1.3
    px = pre_h * (1.0 + rng.uniform(-0.01, 0.03))
    drift = rng.normal(-0.0004, 0.0008)
    hs = int(rng.integers(600, 900)) if halt else -1
    for m in range(570, 960):
        if hs <= m < hs + 7 or rng.random() < 0.06:
            continue
        c = px * (1 + drift + rng.normal(0, 0.004))
        d[m] = (px, max(px, c) * (1 + abs(rng.normal(0, 0.002))), min(px, c) * (1 - abs(rng.normal(0, 0.002))), c,
                float(rng.integers(500, 20000)))
        px = c
    return mk(d)


class FakePhoto:
    manifest_sha256 = "f" * 64

    def __init__(self, bars, quotes):
        self.b, self.q = bars, quotes

    def bars(self, sym, date):
        df = self.b.get((sym, TS(date)))
        if df is None:
            return PM.Bars1m(status="missing", feed=None, df=None, dq=None)
        return PM.Bars1m(status="ok" if len(df) else "empty", feed="sip", df=df,
                         dq={"dropped_v_le_0": 0, "dropped_price_le_0": 0, "dropped_dup_identical": 0,
                             "dropped_outside_0400_1559": 0})

    def quotes(self, sym, date, kind="quotes_pmfail_am"):
        df = self.q.get((sym, TS(date), kind))
        if df is None:
            return PM.Quotes(status="refused", feed=None, df=None)
        return PM.Quotes(status="ok", feed="sip", df=df)

    def stamp(self):
        return {"manifest_sha256": self.manifest_sha256, "synthetic": True}


def make_world(seed=11, per_year=6):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2016-05-02", "2025-06-27")
    wf = days[(days >= PM.WF0) & (days <= PM.WF1)]
    evs, bars, quotes = [], {}, {}
    for yi in range(9):
        yd = wf[(wf >= TS(2016 + yi, 7, 1)) & (wf <= TS(2017 + yi, 6, 30))]
        picks = list(np.linspace(5, len(yd) - 15, per_year + 2).astype(int))
        for j, pi in enumerate(picks):
            t = yd[pi]
            ti = int(days.get_loc(t))
            role = "reg" if j < per_year else ("nonevent" if j == per_year else ("carry" if yi < 2 else "reg"))
            P = float(rng.uniform(1.5, 15.0))
            sym = f"S{yi}{j}"
            nx = [(days[u], P * 1.2 if not (yi == 0 and j == 0) else NAN, False) for u in range(ti + 1, min(ti + 11, len(days)))]
            ev = SimpleNamespace(symbol=sym, date=t, ti=ti, yi=yi, wf_year=PM.WF_YEARS[yi], role=role,
                                 bucket="lt5" if P < 5 else "5to20", P=P, adv=float(rng.uniform(2e6, 6e7)),
                                 O_day=P * 1.25, V_day=1e6, nxt=nx, t_next=days[ti + 1],
                                 nxt_sc=[False] * len(nx), nxt_m=[False] * len(nx),
                                 flags={"revsplit60": j % 5 == 0, "rs_sources": {"s1": j % 5 == 0, "cal": False, "m": False},
                                        "delisted": j % 4 == 0, "inactive": j % 4 == 0, "mixed": False,
                                        "shortable_active": (None if j % 4 == 0 else j % 2 == 0), "reused": j % 6 == 0,
                                        "s3p": j % 7 == 0, "s3v": False, "lowfloat": ("lt20m", "ge20m", "unknown")[j % 3]},
                                 F_prev=1.0, quotes=(role == "reg" and j < 3))
            evs.append(ev)
            bars[(sym, t)] = gen_day(rng, P, halt=(j == 2))
            if role == "reg" and j == 1 and yi in (1, 2, 3):
                d = {m: tuple(x * P / 5.0 for x in v[:4]) + (v[4] if len(v) > 4 else 1000.0,) for m, v in base().items()}
                if yi == 1:
                    d[571] = d[571][:2] + (0.85 * P,) + d[571][3:]          # SSR active at the signal
                    d[580] = d[580][:1] + (6.1 * P / 5.0,) + d[580][2:]      # the legal limit fills on 09:40
                else:
                    for m in range(955, 960):
                        d.pop(m)                                            # halted into the close
                    if yi == 3:
                        ev.nxt = [(x, NAN, False) for x, _o, _f in ev.nxt]   # no daily bar within 10 sessions
                bars[(sym, t)] = mk(d)
            if ev.quotes:
                t0 = PM.et_ns(t, 9, 35, 0)
                tt = t0 + np.sort(rng.integers(0, 90 * 60, 300)).astype(np.int64) * 1_000_000_000
                quotes[(sym, t, "quotes_pmfail_am")] = pd.DataFrame({"t_ns": tt, "bp": P * 0.997, "ap": P * 1.003})
                tc = PM.et_ns(t, 15, 50, 0) + np.arange(0, 600, 7, dtype=np.int64) * 1_000_000_000
                quotes[(sym, t, "quotes_pmfail_close")] = pd.DataFrame({"t_ns": tc, "bp": P * 0.996, "ap": P * 1.004})
    n = len(wf)
    mtm = rng.normal(40, 400, n)
    res = rng.normal(0, 100, n)
    inR = np.zeros(n, bool)
    inR[rng.choice(n, PM.R_DAYS, replace=False)] = True
    book = SimpleNamespace(index=wf, mtm=mtm, legs={f"L{i}_mtm": np.where(rng.random(n) < 0.5, mtm / 4, 0.0) for i in range(4)},
                           L=mtm + 0.264 * res, res_c=0.264 * res, inR=inR,
                           r_eps=[(wf[10], wf[30]), (wf[400], wf[420])], dd_eps=[(wf[50], wf[60])],
                           dd_days=np.asarray((wf >= wf[50]) & (wf <= wf[60])), years=(wf[-1] - wf[0]).days / 365.25)
    inp = SimpleNamespace(days=days, wf=wf, events=evs, builder_counts={"pmfail": {"synthetic": True}},
                          m_keeps_volume=False, shas={"daily_raw.parquet": "a" * 64}, preregs={}, book=book,
                          top20=None, top20_error="not computed (synthetic)")
    return inp, FakePhoto(bars, quotes)


def fake_r2(tmp, omega="ab" * 32, scale=1.0, tag="a"):
    p = tmp / f"fake_r2_{tag}.py"
    p.write_text(f"# fake RUNNER2 harness {tag}\n", encoding="utf-8")
    mod = types.ModuleType(f"fake_r2_{tag}")
    mod.__file__ = str(p)
    mod.null_context = lambda photo=None, book=None: SimpleNamespace(omega_sha256=omega, omega_n=40)

    def null_half(ctx, n=500, seed=20261010):
        assert seed == 20261010
        return np.random.default_rng(seed).normal(0, scale, (n, 2, 3)), {"nstar_P": [5000.0] * n}
    mod.null_half = null_half
    return mod, str(p)


def write_r2_counts(home, sched):
    d = os.path.join(home, "_anatomy_cache", "disc_runner2_r1")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "counts.json"), "w", encoding="utf-8") as f:
        json.dump({"omega_sha256": "ab" * 32}, f)
    rows = sched[["symbol", "date"]].head(3)
    rows.to_csv(os.path.join(d, "schedule.csv"), index=False)


def _no_sockets(mp):
    def boom(*a, **k):
        raise AssertionError("a socket was opened")
    mp.setattr(socket.socket, "connect", boom)
    mp.setattr(socket, "create_connection", boom)
    mp.setattr(socket, "getaddrinfo", boom)


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pmfail_chain")
    home = str(tmp / "home")
    inp, photo = make_world()
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv("EDGELOG_HOME", home)
        _no_sockets(mp)
        counts, sched = PM.mode_counts(inp, photo, verbose=False)
        write_r2_counts(home, sched)
        ov = PM.mode_overlap(inp, verbose=False)
        pw = PM.mode_power(inp, photo, verbose=False)
        shutil.copytree(home, str(tmp / "home_pre_null"))
        r2 = fake_r2(tmp)
        nj, draws = PM.mode_null(inp, photo, r2=r2, verbose=False)
        out = PM.mode_run(inp, photo, verbose=False)
    finally:
        mp.undo()
    return SimpleNamespace(tmp=tmp, home=home, inp=inp, photo=photo, counts=counts, sched=sched, overlap=ov, power=pw,
                           null=nj, draws=draws, run=out, r2=r2)


def _od(home):
    return os.path.join(home, "_anatomy_cache", "disc_pmfail_r1")


def test_chain_counts_schedule_and_gate(chain):
    c = chain.counts
    od = _od(chain.home)
    assert os.path.exists(os.path.join(od, "counts.json")) and os.path.exists(os.path.join(od, "schedule.csv"))
    n = sum(c["fills_by_year"].values())
    assert n == len(chain.sched) and n > 0
    assert c["count_gate"]["n"] == n and not c["count_gate"]["pass"]           # a synthetic world misses the gate
    reg = sum(1 for e in chain.inp.events if e.role == "reg")
    assert sum(sum(v.values()) for v in c["skips"].values()) + n == reg
    assert c["spreads"]["lt5"]["source"] == "priors"                           # < 20 quote days a bucket
    assert c["schedule_sha256"] == hashlib.sha256(open(os.path.join(od, "schedule.csv"), "rb").read()).hexdigest()
    assert sum(c["skips"]["ssr_active"].values()) >= 1
    assert sum(c["exit_window_empty_among_fills_by_year"].values()) >= 2
    assert c["halts"]["run_lengths"]["6-9"] >= 1


def test_chain_halted_close_trades_book_later_with_nights(chain):
    tr = pd.read_csv(os.path.join(_od(chain.home), "trades.csv"), keep_default_na=False)
    h = tr[(tr["halted_close"] == 1) & (tr["cell"] == "primary") & (tr["reading"] == "L")]
    assert set(h["priced_by"]) >= {"next_open", "stress_no_bar"}
    assert (pd.to_datetime(h["exit_date"]) > pd.to_datetime(h["date"])).all() and (h["nights"] >= 1).all()
    s = h[h["priced_by"] == "stress_no_bar"]
    assert (s["exit"] >= s["stop"] - 1e-9).all()                               # max(stop, last pre-halt close)
    rep = chain.run["reports"]
    assert rep["halted_close"]["n"] == len(h) and rep["bars_6_8_without_halted_close"]["n"] == rep["halted_close_without"]["n"]
    assert rep["SSR_legal_primary"]["n"] >= 1


def test_chain_run_continues_past_a_gate_miss_and_writes_its_files(chain):
    out = chain.run
    assert out["bars"]["3_count"] is False and out["verdict"] in ("RESEARCH ROW", "FAIL")
    od = _od(chain.home)
    for f in ("trades.csv", "daily.csv", "stage_a.json"):
        assert os.path.exists(os.path.join(od, f))
    tr = pd.read_csv(os.path.join(od, "trades.csv"), keep_default_na=False)
    assert set(tr["cell"]) == {"primary", "neighbour"} and set(tr["reading"]) == {"L", "N"}
    sh = tr.groupby(["symbol", "date", "cell"])["shares"].nunique()
    assert (sh == 1).all()                             # every reading re-prices the cell's N* shares
    advs = {(e.symbol, f"{e.date:%Y-%m-%d}"): e.adv for e in chain.inp.events}
    for c in ("primary", "neighbour"):
        nstar = out["cells"][c]["N_star"]
        t = tr[(tr["cell"] == c) & (tr["reading"] == "L")]
        want = [math.floor(min(nstar, 0.01 * advs[(s, d)]) / e + 1e-9) for s, d, e in zip(t["symbol"], t["date"], t["entry"])]
        assert t["shares"].tolist() == want and (t["shares"] >= 1).all()
    assert out["null_sha256"] == open(os.path.join(od, "null.sha256")).read().split()[0]
    st = out["cells"]["primary"]["stats"]["L"]
    assert out["bar_values"]["1_return"]["roc30"] == pytest.approx(st["roc30"])
    assert "OPENPRINT" in out["reports"] and "PMBREAK" in out["reports"] and "placebo_nonevent_primary" in out["reports"]
    assert out["reports"]["SSR_legal_primary"]["carry_over_days"] >= 0
    assert set(out["diagnostics"]) >= {"event_path_L", "cost_curve", "capacity", "book_add", "episodes", "correlation"}


def test_chain_power_prints_and_files_lines_only(chain, capsys):
    pw = chain.power
    assert set(pw) == {"n_trades", "coin_long", "coin_short", "lines", "stamp"}
    for v in pw["lines"].values():
        assert set(v) == {"k", "sd", "line_5pct", "line_80pct", "draws", "days", "years"}
    for f in ("coinflip_daily.csv", "book463_wf.csv", "cand_c.csv", "cand_30k.csv"):
        assert os.path.exists(os.path.join(_od(chain.home), f))
    pre = str(chain.tmp / "home_pre_null")
    home2 = str(chain.tmp / "home_power_again")
    shutil.copytree(pre, home2)
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv("EDGELOG_HOME", home2)
        capsys.readouterr()
        PM.mode_power(chain.inp, chain.photo, verbose=True)
        out = capsys.readouterr().out
    finally:
        mp.undo()
    assert "net" not in out.lower() and "pf " not in out.lower() and "roc@30k " not in out.lower().replace("roc@$30k", "")


def test_chain_null_is_independent_of_runner2s_half(chain):
    home2 = str(chain.tmp / "home_null_b")
    shutil.copytree(str(chain.tmp / "home_pre_null"), home2)
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv("EDGELOG_HOME", home2)
        nj2, draws2 = PM.mode_null(chain.inp, chain.photo, r2=fake_r2(chain.tmp, omega="cd" * 32, scale=9.0, tag="b"),
                                   verbose=False)
    finally:
        mp.undo()
    pm_cols = [c for c in chain.draws.columns if c.startswith("pm_")]
    assert pm_cols and chain.draws[pm_cols].equals(draws2[pm_cols])
    assert not chain.draws["r2_P_roc30"].equals(draws2["r2_P_roc30"])
    assert nj2["omega"]["sha256"] == "cd" * 32 and chain.null["seeds"] == {"pmfail": 20261006, "runner2": 20261010}
    four = np.stack([chain.draws[[f"{c}_{s}" for s in PM.STATS]].to_numpy() for c in ("pm_primary", "pm_neighbour", "r2_P", "r2_W")], axis=1)
    f = np.where(np.isnan(four), -np.inf, four)
    assert np.allclose(chain.draws[[f"max4_{s}" for s in PM.STATS]].to_numpy(), f.max(axis=1))


def test_null_refuses_without_runner2s_counts(chain):
    home2 = str(chain.tmp / "home_null_c")
    shutil.copytree(str(chain.tmp / "home_pre_null"), home2)
    shutil.rmtree(os.path.join(home2, "_anatomy_cache", "disc_runner2_r1"))
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv("EDGELOG_HOME", home2)
        with pytest.raises(SystemExit, match="RUNNER2's count step"):
            PM.mode_null(chain.inp, chain.photo, r2=chain.r2, verbose=False)
    finally:
        mp.undo()


def test_verify_null_file_for_runner2(chain, tmp_path):
    p = os.path.join(_od(chain.home), "null.json")
    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    nj = PM.verify_null_file(sha, omega_sha="ab" * 32, r2_harness_path=chain.r2[1], path=p)
    assert nj["draws"] == 500
    with pytest.raises(SystemExit, match="posted"):
        PM.verify_null_file("0" * 64, path=p)
    with pytest.raises(SystemExit, match="Omega"):
        PM.verify_null_file(sha, omega_sha="ee" * 32, path=p)
    other = tmp_path / "other_r2.py"
    other.write_text("# another harness\n")
    with pytest.raises(SystemExit, match="different RUNNER2 harness"):
        PM.verify_null_file(sha, r2_harness_path=str(other), path=p)
    bad = json.loads(open(p, encoding="utf-8").read())
    bad["seeds"]["runner2"] = 20261006
    q = tmp_path / "null.json"
    q.write_bytes(json.dumps(bad).encode())
    with pytest.raises(SystemExit, match="seeds"):
        PM.verify_null_file(hashlib.sha256(q.read_bytes()).hexdigest(), path=str(q))


def test_run_refuses_when_the_recomputed_counts_differ(chain):
    home2 = str(chain.tmp / "home_tamper")
    shutil.copytree(chain.home, home2)
    p = os.path.join(_od(home2), "counts.json")
    c = json.load(open(p, encoding="utf-8"))
    c["halts"]["run_lengths"]["4"] += 1
    open(p, "w", encoding="utf-8").write(json.dumps(c))
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv("EDGELOG_HOME", home2)
        with pytest.raises(SystemExit, match="recomputed counts"):
            PM.mode_run(chain.inp, chain.photo, verbose=False)
    finally:
        mp.undo()


def test_a_later_step_refuses_a_different_stamp(chain):
    home2 = str(chain.tmp / "home_stamp")
    shutil.copytree(chain.home, home2)
    inp2 = SimpleNamespace(**vars(chain.inp))
    inp2.shas = {"daily_raw.parquet": "b" * 64}
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv("EDGELOG_HOME", home2)
        with pytest.raises(SystemExit, match="different inputs_sha256"):
            PM.mode_power(inp2, chain.photo, verbose=False)
        with pytest.raises(SystemExit, match="has not been filed"):
            mp.setenv("EDGELOG_HOME", str(chain.tmp / "empty_home"))
            PM.mode_overlap(chain.inp, verbose=False)
    finally:
        mp.undo()


def test_counts_step_never_walks_an_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path / "home"))
    _no_sockets(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("an exit walk ran in the count step")
    monkeypatch.setattr(PM, "walk", boom)
    monkeypatch.setattr(PM, "halted_close_exit", boom)
    monkeypatch.setattr(PM, "resolve", boom)
    inp, photo = make_world(seed=12, per_year=3)
    counts, sched = PM.mode_counts(inp, photo, verbose=False)
    od = _od(str(tmp_path / "home"))
    assert os.path.exists(os.path.join(od, "counts.json")) and "count_gate" in counts
    assert not os.path.exists(os.path.join(od, "trades.csv")) and not os.path.exists(os.path.join(od, "daily.csv"))
    assert {"E", "S1", "S2", "entry_m"} <= set(sched.columns) and "exit" not in sched.columns


def test_fb_meta_probe_verdict():
    """tools/disc_gapper_probe.py: SAME MAPPING only when both symbols are served and serve the same records"""
    import disc_gapper_probe as PR
    rec = ['{"c": 135.68, "t": "2019-01-02T05:00:00Z"}']
    assert PR.verdict(rec, list(rec)) == "SAME MAPPING"
    assert PR.verdict(rec, None).startswith("DIFFERENT")
    assert PR.verdict([], []).startswith("DIFFERENT")
    assert PR.verdict(rec, []).startswith("DIFFERENT")
    assert PR.verdict(rec, ['{"c": 135.69, "t": "2019-01-02T05:00:00Z"}']).startswith("DIFFERENT")
    body = json.dumps({"bars": {"META": [{"t": "2019-01-02T05:00:00Z", "c": 135.68}]}, "next_page_token": None}).encode()
    assert PR.served("bars", "META", body) == ['{"c": 135.68, "t": "2019-01-02T05:00:00Z"}']
    assert PR.served("bars", "FB", json.dumps({"bars": {}}).encode()) == []


def test_split_cap_counts_the_stress_priced_halts_ttm_asked_for():
    """TTM #55 / #56: a halted-into-close short whose next open gaps 2-3x is flagged by price-only test M and priced at
    max(stop, last close) - count it, and the dollars the cap kept off the short"""
    import disc_runner2_r1_stageA as R2
    for mod in (PM, R2):
        nan = float("nan")
        # M alone fires on the session of the first served open, which gaps to 2.5x the stress price
        r = mod.split_cap([nan, 25.0], [False, False], [False, True], 10.0, -1.0)
        assert r == {"open": 25.0, "flagged": True, "m_only": True, "worse": True, "gap": 15.0}
        # S1 / calendar fired too -> not M alone; an open below the stress price is not 'worse' for a short
        r = mod.split_cap([nan, 8.0], [True, False], [False, True], 10.0, -1.0)
        assert r["flagged"] and not r["m_only"] and not r["worse"]
        # a flag AFTER the first served open never counts; no served open -> None
        assert mod.split_cap([12.0, 30.0], [False, False], [False, True], 10.0, -1.0)["flagged"] is False
        assert mod.split_cap([nan, nan], [False, True], [False, False], 10.0, -1.0) is None
        rep = mod.split_cap_report([(mod.split_cap([nan, 25.0], [False, False], [False, True], 10.0, -1.0), True, 100),
                                    (mod.split_cap([12.0], [False], [False], 10.0, -1.0), False, 50),
                                    (None, True, 10)])
        assert rep == {"halted_close": 3, "priced_as_split": 2, "split_with_open_served": 1, "split_by_test_M_alone": 1,
                       "open_worse_than_stress_price": 1, "worse_and_test_M_alone": 1,
                       "usd_capped_at_judged_shares": 1500.0}
