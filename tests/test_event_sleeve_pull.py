"""EVENT SLEEVE forward feeds: tools/event_sleeve_pull.py (the two owner-approved pulls) and the scorer's forward overlay in
tools/event_sleeve_shadow.py (latest pull, sha check, ratio splice, overlap rule, staleness on the pull's dates, the no-pull
path). Offline and synthetic: the two network functions are replaced, every file lives in a tmp dir (EDGELOG_EVENT_SLEEVE)."""
import contextlib
import datetime
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import event_sleeve_pull as P  # noqa: E402
import event_sleeve_shadow as S  # noqa: E402

NY_AFTER = pd.Timestamp("2026-10-14 17:05:00", tz="America/New_York").to_pydatetime()
NY_BEFORE = pd.Timestamp("2026-10-14 15:10:00", tz="America/New_York").to_pydatetime()


# ------------------------------------------------------------------ synthetic inputs
def _walk(dates, seed, start=100.0, sd=0.008):
    r = np.random.default_rng(seed).normal(0.0002, sd, len(dates))
    return pd.Series(start * np.cumprod(1.0 + r), index=pd.DatetimeIndex(dates))


def _yf_frame(closes):
    """A yfinance-shaped multi-ticker frame (Price x Ticker columns) from {ticker: Series}."""
    d = {}
    for t, s in closes.items():
        d[("Close", t)] = s.values
        d[("Open", t)] = s.values * 0.999
    df = pd.DataFrame(d, index=pd.DatetimeIndex(next(iter(closes.values())).index, name="Date"))
    df.columns = pd.MultiIndex.from_tuples(df.columns, names=["Price", "Ticker"])
    return df


def _pull_dates(last="2026-10-14"):
    return pd.bdate_range("2025-06-02", last)


@pytest.fixture(autouse=True)
def _keep_sys_path(monkeypatch):
    """The scorer's lazy imports put the shared checkout on sys.path; undo that after each test so no later test imports
    a package from there instead of this checkout."""
    monkeypatch.setattr(sys, "path", list(sys.path))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_EVENT_SLEEVE", str(tmp_path))
    return tmp_path


def _fake_yahoo(monkeypatch, closes):
    calls = []

    def fake(tickers, start, end):
        calls.append((tuple(tickers), start, end))
        return _yf_frame(closes)
    monkeypatch.setattr(P, "_yf_download", fake)
    return calls


def _std_closes(last="2026-10-14"):
    d = _pull_dates(last)
    return {"SPY": _walk(d, 1, 600.0), "TLT": _walk(d, 2, 88.0), "IEF": _walk(d, 3, 95.0, 0.003)}


def _prov(home):
    return [json.loads(x) for x in open(os.path.join(str(home), "fwd_data", "provenance.jsonl"), encoding="utf-8")]


# ------------------------------------------------------------------ the pull tool
def test_auctions_url_is_the_snapshot_query():
    # the URL tvnt2_provenance.json recorded for treasury_auctions_raw.json (fetched 2026-10-05)
    assert P.AUCTIONS_URL == (
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?fields=cusip,"
        "security_type,security_term,original_security_term,auction_date,announcemt_date,issue_date,reopening,offering_amt,"
        "inflation_index_security,floating_rate&filter=security_type:in:(Note,Bond),auction_date:gte:2005-01-01"
        "&sort=auction_date&page[size]=10000")


def test_fwd_dir_follows_the_scorers_env_var(home):
    assert P.fwd_dir() == os.path.join(str(home), "fwd_data")
    assert S.fwd_dir(str(home)) == P.fwd_dir()


