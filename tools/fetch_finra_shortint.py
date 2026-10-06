# -*- coding: utf-8 -*-
"""FINRA CONSOLIDATED SHORT INTEREST, 2018-06-15 .. the sealed-year cut (TV, public-data scout; MANAGER #82 for
STRATEGY-BEATING SHORTINT r1).

SOURCES (public, no account, no key):
  https://cdn.finra.org/equity/otcmarket/biweekly/shrtYYYYMMDD.csv    one pipe-delimited file per settlement date (all US
      exchange-listed AND OTC issues; columns accountingYearMonthNumber, symbolCode, issueName,
      issuerServicesGroupExchangeCode, marketClassCode, currentShortPositionQuantity, previousShortPositionQuantity,
      stockSplitFlag, averageDailyVolumeQuantity, daysToCoverQuantity, revisionFlag, changePercent, changePreviousNumber,
      settlementDate). The CDN has no listing: settlement dates are FOUND by a HEAD probe of every weekday on days 8-17 and
      24-31 of each month (a missing date answers 403); the probe answers (status, size, Last-Modified) are saved too.
  FINRA's reporting-schedule page (settlement / due / publication dates): the live page carries only the current years, so the
      2018-2025 schedules are photographed from the Internet Archive's snapshots of that page (and of its pre-2020 address).
PHOTOGRAPH RULE: every response saved byte for byte under C:\\EdgeLog\\_research_cache\\finra_shortint\\ with URL / UTC time /
bytes / sha256 (and the CDN's Last-Modified) in finra_shortint_provenance.json; a saved file is never refetched.
SEALED YEAR: a settlement file is fetched only if its PUBLICATION date (from the photographed schedule) is before 2025-06-30;
settlement dates whose publication is unknown or on/after the cut are listed, never fetched (--allow lets a later run add one
after the schedule is read).

DERIVED: finra_shortint_flat.csv  settlement_date, symbol, issue_name, exchange_code, market_code, short_interest,
         prev_short_interest, split_flag, avg_daily_volume, days_to_cover, revision_flag, source_file
         finra_shortint_manifest.json  per-file row counts by market code, totals, shas.

    python tools/fetch_finra_shortint.py probe            # find the settlement dates (HEAD only)
    python tools/fetch_finra_shortint.py schedule         # photograph the archived schedule pages
    python tools/fetch_finra_shortint.py fetch [--allow YYYYMMDD ...]
    python tools/fetch_finra_shortint.py build
"""
import argparse, datetime, hashlib, io, json, os, sys, time, urllib.error, urllib.request

import pandas as pd

RAW = r"C:\EdgeLog\_research_cache\finra_shortint"
PROV = os.path.join(RAW, "finra_shortint_provenance.json")
PROBE = os.path.join(RAW, "probe_settlement_dates.json")
URL = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt%s.csv"
UA = {"User-Agent": "EdgeLog research tool edgelog-research@example.com", "Accept-Encoding": "identity"}
START, CUT = datetime.date(2018, 6, 1), datetime.date(2025, 6, 30)
PAGES = ["finra.org/filing-reporting/regulatory-filing-systems/short-interest", "finra.org/industry/short-interest-reporting"]


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(p, default):
    return json.load(open(p)) if os.path.exists(p) else default


def req(url, method="GET"):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA, method=method), timeout=120)


def save_prov(entries):
    """merge into the provenance file on disk (never overwrite entries another run wrote meanwhile)"""
    p = load(PROV, {}); p.update(entries); json.dump(p, open(PROV, "w"), indent=1)


def candidates():
    d = START
    while d < CUT:
        if d.weekday() < 5 and (8 <= d.day <= 17 or d.day >= 24):
            yield d
        d += datetime.timedelta(days=1)


def probe():
    found = load(PROBE, {})
    for d in candidates():
        k = d.strftime("%Y%m%d")
        if k in found:
            continue
        try:
            r = req(URL % k, "HEAD"); found[k] = dict(status=r.status, bytes=int(r.headers.get("Content-Length", 0)), last_modified=r.headers.get("Last-Modified"))
        except urllib.error.HTTPError as e:
            found[k] = dict(status=e.code)
        time.sleep(0.12)
    json.dump(found, open(PROBE, "w"), indent=1)
    hits = sorted(k for k, v in found.items() if v.get("status") == 200)
    print("probed %d candidate weekdays; %d settlement files exist (%s .. %s)" % (len(found), len(hits), hits[0], hits[-1]))
    return hits


