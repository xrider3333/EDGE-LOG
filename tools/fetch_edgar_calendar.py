# -*- coding: utf-8 -*-
"""EDGAR FILING CALENDAR for every Nasdaq-100 member the house knows (TV, public-data scout, MANAGER #62, 2026-10-05).

WHAT: for each company, every 8-K / 10-Q / 10-K (and amendments) the SEC's submissions index lists, with the EDGAR
acceptance time - the house's EARNINGS CALENDAR is the 8-K rows carrying Item 2.02 ("Results of Operations"), filed
within minutes of the press release (method of tools/fetch_megacap_earnings.py, NOISE round 60, widened from 7 names).

SOURCES (public, no key):
  https://www.sec.gov/files/company_tickers.json            current ticker -> CIK
  https://data.sec.gov/submissions/CIK##########.json      the filing index, plus its older 'files' pages
PHOTOGRAPH RULE: every response is saved byte for byte under C:\\EdgeLog\\_research_cache\\edgar\\ and listed in
edgar_provenance.json (URL, fetch time, bytes, sha256); the derived CSVs are rebuilt from those files, never re-fetched.
A second run REFUSES to overwrite an existing raw file (pass --refresh-into NEWDIR for a new photograph).
CONTACT STRING: SEC asks every client to declare one; this sends the house's neutral string (as fetch_megacap_earnings.py
does), never the owner's address. ~0.15 s between requests (SEC's cap is 10 a second).

UNMAPPED: tickers that are no longer listed (acquired, renamed) are not in the current ticker file; they are printed and
can be added to EXTRA_CIK by hand with a source note.

    python tools/fetch_edgar_calendar.py            # fetch (once) + build
    python tools/fetch_edgar_calendar.py --build    # rebuild the CSVs from the saved photographs only
"""
import argparse, csv, datetime, hashlib, json, os, sys, time, urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = r"C:\EdgeLog\_research_cache\edgar"
PROV = os.path.join(RAW, "edgar_provenance.json")
OUT_FILINGS = os.path.join(RAW, "filings_ndx.csv")
OUT_EARN = os.path.join(RAW, "earnings_calendar_ndx.csv")
UA = {"User-Agent": "EdgeLog research tool edgelog-research@example.com", "Accept-Encoding": "identity"}
FORMS = {"8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A"}
# Old tickers the current file no longer carries, mapped by hand from SEC's cik-lookup-data.txt (photographed 10-05 with
# provenance) by company name, choosing the CIK that filed during the ticker's Nasdaq-100 membership (e.g. VIAB = the
# 2006-2019 Viacom Inc 1339947, not CBS / old Viacom 813828; MYL = Mylan N.V. 1623613; ESRX = Express Scripts Holding).
EXTRA_CIK = {"FB": "0001326801", "GOOG": "0001652044", "GOOGL": "0001652044",
             "ALXN": "0000899866", "ANSS": "0001013462", "ATVI": "0000718877", "BBBY": "0000886158", "CA": "0000356028",
             "CELG": "0000816284", "CERN": "0000804753", "CTRP": "0001269238", "CTXS": "0000877890", "DISCA": "0001437107",
             "DISCK": "0001437107", "DISH": "0001001082", "EA": "0000712515", "ENDP": "0001593034", "ESRX": "0001532063",
             "HOLX": "0000859737", "LLTC": "0000791907", "LMCA": "0001560385", "LMCK": "0001560385", "LVNTA": "0001355096",
             "MXIM": "0000743316", "MYL": "0001623613", "NLOK": "0000849399", "SYMC": "0000849399", "PCLN": "0001075531",
             "QRTEA": "0001355096", "QVCA": "0001355096", "SGEN": "0001060736", "SHPG": "0000936402", "SPLK": "0001353283",
             "SRCL": "0000861878", "TFCF": "0001308161", "TFCFA": "0001308161", "VIAB": "0001339947", "WBA": "0001618921",
             "WFM": "0000865436", "WLTW": "0001140536", "XLNX": "0000743988", "YHOO": "0001011006"}


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def fetch(url, dst, prov, skip_existing=False):
    if os.path.exists(dst) and skip_existing:
        return open(dst, "rb").read()
    if os.path.exists(dst):
        sys.exit("REFUSED: %s exists - a cache is a photograph; use --build, or --refresh-into a new folder" % dst)
    time.sleep(0.15)
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(raw)
    prov[os.path.relpath(dst, RAW)] = dict(url=url, fetched_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                                          bytes=len(raw), sha256=sha256(raw))
    return raw


def tickers():
    t = pd.read_csv(os.path.join(ROOT, "tools", "data", "ndx_members.csv"))
    return sorted(set(t["ticker"].str.upper()))


def do_fetch():
    prov = json.load(open(PROV)) if os.path.exists(PROV) else {}
    tk = json.loads(fetch("https://www.sec.gov/files/company_tickers.json", os.path.join(RAW, "company_tickers.json"), prov))
    cik_of = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in tk.values()}
    cik_of.update(EXTRA_CIK)
    want = tickers(); unmapped = [t for t in want if t not in cik_of]
    ciks = sorted(set(cik_of[t] for t in want if t in cik_of))
    print("tickers %d, mapped %d CIKs, unmapped %d: %s" % (len(want), len(ciks), len(unmapped), " ".join(unmapped)))
    for i, cik in enumerate(ciks):
        d = json.loads(fetch("https://data.sec.gov/submissions/CIK%s.json" % cik, os.path.join(RAW, "submissions", "CIK%s.json" % cik), prov))
        for f in d["filings"].get("files", []):
            fetch("https://data.sec.gov/submissions/" + f["name"], os.path.join(RAW, "submissions", f["name"]), prov)
        if i % 25 == 0:
            print("  %d / %d" % (i + 1, len(ciks)), flush=True)
            json.dump(prov, open(PROV, "w"), indent=1)
    json.dump(dict(prov, _unmapped=unmapped), open(PROV, "w"), indent=1)