def test_yahoo_pull_writes_close_csv_and_a_provenance_record(home, monkeypatch):
    closes = _std_closes()
    calls = _fake_yahoo(monkeypatch, closes)
    rec = P.pull_yahoo(now=NY_AFTER)
    tomorrow = str(P._now(NY_AFTER).date() + datetime.timedelta(days=1))           # end = tomorrow (local), exclusive
    assert calls == [(("SPY", "TLT", "IEF"), "2025-06-01", tomorrow)]
    path = os.path.join(str(home), "fwd_data", rec["file"])
    raw = open(path, "rb").read()
    assert rec["file"] == "yahoo_daily_%s.csv" % P.stamp(P._now(NY_AFTER)) and rec["file"].startswith("yahoo_daily_2026")
    assert raw.splitlines()[0] == b"date,SPY,TLT,IEF" and b"\r\n" not in raw
    df = S.load_pull_csv(path)
    assert list(df.columns) == ["SPY", "TLT", "IEF"]
    for t in ("SPY", "TLT", "IEF"):
        assert np.array_equal(df[t].values, closes[t].values)                    # verbatim: floats round-trip exactly
    assert df.index[-1] == pd.Timestamp("2026-10-14")                                 # after 16:30 ET: today kept
    (r,) = _prov(home)
    assert r == rec
    for k in ("kind", "tickers", "params", "fetched_at", "fetched_at_epoch", "bytes", "sha256", "rows", "first_date",
              "last_date", "file", "tool_sha256_lf"):
        assert k in r, k
    assert r["kind"] == "yahoo" and r["tickers"] == ["SPY", "TLT", "IEF"]
    assert r["params"]["auto_adjust"] is True and r["params"]["start"] == "2025-06-01" and r["params"]["kept"] == "Close"
    assert r["bytes"] == len(raw) and r["sha256"] == hashlib.sha256(raw).hexdigest()
    assert r["rows"] == len(closes["SPY"]) and (r["first_date"], r["last_date"]) == ("2025-06-02", "2026-10-14")
    assert pd.Timestamp(r["fetched_at"]).tzinfo is not None                            # ISO local time WITH its offset
    assert r["dropped_incomplete_today"] is None


def test_yahoo_drops_todays_row_before_1630_et(home, monkeypatch):
    _fake_yahoo(monkeypatch, _std_closes())
    rec = P.pull_yahoo(now=NY_BEFORE)
    assert rec["last_date"] == "2026-10-13" and rec["dropped_incomplete_today"] == "2026-10-14"
    assert S.load_pull_csv(os.path.join(str(home), "fwd_data", rec["file"])).index[-1] == pd.Timestamp("2026-10-13")


def test_pull_never_overwrites_an_existing_file(home, monkeypatch):
    _fake_yahoo(monkeypatch, _std_closes())
    rec = P.pull_yahoo(now=NY_AFTER)
    path = os.path.join(str(home), "fwd_data", rec["file"])
    before = open(path, "rb").read()
    _fake_yahoo(monkeypatch, _std_closes("2026-10-13"))          # a different answer at the same second
    with pytest.raises(SystemExit, match="never overwritten"):
        P.pull_yahoo(now=NY_AFTER)
    assert open(path, "rb").read() == before and len(_prov(home)) == 1


def test_yahoo_refuses_an_empty_frame_or_an_empty_ticker(home, monkeypatch):
    monkeypatch.setattr(P, "_yf_download", lambda t, s, e: pd.DataFrame())
    with pytest.raises(SystemExit, match="empty frame"):
        P.pull_yahoo(now=NY_AFTER)
    c = _std_closes()
    c["IEF"] = c["IEF"] * np.nan
    _fake_yahoo(monkeypatch, c)
    with pytest.raises(SystemExit, match="IEF"):
        P.pull_yahoo(now=NY_AFTER)
    assert not os.path.exists(os.path.join(str(home), "fwd_data", "provenance.jsonl"))


def _auction_json(rows, total=None):
    return json.dumps({"data": rows, "meta": {"total-count": len(rows) if total is None else total}}).encode()


