# -*- coding: utf-8 -*-
"""SEC INSIDER TRANSACTIONS (Forms 3 / 4 / 5) - the quarterly data sets, 2006Q1 on (TV, public-data scout, MANAGER #62).

SOURCE (public, no key): https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/YYYYqN_form345.zip
Each zip holds tab-separated tables: SUBMISSION (accession, filing date, issuer CIK + ticker), REPORTINGOWNER (who, and the
relationship: director / officer / ten-percent owner), NONDERIV_TRANS (date, code, shares, price, acquired/disposed).
PHOTOGRAPH RULE: zips saved byte for byte under C:\\EdgeLog\\_research_cache\\form4\\ with URL / time / bytes / sha256 in
form4_provenance.json; a second fetch REFUSES to overwrite. CONTACT STRING: the house's neutral one, never the owner's address.

DERIVED (rebuilt from the saved photographs only), Nasdaq-100 members (tools/data/ndx_members.csv, every ticker incl. the 39
delisted ones, via the CIK map of tools/fetch_edgar_calendar.py), one row per non-derivative transaction:
  form4_ndx_all.csv.gz        EVERY transaction code (P buy, S sell, A grant, M option exercise, F tax withholding, G gift ...)
  form4_ndx_open_market.csv   the P / S rows only
columns: filing_date, accepted_et (EDGAR acceptance time, joined from the issuer's saved submissions index - the moment the
market could know it), trans_date, ndx_tickers, issuer_cik, owner_cik (the insider's own id, for per-insider histories),
owner, n_owners (joint filings keep the first owner), roles, title, code, acq_disp, shares, price, value, shares_after,
direct_indirect, timeliness, aff10b5one (10b5-1 plan box, 2023- only), form, accession.

    python tools/fetch_form4.py            # fetch every quarter not yet saved (refuses existing files) + build
    python tools/fetch_form4.py --build    # rebuild the derived CSV from the saved zips only
"""
import argparse, datetime, hashlib, io, json, os, sys, time, urllib.request, zipfile

import pandas as pd

RAW = r"C:\EdgeLog\_research_cache\form4"
EDGAR = r"C:\EdgeLog\_research_cache\edgar"
PROV = os.path.join(RAW, "form4_provenance.json")
OUT = os.path.join(RAW, "form4_ndx_open_market.csv")
OUT_ALL = os.path.join(RAW, "form4_ndx_all.csv.gz")
URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/%dq%d_form345.zip"
UA = {"User-Agent": "EdgeLog research tool edgelog-research@example.com", "Accept-Encoding": "identity"}
LAST = (2025, 2)                      # the quarter holding 2025-06-29; later quarters are lockbox-era and not fetched here


def quarters():
    y, q = 2006, 1
    while (y, q) <= LAST:
        yield y, q
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)


