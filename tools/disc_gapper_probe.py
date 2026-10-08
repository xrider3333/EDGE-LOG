"""The FB/META probe PREREG_pmfail_r1 section 17 asks for, for the disc_gapper photograph (manifest bac11716...).

The pull of 2026-10-06 ran without it (its manifest holds no probe row), so it runs AFTER the pull: AMENDMENT 1 of
PREREG_pmfail_r1 / PREREG_runner2_r1 discloses the order. It extends tools/rocfrontier/r5_siporb.py's probe (1Day and
5Min on 2019-01-02) to the two endpoints the photograph used - 1Min feed=sip bars and /v2/stocks/quotes feed=sip - and
asks every endpoint the same question: does FB (renamed META in June 2022) answer for 2019-01-02 exactly as META does?
One line per endpoint, "SAME MAPPING" or "DIFFERENT"; the harnesses read the log with --probe-log and refuse unless
every endpoint says SAME MAPPING. A DIFFERENT line voids the photograph for MANAGER to rule on (section 17: any other
result stops the pull).

Nothing is saved but the log (C:/EdgeLog/alpaca_cache/disc_gapper/probe_fbmeta.log; the photograph's files and
manifest are never touched). 8 requests, paced at 150 a minute and through augur_engine.alpaca_rate. Keys come from MANAGER's wrapper environment
(ALPACA_API_KEY / ALPACA_SECRET_KEY) and are never printed or logged.

    python C:/EdgeLog/manager/_scripts/with_alpaca_keys.py tools/disc_gapper_probe.py
"""
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine import alpaca_rate  # noqa: E402 - the account-wide pace every Alpaca request goes through

LOG = "C:/EdgeLog/alpaca_cache/disc_gapper/probe_fbmeta.log"
BASE = "https://data.alpaca.markets/v2/stocks/"
DAY = "2019-01-02"
PACE = 60.0 / 150.0
# endpoint -> (path, params): the photograph's own parameters (feed=sip, adjustment=raw, sort=asc) on 2019-01-02
ENDPOINTS = {
    "1Day": ("bars", {"timeframe": "1Day", "adjustment": "raw", "feed": "sip", "sort": "asc", "limit": 10,
                      "start": "2019-01-02T00:00:00Z", "end": "2019-01-02T23:59:59Z"}),
    "5Min": ("bars", {"timeframe": "5Min", "adjustment": "raw", "feed": "sip", "sort": "asc", "limit": 10,
                      "start": "2019-01-02T14:30:00Z", "end": "2019-01-02T14:34:59Z"}),
    "1Min": ("bars", {"timeframe": "1Min", "adjustment": "raw", "feed": "sip", "sort": "asc", "limit": 10,
                      "start": "2019-01-02T14:30:00Z", "end": "2019-01-02T14:34:59Z"}),
    "quotes": ("quotes", {"feed": "sip", "sort": "asc", "limit": 20,
                          "start": "2019-01-02T14:30:00Z", "end": "2019-01-02T14:30:01Z"}),
}
_last = [0.0]


def get(url, key, secret):
    for attempt in range(6):
        wait = PACE - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        alpaca_rate.wait()
        req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                                                   "User-Agent": "edgelog-disc-gapper-probe/1"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(5 * (attempt + 1))
                continue
            return e.code, body
        except Exception as ex:                                  # noqa: BLE001 - logged as status -1
            if attempt < 5:
                time.sleep(5 * (attempt + 1))
                continue
            return -1, str(ex).encode()
    return -1, b""


def served(path, sym, body):
    """the served records for one symbol, as a canonical list (the symbol key itself left out)"""
    obj = json.loads(body)
    v = obj.get(path)
    if isinstance(v, dict):
        v = v.get(sym)
    return [json.dumps(r, sort_keys=True) for r in (v or [])]


def verdict(fb, meta):
    """SAME MAPPING = both symbols served, the same records. Pure, tested."""
    if fb is None or meta is None:
        return "DIFFERENT (a request was not served)"
    if not fb and not meta:
        return "DIFFERENT (neither symbol served a record)"
    if not fb or not meta:
        return f"DIFFERENT (FB {len(fb)} records, META {len(meta)})"
    if fb != meta:
        return f"DIFFERENT (FB {len(fb)} records, META {len(meta)}, contents differ)"
    return "SAME MAPPING"


def main():
    key, secret = os.environ.get("ALPACA_API_KEY", ""), os.environ.get("ALPACA_SECRET_KEY", "")
    if not (key and secret):
        sys.exit("no keys in the environment - run through MANAGER's with_alpaca_keys.py")
    lines = [f"FB/META probe for the disc_gapper photograph (manifest bac11716...), run "
             f"{dt.datetime.now(dt.timezone.utc).isoformat()}; script sha256 "
             f"{hashlib.sha256(open(__file__, 'rb').read()).hexdigest()}; day {DAY}; no request sends asof"]
    for ep, (path, params) in ENDPOINTS.items():
        got = {}
        for sym in ("FB", "META"):
            url = BASE + path + "?" + urllib.parse.urlencode(dict(params, symbols=sym))
            st, body = get(url, key, secret)
            got[sym] = served(path, sym, body) if st == 200 else None
            first = got[sym][0] if got[sym] else None
            lines.append(f"  {ep} {sym}: status {st}, {len(got[sym]) if got[sym] is not None else 0} records, "
                         f"sha256 {hashlib.sha256(body).hexdigest()[:16]}, first {first}")
        lines.append(f"FB/META {ep} feed=sip {DAY}: {verdict(got['FB'], got['META'])}")
    text = "\n".join(lines) + "\n"
    with open(LOG, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(text, end="")
    print(f"log {LOG} sha256 {hashlib.sha256(text.encode('utf-8')).hexdigest()}")


if __name__ == "__main__":
    main()