def test_auctions_pull_saves_the_response_byte_for_byte(home, monkeypatch):
    rows = [dict(auction_date="2026-10-%02d" % d, announcemt_date="2026-10-%02d" % (d - 5), security_term="10-Year")
            for d in (7, 9, 14)]
    raw = _auction_json(rows)
    seen = []
    monkeypatch.setattr(P, "_http_get", lambda url: seen.append(url) or raw)
    rec = P.pull_auctions(now=NY_AFTER)
    assert seen == [P.AUCTIONS_URL]
    path = os.path.join(str(home), "fwd_data", rec["file"])
    assert rec["file"].startswith("treasury_auctions_") and rec["file"].endswith(".json")
    assert open(path, "rb").read() == raw
    (r,) = _prov(home)
    assert r["kind"] == "auctions" and r["url"] == P.AUCTIONS_URL and r["rows"] == 3
    assert (r["first_date"], r["last_date"], r["last_announced"]) == ("2026-10-07", "2026-10-14", "2026-10-09")
    assert r["sha256"] == hashlib.sha256(raw).hexdigest() and r["bytes"] == len(raw)


@pytest.mark.parametrize("raw, why", [(b'{"meta": {}}', "data"), (b'{"data": []}', "data"), (b"not json", "not JSON"),
                                      (_auction_json([dict(auction_date="2026-10-07")], total=5), "cut")])
def test_auctions_pull_refuses_a_response_without_data(home, monkeypatch, raw, why):
    monkeypatch.setattr(P, "_http_get", lambda url: raw)
    with pytest.raises(SystemExit, match=why):
        P.pull_auctions(now=NY_AFTER)
    assert not os.path.exists(os.path.join(str(home), "fwd_data")) or os.listdir(os.path.join(str(home), "fwd_data")) == []


# ------------------------------------------------------------------ ratio splice + overlap rule
def test_ratio_splice_keeps_history_and_carries_the_pulls_returns():
    snap = _walk(pd.bdate_range("2025-01-02", "2026-09-08"), 7, 90.0)
    snap.iloc[100] = np.nan                                          # a snapshot hole stays a hole
    pull = _walk(pd.bdate_range("2025-06-02", "2026-10-14"), 8, 50.0)
    pull.loc[pd.Timestamp("2026-09-08")] = 51.0
    sp, L, k = S.ratio_splice(snap, pull)
    assert L == pd.Timestamp("2026-09-08") and k == pytest.approx(snap[L] / 51.0)
    hist = sp[sp.index <= L]
    assert hist.index.equals(snap.index) and np.array_equal(hist.values, snap.values, equal_nan=True)
    after = sp[sp.index >= L]
    pr = pull[pull.index >= L]
    assert after.index.equals(pr.index)
    assert np.allclose(after.values[1:] / after.values[:-1], pr.values[1:] / pr.values[:-1], rtol=1e-12)
    assert after.index[-1] == pd.Timestamp("2026-10-14")


def test_ratio_splice_refuses_when_the_snapshots_last_date_is_not_in_the_pull():
    snap = _walk(pd.bdate_range("2025-01-02", "2026-09-08"), 7)
    pull = _walk(pd.bdate_range("2025-06-02", "2026-10-14"), 8)
    with pytest.raises(ValueError, match="pull does not overlap the snapshot"):
        S.ratio_splice(snap, pull.drop(pd.Timestamp("2026-09-08")))
    late = _walk(pd.bdate_range("2026-09-09", "2026-10-14"), 8)
    with pytest.raises(ValueError, match="pull does not overlap the snapshot"):
        S.ratio_splice(snap, late)
    sp, _, note, why = S.checked_splice("TLT", snap, dict(file="y.csv", df=pd.DataFrame({"TLT": late})))
    assert sp is None and "pull does not overlap the snapshot" in why