def do_fetch_extra():
    """Fetch only the hand-mapped CIKs whose submissions are not saved yet (the photographs already taken stay untouched)."""
    prov = json.load(open(PROV))
    for cik in sorted(set(EXTRA_CIK.values())):
        dst = os.path.join(RAW, "submissions", "CIK%s.json" % cik)
        if os.path.exists(dst):
            continue
        d = json.loads(fetch("https://data.sec.gov/submissions/CIK%s.json" % cik, dst, prov))
        for f in d["filings"].get("files", []):
            fetch("https://data.sec.gov/submissions/" + f["name"], os.path.join(RAW, "submissions", f["name"]), prov, skip_existing=True)
        print("  CIK%s %s" % (cik, d.get("name")), flush=True)
    prov["_unmapped"] = [t for t in prov.get("_unmapped", []) if t not in EXTRA_CIK]
    json.dump(prov, open(PROV, "w"), indent=1)


def reaction_session(acc_utc):
    """The first US regular session that starts after the acceptance time (weekday calendar; holidays are left to the
    consumer, which joins on its own session list): before 09:30 ET -> same day; after 16:00 ET -> next weekday."""
    et = acc_utc.tz_convert("US/Eastern"); d = et.normalize().tz_localize(None); mins = et.hour * 60 + et.minute
    if et.weekday() >= 5 or mins >= 960:
        d = d + pd.offsets.BDay(1)
    return d.date(), ("pre-open" if mins < 570 and et.weekday() < 5 else ("intraday" if mins < 960 and et.weekday() < 5 else "after-close"))


def build():
    prov = json.load(open(PROV))
    tk = json.load(open(os.path.join(RAW, "company_tickers.json"), "rb"))
    tick_of = {}
    for v in tk.values():
        tick_of.setdefault(str(v["cik_str"]).zfill(10), v["ticker"].upper())
    for t, c in EXTRA_CIK.items():                    # delisted names keep the ticker they had in the index
        tick_of.setdefault(c, t)
    # One company can carry several index tickers over time (FB -> META, PCLN -> BKNG, SYMC -> NLOK -> GEN) or at once (GOOG +
    # GOOGL, DISCA + DISCK, QVCA + LVNTA tracking stocks): 'ticker' is EDGAR's current one, 'ndx_tickers' every members-file
    # ticker on the same CIK - consumers join on ndx_tickers, never on ticker alone.
    cur = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in tk.values()}
    ndx_of = {}
    for t in tickers():
        c = EXTRA_CIK.get(t) or cur.get(t)
        if c:
            ndx_of.setdefault(c, set()).add(t)
    rows = []
    sub = os.path.join(RAW, "submissions")
    for fn in sorted(os.listdir(sub)):
        if not fn.startswith("CIK") or "-submissions-" in fn:
            continue
        cik = fn[3:13]; d = json.load(open(os.path.join(sub, fn), "rb"))
        blocks = [d["filings"]["recent"]] + [json.load(open(os.path.join(sub, f["name"]), "rb")) for f in d["filings"].get("files", [])]
        for b in blocks:
            for i, form in enumerate(b["form"]):
                if form in FORMS:
                    rows.append(dict(cik=cik, ticker=tick_of.get(cik, (d.get("tickers") or [""])[0]),
                                     ndx_tickers=";".join(sorted(ndx_of.get(cik, ()))), name=d.get("name"), form=form,
                                     filing_date=b["filingDate"][i], report_date=b["reportDate"][i],
                                     accepted=b["acceptanceDateTime"][i], items=b["items"][i] or "", accession=b["accessionNumber"][i]))
    F = pd.DataFrame(rows).drop_duplicates("accession").sort_values(["cik", "accepted"])
    F.to_csv(OUT_FILINGS, index=False)
    E = F[F["form"].isin(["8-K", "8-K/A"]) & F["items"].str.contains("2.02", regex=False)].copy()
    acc = pd.to_datetime(E["accepted"], utc=True)
    rs = [reaction_session(a) for a in acc]
    E["accepted_et"] = acc.dt.tz_convert("US/Eastern").dt.strftime("%Y-%m-%d %H:%M")
    E["reaction_session"] = [r[0] for r in rs]; E["timing"] = [r[1] for r in rs]
    E[["ticker", "ndx_tickers", "cik", "name", "form", "accepted_et", "reaction_session", "timing", "items", "accession"]].to_csv(OUT_EARN, index=False)
    print("filings %d rows (%d companies) -> %s" % (len(F), F["cik"].nunique(), OUT_FILINGS))
    print("earnings (8-K item 2.02) %d rows, %s .. %s; timing %s -> %s" % (len(E), E["accepted_et"].min(), E["accepted_et"].max(),
          E["timing"].value_counts().to_dict(), OUT_EARN))
    print("unmapped tickers:", prov.get("_unmapped"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--build", action="store_true"); ap.add_argument("--extra", action="store_true")
    a = ap.parse_args()
    if a.extra:
        do_fetch_extra()
    elif not a.build:
        do_fetch()
    build()