def do_fetch():
    os.makedirs(RAW, exist_ok=True)
    prov = json.load(open(PROV)) if os.path.exists(PROV) else {}
    for y, q in quarters():
        dst = os.path.join(RAW, "%dq%d_form345.zip" % (y, q))
        if os.path.exists(dst):
            continue                                           # already photographed: never refetched
        time.sleep(0.3)
        raw = urllib.request.urlopen(urllib.request.Request(URL % (y, q), headers=UA), timeout=300).read()
        with open(dst, "wb") as f:
            f.write(raw)
        prov[os.path.basename(dst)] = dict(url=URL % (y, q), fetched_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                                           bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        json.dump(prov, open(PROV, "w"), indent=1)
        print("  %dq%d %.1f MB" % (y, q, len(raw) / 1e6), flush=True)


def ndx_ciks():
    """issuer CIK (int) -> 'FB;META'-style list of every members-file ticker on it (same map as the EDGAR calendar)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fetch_edgar_calendar import EXTRA_CIK, tickers
    tk = json.load(open(os.path.join(EDGAR, "company_tickers.json"), "rb"))
    cur = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in tk.values()}
    out = {}
    for t in tickers():
        c = EXTRA_CIK.get(t) or cur.get(t)
        if c:
            out.setdefault(int(c), set()).add(t)
    return {c: ";".join(sorted(v)) for c, v in out.items()}


def acceptance_times(ciks):
    """accession -> EDGAR acceptance time (UTC string) for Forms 4 / 4-A, from the issuers' saved submissions photographs."""
    sub, acc = os.path.join(EDGAR, "submissions"), {}
    for c in ciks:
        fn = os.path.join(sub, "CIK%010d.json" % c)
        if not os.path.exists(fn):
            continue
        d = json.load(open(fn, "rb"))
        for b in [d["filings"]["recent"]] + [json.load(open(os.path.join(sub, f["name"]), "rb")) for f in d["filings"].get("files", [])]:
            for i, form in enumerate(b["form"]):
                if form in ("4", "4/A"):
                    acc[b["accessionNumber"][i]] = b["acceptanceDateTime"][i]
    return acc


def read(z, name):
    hit = [n for n in z.namelist() if n.upper().endswith(name)]
    return pd.read_csv(io.BytesIO(z.read(hit[0])), sep="\t", dtype=str, low_memory=False) if hit else pd.DataFrame()


def build():
    ciks = ndx_ciks(); out = []; acc = acceptance_times(ciks)
    for fn in sorted(f for f in os.listdir(RAW) if f.endswith("_form345.zip")):
        with zipfile.ZipFile(os.path.join(RAW, fn)) as z:
            S, O, T = read(z, "SUBMISSION.TSV"), read(z, "REPORTINGOWNER.TSV"), read(z, "NONDERIV_TRANS.TSV")
        if S.empty or T.empty:
            print("  %s: missing tables" % fn); continue
        S = S[pd.to_numeric(S["ISSUERCIK"], errors="coerce").isin(ciks.keys())]
        T = T[T["ACCESSION_NUMBER"].isin(S["ACCESSION_NUMBER"])]
        O = O[O["ACCESSION_NUMBER"].isin(S["ACCESSION_NUMBER"])]
        roles = O.groupby("ACCESSION_NUMBER", sort=False).agg(owner_cik=("RPTOWNERCIK", "first"), owner=("RPTOWNERNAME", "first"),
                                                              title=("RPTOWNER_TITLE", "first"), n_owners=("RPTOWNERCIK", "size"),
                                                              roles=("RPTOWNER_RELATIONSHIP", lambda x: ";".join(sorted(set(";".join(x.dropna()).split(";"))))))
        if "AFF10B5ONE" not in S:
            S = S.assign(AFF10B5ONE="")
        m = T.merge(S[["ACCESSION_NUMBER", "FILING_DATE", "ISSUERCIK", "DOCUMENT_TYPE", "AFF10B5ONE"]], on="ACCESSION_NUMBER").merge(roles, on="ACCESSION_NUMBER", how="left")
        m["ndx_tickers"] = pd.to_numeric(m["ISSUERCIK"]).map(ciks)
        out.append(m)
        print("  %s: %d rows (%d P / S)" % (fn, len(m), m["TRANS_CODE"].isin(["P", "S"]).sum()), flush=True)
    D = pd.concat(out, ignore_index=True)
    D["shares"] = pd.to_numeric(D["TRANS_SHARES"], errors="coerce"); D["price"] = pd.to_numeric(D["TRANS_PRICEPERSHARE"], errors="coerce")
    D["value"] = D["shares"] * D["price"]
    D = D.rename(columns={"FILING_DATE": "filing_date", "TRANS_DATE": "trans_date", "ISSUERCIK": "issuer_cik", "TRANS_CODE": "code",
                          "TRANS_ACQUIRED_DISP_CD": "acq_disp", "ACCESSION_NUMBER": "accession", "SHRS_OWND_FOLWNG_TRANS": "shares_after",
                          "DIRECT_INDIRECT_OWNERSHIP": "direct_indirect", "TRANS_TIMELINESS": "timeliness", "AFF10B5ONE": "aff10b5one",
                          "DOCUMENT_TYPE": "form"})
    for c in ("filing_date", "trans_date"):              # the data sets write 31-MAR-2006; consumers get ISO dates
        D[c] = pd.to_datetime(D[c], format="%d-%b-%Y", errors="coerce").dt.strftime("%Y-%m-%d")
    D["accepted_et"] = pd.to_datetime(D["accession"].map(acc), utc=True).dt.tz_convert("US/Eastern").dt.strftime("%Y-%m-%d %H:%M")
    cols = ["filing_date", "accepted_et", "trans_date", "ndx_tickers", "issuer_cik", "owner_cik", "owner", "n_owners", "roles", "title",
            "code", "acq_disp", "shares", "price", "value", "shares_after", "direct_indirect", "timeliness", "aff10b5one", "form", "accession"]
    D[cols].to_csv(OUT_ALL, index=False, compression="gzip")
    P = D[D["code"].isin(["P", "S"])]
    P[cols].to_csv(OUT, index=False)
    print("form4 rows %d (all codes %s) -> %s" % (len(D), D["code"].value_counts().head(8).to_dict(), OUT_ALL))
    print("open-market rows %d (P %d / S %d), %d companies, acceptance time on %.1f %% -> %s" % (len(P), (P["code"] == "P").sum(),
          (P["code"] == "S").sum(), P["issuer_cik"].nunique(), 100 * P["accepted_et"].notna().mean(), OUT))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--build", action="store_true"); a = ap.parse_args()
    if not a.build:
        do_fetch()
    build()