def _agreeing_pull(snap, last="2026-10-14", scale=1.0137, noise=1e-5, bad_share=0.0, bad=2e-3, seed=11):
    """A pull whose returns on the snapshot's dates equal the snapshot's (+ noise; a share of days off by `bad`), extended
    past the snapshot's end with its own walk."""
    rng = np.random.default_rng(seed)
    s = snap.dropna()
    s = s[s.index >= pd.Timestamp("2025-06-02")]
    r = s.values[1:] / s.values[:-1] - 1.0 + rng.normal(0, noise, len(s) - 1)
    hit = rng.random(len(r)) < bad_share
    r[hit] += bad
    lvl = np.concatenate([[s.values[0] * scale], s.values[0] * scale * np.cumprod(1.0 + r)])
    head = pd.Series(lvl, index=s.index)
    tail_idx = pd.bdate_range(s.index[-1] + pd.Timedelta(days=1), last)
    tail = pd.Series(head.iloc[-1] * np.cumprod(1.0 + rng.normal(0, 0.006, len(tail_idx))), index=tail_idx)
    return pd.concat([head, tail])


def test_overlap_rule_passes_an_agreeing_pull_and_prints_its_share():
    snap = _walk(pd.bdate_range("2024-01-02", "2026-09-08"), 21, 88.0)
    pull = _agreeing_pull(snap)
    n, share, mx = S.overlap_agreement(snap, pull)
    assert n > 300 and share == 1.0 and mx < 1e-4
    sp, L, note, why = S.checked_splice("TLT", snap, dict(file="y.csv", df=pd.DataFrame({"TLT": pull})))
    assert why is None and L == pd.Timestamp("2026-09-08")
    assert "100.0 % within 0.001" in note and "max |diff|" in note and "spliced after L 2026-09-08" in note
    assert sp.index[-1] == pd.Timestamp("2026-10-14")


def test_overlap_rule_refuses_a_disagreeing_or_short_pull():
    snap = _walk(pd.bdate_range("2024-01-02", "2026-09-08"), 21, 88.0)
    pull = _agreeing_pull(snap, bad_share=0.10)
    n, share, mx = S.overlap_agreement(snap, pull)
    assert share < 0.95 and mx > 1e-3
    sp, _, note, why = S.checked_splice("TLT", snap, dict(file="y.csv", df=pd.DataFrame({"TLT": pull})))
    assert sp is None and "disagrees with its snapshot" in why and "%.1f %%" % (100 * share) in why and "max |diff|" in why
    short = _agreeing_pull(snap)
    short = short[short.index >= pd.Timestamp("2026-08-20")]          # 13 common return days: under the 20-day floor
    n, share, _ = S.overlap_agreement(snap, short)
    sp, _, _, why = S.checked_splice("TLT", snap, dict(file="y.csv", df=pd.DataFrame({"TLT": short})))
    assert n == 13 and share == 1.0 and sp is None and "13 common return days" in why and "needs >= 20 days" in why


def test_splice_fund_frame_extends_the_calendar_and_leaves_history():
    idx = pd.bdate_range("2026-08-03", "2026-09-23")
    C = pd.DataFrame({"IEF": _walk(idx, 1, 95.0).values, "TLT": _walk(idx, 2, 88.0).values}, index=idx)
    C.loc[C.index > pd.Timestamp("2026-09-08"), "TLT"] = np.nan        # the TLT master ends earlier than the cache calendar
    C.loc[pd.Timestamp("2026-09-22"), "IEF"] = np.nan
    L = {"IEF": pd.Timestamp("2026-09-23"), "TLT": pd.Timestamp("2026-09-08")}
    tail = pd.bdate_range("2026-09-09", "2026-10-14")
    sp = {"IEF": pd.concat([C["IEF"], pd.Series(90.0, index=tail[tail > L["IEF"]])]),
          "TLT": pd.concat([C["TLT"][C.index <= L["TLT"]], pd.Series(80.0, index=tail)])}
    out = S.splice_fund_frame(C, sp, L)
    assert out.index[: len(C)].equals(C.index) and out.index[-1] == pd.Timestamp("2026-10-14")
    old = out.loc[C.index]
    assert np.array_equal(old["IEF"].values, C["IEF"].values, equal_nan=True)          # IEF history incl. its hole
    keep = C.index <= L["TLT"]
    assert np.array_equal(old["TLT"].values[keep], C["TLT"].values[keep])
    assert (out.loc[out.index > L["TLT"], "TLT"] == 80.0).all() and (out.loc[out.index > L["IEF"], "IEF"] == 90.0).all()