def schedule():
    prov = load(PROV, {})
    os.makedirs(os.path.join(RAW, "schedule"), exist_ok=True)
    for y in range(2018, 2026):
        for page in PAGES:
            for ts in ("%d0115" % y, "%d0215" % y, "%d0401" % y, "%d0901" % y):
                api = "https://archive.org/wayback/available?url=%s&timestamp=%s" % (page, ts)
                snap = json.loads(req(api).read()).get("archived_snapshots", {}).get("closest")
                if not snap or snap.get("status") != "200":
                    continue
                url = snap["url"]; dst = os.path.join(RAW, "schedule", "wayback_%s_%s.html" % (snap["timestamp"], page.split("/")[-1]))
                if os.path.exists(dst):
                    continue
                raw = req(url).read()
                open(dst, "wb").write(raw)
                prov[os.path.relpath(dst, RAW)] = dict(url=url, fetched_at_utc=now_utc(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), asked=ts)
                time.sleep(1.0)
    live = os.path.join(RAW, "schedule", "short-interest_page.html")
    if os.path.exists(live) and "schedule/short-interest_page.html" not in prov:
        raw = open(live, "rb").read()
        prov["schedule/short-interest_page.html"] = dict(url="https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest",
                                                         fetched_at_utc=open(live.replace(".html", ".fetched_utc")).read().strip(),
                                                         bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    save_prov(prov)
    print("schedule pages saved:", sorted(k for k in prov if k.startswith("schedule")))


def fetch(allow=()):
    found = load(PROBE, {}); prov = load(PROV, {})
    hits = sorted(k for k, v in found.items() if v.get("status") == 200)
    held = []
    for k in hits:
        # publication is ~7-8 business days after settlement: a settlement within 12 calendar days of the cut needs the
        # photographed schedule to say it was published before 2025-06-30 (pass it with --allow after reading the schedule)
        if (CUT - datetime.date(int(k[:4]), int(k[4:6]), int(k[6:]))).days <= 21 and k not in allow:
            held.append(k); continue
        dst = os.path.join(RAW, "files", "shrt%s.csv" % k)
        if os.path.exists(dst):
            continue
        r = req(URL % k); raw = r.read()
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(raw)
        prov["files/shrt%s.csv" % k] = dict(url=URL % k, fetched_at_utc=now_utc(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                            last_modified=r.headers.get("Last-Modified"))
        save_prov(prov)
        time.sleep(0.3)
    print("files saved: %d; held back pending the schedule: %s" % (sum(1 for k in prov if k.startswith("files/")), held))


MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September",
                                             "October", "November", "December"])}


def schedule_table():
    """settlement -> (due, release) from every photographed schedule page. Pages before 2020 name the release column
    'Exchange Receipt Date', later ones 'Publication Date'; each block '<YEAR> Short Interest Reporting Dates' lists triples
    settlement / due (6 p.m.) / release. A date earlier in the year than its settlement belongs to the next year."""
    import glob, html as _h, re
    rows = []
    for fn in sorted(glob.glob(os.path.join(RAW, "schedule", "*.html"))):
        t = open(fn, encoding="utf-8", errors="replace").read()
        t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
        t = re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", t)))
        blocks = [(m.start(), int(m.group(1))) for m in re.finditer(r"(20\d\d) Short Interest Reporting Dates", t)]
        for bi, (pos, year) in enumerate(blocks):
            end = blocks[bi + 1][0] if bi + 1 < len(blocks) else pos + 6000
            seg = t[pos:end]
            col = "publication" if "Publication Date" in seg[:200] else ("exchange_receipt" if "Exchange Receipt" in seg[:200] else "release")
            ds = [(MONTHS[m.group(1)], int(m.group(2))) for m in re.finditer(r"\b(%s) (\d{1,2})\b" % "|".join(MONTHS), seg)]
            for i in range(0, len(ds) - 2, 3):
                (sm, sd), (dm, dd), (rm, rd) = ds[i], ds[i + 1], ds[i + 2]
                try:
                    st = datetime.date(year, sm, sd)
                    due = datetime.date(year + (dm < sm), dm, dd); rel = datetime.date(year + (rm < sm), rm, rd)
                except ValueError:
                    continue
                if 0 <= (due - st).days <= 10 and 0 <= (rel - st).days <= 25:
                    rows.append(dict(settlement=st.isoformat(), due=due.isoformat(), release=rel.isoformat(), release_column=col,
                                     page=os.path.basename(fn)))
    S = pd.DataFrame(rows)
    if S.empty:
        return S
    agree = S.groupby("settlement")["release"].nunique()
    S = S.sort_values("page").drop_duplicates("settlement", keep="last").set_index("settlement")
    S["pages_disagree"] = agree.reindex(S.index).fillna(1).astype(int) > 1
    S.reset_index().to_csv(os.path.join(RAW, "finra_schedule_2018_2025.csv"), index=False)
    return S