# ------------------------------------------------------------------ latest pull + sha check
def test_latest_pull_is_the_newest_existing_file_and_a_changed_file_refuses(home, monkeypatch):
    _fake_yahoo(monkeypatch, _std_closes("2026-10-13"))
    old = P.pull_yahoo(now=NY_AFTER - datetime.timedelta(days=1))
    _fake_yahoo(monkeypatch, _std_closes())
    new = P.pull_yahoo(now=NY_AFTER)
    fdir = os.path.join(str(home), "fwd_data")
    rec, path, why = S.latest_pull(fdir, "yahoo")
    assert rec["file"] == new["file"] and why is None
    assert S.latest_pull(fdir, "auctions") == (None, None, None)
    os.remove(os.path.join(fdir, new["file"]))                        # a deleted file is passed over
    rec, _, why = S.latest_pull(fdir, "yahoo")
    assert rec["file"] == old["file"] and why is None
    with open(os.path.join(fdir, old["file"]), "ab") as f:            # a changed file is refused, not replaced by an older one
        f.write(b"2026-10-15,1,1,1\n")
    rec, _, why = S.latest_pull(fdir, "yahoo")
    assert rec["file"] == old["file"] and "sha256" in why and "is not the recorded" in why
    feeds = S.forward_feeds(str(home))
    assert feeds["yahoo"]["error"] == why and feeds["auctions"] is None
    monkeypatch.setattr(S, "_master_file", lambda *a: "master_x.csv")
    for p in ("A", "B"):
        plan = S.part_plan(p, feeds, pd.Timestamp("2026-10-14"), str(home), pd.Timestamp("2026-10-14"))
        assert plan["refuse"] == why


# ------------------------------------------------------------------ staleness on the pull's dates
def _snapshots(monkeypatch):
    """Snapshots ending where the real ones do: TLT / SPY masters 2026-09-08, IEF cache 2026-09-23 (one hole)."""
    spy = _walk(pd.bdate_range("2024-01-02", "2026-09-08"), 31, 600.0)
    tlt = _walk(pd.bdate_range("2024-01-02", "2026-09-08"), 32, 88.0)
    ief = _walk(pd.bdate_range("2024-01-02", "2026-09-23"), 33, 95.0, 0.003)
    ief.loc[pd.Timestamp("2026-09-22")] = np.nan
    fake = types.ModuleType("rebal_scan")
    fake.SPY, fake.TLT = spy, tlt
    monkeypatch.setitem(sys.modules, "rebal_scan", fake)
    monkeypatch.setattr(S, "snapshot_ief", lambda: ief)
    monkeypatch.setattr(S, "master_close", lambda sym: {"TLT": tlt, "SPY": spy}[sym])
    monkeypatch.setattr(S, "_master_file", lambda inst, *a: "master_%s.csv" % inst)
    monkeypatch.setattr(S, "master_last_bar", lambda *a: pd.Timestamp("2026-10-13 15:55", tz="US/Eastern"))
    monkeypatch.setattr(S, "auction_calendar_fetch_date", lambda: pd.Timestamp("2026-10-05"))
    return fake, spy, tlt, ief


def _write_agreeing_pull(home, monkeypatch, spy, tlt, ief, now=NY_AFTER, last="2026-10-13"):
    c = {"SPY": _agreeing_pull(spy, last, seed=1), "TLT": _agreeing_pull(tlt, last, seed=2),
         "IEF": _agreeing_pull(ief, last, seed=3)}
    idx = c["SPY"].index
    _fake_yahoo(monkeypatch, {k: v.reindex(idx) for k, v in c.items()})
    return P.pull_yahoo(now=now)


def test_part_b_staleness_reads_the_spliced_series_and_swaps_rebal_scans_globals(home, monkeypatch):
    fake, spy, tlt, _ = _snapshots(monkeypatch)
    rec = _write_agreeing_pull(home, monkeypatch, spy, tlt, _)
    feeds = S.forward_feeds(str(home))
    today = pd.Timestamp("2026-10-14")
    plan = S.part_plan("B", feeds, today, str(home), today)
    assert plan["refuse"] is None and plan["data"].count(rec["file"]) == 2 and "master_ES.csv" in plan["data"]
    assert any(n.startswith("SPY pull vs snapshot") and "100.0 %" in n for n in plan["notes"])
    with plan["ctx"]():
        assert fake.SPY is not spy and fake.SPY.index[-1] == pd.Timestamp("2026-10-13")
        assert fake.SPY[fake.SPY.index <= pd.Timestamp("2026-09-08")].equals(spy)
        ends = plan["ends"]()
    assert fake.SPY is spy and fake.TLT is tlt                                  # restored
    assert sorted(pd.Timestamp(v) for v in ends.values()) == [pd.Timestamp("2026-10-13")] * 3
    assert any(k.startswith("SPY close (yahoo_adj 1d master to 2026-09-08 + %s" % rec["file"]) for k in ends)
    ok, why, _ = S.staleness(ends, today)
    assert ok
    ok, _, _ = S.staleness({"SPY close (yahoo_adj 1d master)": spy.index[-1]}, today)
    assert not ok                                                               # the snapshot alone is stale


def test_part_a_staleness_reads_the_spliced_closes_and_the_forward_auction_date(home, monkeypatch):
    _, spy, tlt, ief = _snapshots(monkeypatch)
    rec = _write_agreeing_pull(home, monkeypatch, spy, tlt, ief)
    today = pd.Timestamp("2026-10-14")
    plan = S.part_plan("A", S.forward_feeds(str(home)), today, str(home), today)  # no auctions pull yet
    assert plan["refuse"] is None
    ends = plan["ends"]()
    assert ends["auction calendar (treasury_auctions_raw.json fetch)"] == pd.Timestamp("2026-10-05")
    ok, why, _ = S.staleness(ends, today)
    assert not ok and "auction calendar (treasury_auctions_raw.json fetch) ends 2026-10-05" in why and "IEF" not in why
    monkeypatch.setattr(P, "_http_get", lambda url: _auction_json([dict(auction_date="2026-10-14")]))
    arec = P.pull_auctions(now=pd.Timestamp("2026-10-13 12:00", tz="America/New_York").to_pydatetime())
    plan = S.part_plan("A", S.forward_feeds(str(home)), today, str(home), today)
    assert arec["file"] in plan["data"] and rec["file"] in plan["data"]
    _, T2 = S._imp_auction()
    snap_file = T2.AUC_FILE
    with plan["ctx"]():
        assert T2.AUC_FILE == os.path.join(str(home), "fwd_data", arec["file"])
        ends = plan["ends"]()
    assert T2.AUC_FILE == snap_file and S._AUC_FETCH_OVERRIDE is None          # restored
    assert ends == {"IEF close (nonequity_close.csv to 2026-09-23 + %s)" % rec["file"]: pd.Timestamp("2026-10-13"),
                    "TLT close (yahoo_adj 1d master to 2026-09-08 + %s)" % rec["file"]: pd.Timestamp("2026-10-13"),
                    "auction calendar (%s fetch)" % arec["file"]: pd.Timestamp(arec["fetched_at"][:10])}
    ok, why, _ = S.staleness(ends, today)
    assert ok


def test_part_a_refuses_when_a_pull_series_disagrees(home, monkeypatch):
    _, spy, tlt, ief = _snapshots(monkeypatch)
    c = {"SPY": _agreeing_pull(spy, "2026-10-13", seed=1), "TLT": _agreeing_pull(tlt, "2026-10-13", seed=2, bad_share=0.2),
         "IEF": _agreeing_pull(ief, "2026-10-13", seed=3)}
    _fake_yahoo(monkeypatch, {k: v.reindex(c["SPY"].index) for k, v in c.items()})
    P.pull_yahoo(now=NY_AFTER)
    today = pd.Timestamp("2026-10-14")
    feeds = S.forward_feeds(str(home))
    for p in ("A", "B"):                                                        # TLT feeds both parts
        plan = S.part_plan(p, feeds, today, str(home), today)
        assert plan["refuse"].startswith("TLT ") and "disagrees with its snapshot" in plan["refuse"]