def build():
    prov = load(PROV, {}); frames, counts = [], {}
    for k in sorted(p for p in prov if p.startswith("files/")):
        fn = os.path.join(RAW, k)
        d = pd.read_csv(fn, sep="|", dtype=str, keep_default_na=False)
        d["source_file"] = os.path.basename(fn)
        counts[os.path.basename(fn)] = {m: int(n) for m, n in d["marketClassCode"].value_counts().items()}
        frames.append(d)
    D = pd.concat(frames, ignore_index=True)
    D = D.rename(columns={"settlementDate": "settlement_date", "symbolCode": "symbol", "issueName": "issue_name",
                          "issuerServicesGroupExchangeCode": "exchange_code", "marketClassCode": "market_code",
                          "currentShortPositionQuantity": "short_interest", "previousShortPositionQuantity": "prev_short_interest",
                          "stockSplitFlag": "split_flag", "averageDailyVolumeQuantity": "avg_daily_volume",
                          "daysToCoverQuantity": "days_to_cover", "revisionFlag": "revision_flag"})
    cols = ["settlement_date", "symbol", "issue_name", "exchange_code", "market_code", "short_interest", "prev_short_interest",
            "split_flag", "avg_daily_volume", "days_to_cover", "revision_flag", "source_file"]
    out = os.path.join(RAW, "finra_shortint_flat.csv")
    D[cols].to_csv(out, index=False)
    sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
    S = schedule_table()
    rel = {}
    for k in counts:
        st = "%s-%s-%s" % (k[4:8], k[8:10], k[10:12])
        lm = prov.get("files/" + k, {}).get("last_modified")
        rel[k] = dict(settlement=st, release=(S.loc[st, "release"] if st in S.index else None),
                      release_column=(S.loc[st, "release_column"] if st in S.index else None), cdn_last_modified=lm)
    man = dict(built_at_utc=now_utc(), rows=len(D), files=len(counts), first=min(counts), last=max(counts), out=out, out_sha256=sha,
               schedule_rows=int(len(S)), files_with_release_date=sum(1 for v in rel.values() if v["release"]), release_by_file=rel,
               market_codes_total={m: int(n) for m, n in D["market_code"].value_counts().items()}, rows_by_file_and_market=counts,
               source_shas={k: v.get("sha256") for k, v in prov.items()})
    json.dump(man, open(os.path.join(RAW, "finra_shortint_manifest.json"), "w"), indent=1)
    print("flat: %d rows, %d files (%s .. %s), sha256 %s -> %s" % (len(D), len(counts), man["first"], man["last"], sha, out))
    print("market codes:", man["market_codes_total"])
    print("schedule rows %d; files with a photographed release date %d of %d; last file %s release %s, CDN Last-Modified %s" % (
          man["schedule_rows"], man["files_with_release_date"], len(counts), man["last"], rel[man["last"]]["release"], rel[man["last"]]["cdn_last_modified"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["probe", "schedule", "fetch", "build"])
    ap.add_argument("--allow", nargs="*", default=[]); a = ap.parse_args()
    {"probe": probe, "schedule": schedule, "build": build}.get(a.cmd, lambda: fetch(a.allow))()