def test_part_a_forward_reads_the_forward_auction_file(home, monkeypatch):
    """The A runner end to end on synthetic closes: the calendar comes from the forward file (AUC_FILE swapped) and the
    settle rule uses the forward fetch date."""
    idx = pd.bdate_range("2026-03-02", "2026-10-13")
    C = pd.DataFrame({"IEF": _walk(idx, 41, 95.0, 0.003).values, "TLT": _walk(idx, 42, 88.0).values}, index=idx)
    days = [d for d in idx if d.weekday() == 2 and 8 <= d.day <= 14]          # the second Wednesday, March..September
    rows = []
    for i, d in enumerate(days):
        for term in ("10-Year", "30-Year", "5-Year"):
            rows.append(dict(cusip="X%d%s" % (i, term[:2]), security_type="Note", security_term=term, original_security_term=term,
                             auction_date=str(d.date()), announcemt_date=str((d - pd.Timedelta(days=7)).date()),
                             offering_amt=str(40e9 + i * 1e9), inflation_index_security="No", floating_rate="No"))
    monkeypatch.setattr(P, "_http_get", lambda url: _auction_json(rows))
    arec = P.pull_auctions(now=pd.Timestamp("2026-10-13 12:00", tz="America/New_York").to_pydatetime())
    path = os.path.join(str(home), "fwd_data", arec["file"])
    ends = {"IEF close (x)": idx[-1], "TLT close (x)": idx[-1]}
    _, T2 = S._imp_auction()
    snap_file = T2.AUC_FILE
    with S.auction_feed(path, arec["fetched_at"][:10]):
        assert S.auction_calendar_fetch_date() == pd.Timestamp("2026-10-13")
        fwd, daily, info = S.part_a_forward("2026-06-01", ends, closes=C)
        old_cut, T2.CUT = T2.CUT, pd.Timestamp("2262-01-01")                 # as part_a_forward reads it (no 2025-06-30 cut)
        try:
            ev, _ = T2.load_auctions(C.index)
        finally:
            T2.CUT = old_cut
    assert T2.AUC_FILE == snap_file and S._AUC_FETCH_OVERRIDE is None
    assert sorted(t for t, _, _ in ev["TLT"]) == [C.index.get_loc(d) for d in days]   # the calendar came from the forward file
    assert len(fwd) > 0 and (fwd.entry > pd.Timestamp("2026-06-01")).all() and set(fwd.instrument) <= {"IEF", "TLT"}
    assert abs(float(daily.sum()) - float(fwd.pnl.sum())) < 1e-6
    with S.auction_feed(path, "2026-09-10"):                                      # an earlier fetch date settles fewer runs
        early, _, info_e = S.part_a_forward("2026-06-01", ends, closes=C)
    assert len(early) < len(fwd) and info_e["pending"] > info["pending"]
    assert (early.exit < pd.Timestamp("2026-09-10")).all()


# ------------------------------------------------------------------ the no-pull path is the old path
def test_no_pull_plans_are_the_snapshot_functions(home, monkeypatch):
    monkeypatch.setattr(S, "_master_file", lambda inst, *a: "master_%s.csv" % inst)
    feeds = S.forward_feeds(str(home))
    assert feeds == {"yahoo": None, "auctions": None}
    today = pd.Timestamp("2026-10-14")
    plans = {p: S.part_plan(p, feeds, today, str(home), today) for p in S.PARTS}
    assert plans["A"]["ends"] is S.part_a_ends and plans["B"]["ends"] is S.part_b_ends and plans["C"]["ends"] is S.part_c_ends
    for p in S.PARTS:
        assert plans[p]["refuse"] is None and plans[p]["notes"] == [] and plans[p]["ctx"] is contextlib.nullcontext
    assert "no forward pull on record" in plans["A"]["data"] and "no forward pull on record" in plans["B"]["data"]


def _constants(tmp):
    os.makedirs(str(tmp), exist_ok=True)
    with open(os.path.join(str(tmp), S.CONSTANTS_FILE), "w") as f:
        json.dump(dict(parts={p: dict(scale=1.0) for p in S.PARTS}, harm=dict(threshold_risk_units=-8.2749)), f)


def _stub_parts(monkeypatch):
    a_ends = {"IEF close (research cache nonequity_close.csv)": pd.Timestamp("2026-09-23"),
              "TLT close (yahoo_adj 1d master)": pd.Timestamp("2026-09-08"),
              "auction calendar (treasury_auctions_raw.json fetch)": pd.Timestamp("2026-10-05")}
    b_ends = {"SPY close (yahoo_adj 1d master)": pd.Timestamp("2026-09-08"),
              "TLT close (yahoo_adj 1d master)": pd.Timestamp("2026-09-08"),
              "ES 5m RTH (db_noadj_rth master)": pd.Timestamp("2026-10-14")}
    today = pd.Timestamp(datetime.date.today())
    monkeypatch.setattr(S, "part_a_ends", lambda: dict(a_ends))
    monkeypatch.setattr(S, "part_b_ends", lambda: dict(b_ends))
    monkeypatch.setattr(S, "part_c_ends", lambda: {"NQ 1m ETH (db_noadj_eth master)": today})
    empty = pd.DataFrame(columns=["part", "instrument", "entry", "exit", "side", "pnl", "detail"])
    monkeypatch.setattr(S, "part_c_forward", lambda since, e, out_dir, today: (empty, pd.Series(dtype=float), dict(pending=0)))
    monkeypatch.setattr(S, "_master_file", lambda inst, *a: "master_%s.csv" % inst)
    return a_ends, b_ends, today


def test_forward_without_a_pull_refuses_exactly_as_before(tmp_path, monkeypatch, capsys):
    a_ends, b_ends, today = _stub_parts(monkeypatch)
    _constants(tmp_path)
    T, D, status = S.mode_forward("2026-10-14", out_dir=str(tmp_path))
    out = capsys.readouterr().out
    for p, e in (("A", a_ends), ("B", b_ends)):
        ok, why, _ = S.staleness(e, today)
        assert not ok and status[p]["status"] == "REFUSED" and status[p]["reason"] == why
        assert status[p]["ends"] == {k: str(v.date()) for k, v in e.items()}
        assert ("PART %s %-14s REFUSED - %s" % (p, S.PART_NAME[p], why)) in out
    assert status["C"]["status"] == "SCORED" and len(T) == 0
    assert out.count("      data: ") == 3 and "no forward pull on record" in out
    assert not os.path.exists(os.path.join(str(tmp_path), "fwd_data"))       # nothing written there


def test_forward_with_a_changed_pull_file_refuses_a_and_b_only(home, monkeypatch, capsys):
    _stub_parts(monkeypatch)
    _constants(home)
    _fake_yahoo(monkeypatch, _std_closes())
    rec = P.pull_yahoo(now=NY_AFTER)
    with open(os.path.join(str(home), "fwd_data", rec["file"]), "ab") as f:
        f.write(b"\n")
    _, _, status = S.mode_forward("2026-10-14", out_dir=str(home))
    out = capsys.readouterr().out
    for p in ("A", "B"):
        assert status[p]["status"] == "REFUSED" and "is not the recorded" in status[p]["reason"]
        assert rec["file"] in status[p]["data"]
    assert status["C"]["status"] == "SCORED"
    assert "PART A AUCTION K5     REFUSED - forward yahoo pull %s: sha256" % rec["file"] in out
