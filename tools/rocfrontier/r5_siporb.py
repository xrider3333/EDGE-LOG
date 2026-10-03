# ALPACA r1 family A - SIPORB: 5-minute opening-range breakout on each day's 20 "stocks in play" (Zarattini, Barbon & Aziz 2024,
# SSRN 4729284). Pre-registered: tools/rocfrontier/PREREG_ALPACA_R1.txt, FAMILY A (canonical sha256 = committed blob a038a85c...0ee3,
# main 2ba5b3db, + its pre-data ADDENDUM of 2026-09-30 evening -> canonical LF sha256 bda72203...f41d). Every rule, threshold, window and cost below is that file; where it is silent the choice is marked CHOICE.
#   python r5_siporb.py assets   Alpaca asset list (active + inactive) -> common-stock universe + exclusion counts
#   python r5_siporb.py daily    raw + split daily bars of the universe (500 symbols a request, resume-safe)
#   python r5_siporb.py open5    09:30-09:35 bar of each name that passes filters 1-3 on the day or within the next 14 sessions
#   python r5_siporb.py min1     1-minute bars: each day's top-20, plus every filtered name on WF days (raw twin); estimate first
#   python r5_siporb.py A        replication + Stage A + A2, PRE-LOCKBOX ONLY (inputs cut to dates < 2025-06-30 before anything is computed)
#   python r5_siporb.py B        Stage B (lockbox, once) - refuses unless A2 passed under this exact file + half-day list; `B --gaps-ok` only after a re-pull left the same 1-minute gaps
# The pulls need the owner's Alpaca keys (env ALPACA_API_KEY / ALPACA_SECRET_KEY) and write only to the research cache, never a library master.
# Order: assets, daily, open5, `min1 top`, A (replication check runs on that alone), `min1 twin` (the big one), A again, B only after an A2 pass.
#   python r5_siporb.py probe    ~15 real requests (auth, the FB/META renamed-ticker test: do the 5-minute and the daily requests answer for the same
#                                symbols?, the split factor, symbols per request) - run once after `assets`. No request sends asof: every pull
#                                uses Alpaca's default (today's names), so daily and intraday bars are keyed by the same symbols (prereg addendum 3)
#   python r5_siporb.py smoke [dir]   offline self-test on synthetic bars through a fake transport - no network, no keys (hidden; the dir's name must contain 'smoke')
# pre-run review fixes 2026-10-03 (half-day cut, read-before-flag, no spec change)
# pre-run review round 2, 2026-10-03: Stage A stamps this file's sha256 + the half-day list; B refuses (before the flag) if either changed
import hashlib, json, os, re, sys, time
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("EDGELOG_ROOT", os.path.dirname(os.path.dirname(HERE))); sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from import_alpaca_stocks import EARLY_CLOSE_DATES, EARLY_CLOSE_MIN    # NYSE 13:00 half days: the shared loader's one list (not copied here)

TS = pd.Timestamp
OUT = os.environ.get("EDGELOG_ALPACA_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\alpaca_r1")   # results, outside git
CACHE = os.environ.get("EDGELOG_ALPACA_CACHE", r"C:\EdgeLog\alpaca_cache")                     # raw research pulls
BOOK = os.path.join(os.path.dirname(OUT), "r4", "book463_daily.csv")
D0, D1 = "2015-11-01T00:00:00Z", "2026-06-30T23:59:59Z"      # daily pull (Nov 2015 = warm-up for the 14-session windows)
END = TS("2026-07-01")                                        # exclusive: the pulls hold bars through 2026-06-30
O5_0, O5_1, M1_0 = TS("2015-12-01"), TS("2026-06-30"), TS("2016-01-04")
REP0, REP1, WF0, LB0, LB1 = (TS(x) for x in ("2016-01-04", "2023-12-30", "2024-01-02", "2025-06-30", "2026-07-01"))   # half-open; REP = ..2023-12-29
LBY = (TS("2026-06-30") - LB0).days / 365.25    # LB = 2025-06-30 .. 2026-06-30 INCLUSIVE with the frontier's years (reproduces 164.76 / 4.150)
LOOK, TOP, RVMIN = 14, 20, 1.0
PX_MIN, VOL_MIN, ATR_MIN = 5.0, 1_000_000.0, 0.50
SLOT, RISK, LEV, STOPF = 5000.0, 0.01, 4.0, 0.10               # $100k = 20 slots; 1% of the slot at risk; 4x slot cap; stop = 10% of ATR
COMM, SLIP, SLIP_STRESS = 0.0035, 0.01, 0.02                   # $ per share per side
NMIN, F0, F1 = 390, 5, 388                                     # 1-minute bars 09:30..15:59; fills allowed on bars 09:35..15:58
# CHOICE (pre-data, clarifies prereg lines 27/30): "until 15:59" / "the 15:59 bar" = the session's last regular bar. On an NYSE half day
# (EARLY_CLOSE_DATES) every 1-minute bar from 13:00 on is an extended-hours print and is dropped: fills end on the 12:58 bar, exit = the 12:59 close.
# Nothing else assumes a closing minute: open5 reads only the 09:30 bar and filters 1-3 read Alpaca's daily bars as served.
BOOK_WF, BOOK_LB = (187.79, 4.428), (164.76, 4.150)            # BOOK #463 ROC@30k, Sortino (prereg)
CS = (0.5, 1.0, 2.0)
RULES = {"rep_sharpe": 1.0, "n": 100, "roc": 15.0, "pf": 1.10, "t": 2.0, "months": 0.60, "twin": True, "stress": True, "exbig": True,
         "a2_alone": 187.79, "a2_book": 197.2, "a2_sort": 4.428, "b_n": 50, "b_roc": 164.76, "b_sort": 4.150, "cov": 0.98}
CHECK_BOOK = True       # refuse to judge if the book file does not reproduce #463's prereg numbers; a real run always checks (only smoke() may switch it, see SIPORB_BOOK_CHECK there)
BARS_URL, ASSETS_URL = "https://data.alpaca.markets/v2/stocks/bars", "https://paper-api.alpaca.markets/v2/assets"
EXCH = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}
# CHOICE: keywords match as whole words (\b), case-insensitive - a substring match would drop Netflix ("etf") and Ultragenyx ("ultra")
# CHOICE (logged, kept as is): known false positives - real common stocks dropped: IVZ, PFBC, APTS, DJCO, UPL, UCTT, BSF (name) and BRK.B (dot)
BAD_NAME = re.compile(r"\b(?:ETFs?|ETNs?|Exchange Traded|Funds?|iShares|SPDR|ProShares|Direxion|Vanguard|Invesco|Leveraged|Daily|Ultra|2X|3X"
                      r"|Bull|Bear|Notes|Warrants?|Units|Rights|Preferred|Depositary Shares Representing)\b", re.I)
PACE, BACKOFF, RETRY, URL_MAX, DAILY_BATCH, SMOKE, BAD = 0.31, 20, 10, 6500, 500, False, []
TRCOLS = ["date", "symbol", "side", "rv", "atr", "entry", "exit", "shares", "gross", "fill_min", "exit_min", "stopped", "pnl", "pnl_stress"]
try:
    import pyarrow  # noqa: F401
    EXT = ".parquet"
except ImportError:
    EXT = ".csv.gz"


# ------------------------------------------------------------------ transport (keys required; smoke swaps _http_get)
def _http_get(url, heads, params):
    if SMOKE:
        raise SystemExit("network call during smoke")
    import requests
    from augur_engine import alpaca_rate
    alpaca_rate.wait()            # one account-wide pace: five lanes share the 200/min cap
    return requests.get(url, headers=heads, params=params, timeout=120)


def keys():
    if SMOKE:
        return "smoke", "smoke"
    from import_alpaca_stocks import load_keys            # the shared loader's key lookup (env first)
    key, secret = load_keys()
    if not (key and secret):
        raise SystemExit("No Alpaca keys yet - the owner saves ALPACA_API_KEY / ALPACA_SECRET_KEY (ALPACA_STAGE_R1.md).")
    return key, secret


def _get(url, params, key, secret):
    """one GET, r5_nqbrd's pacing: 0.31 s after a good reply, 429 -> sleep 20 s and retry, 401/403 -> stop"""
    heads, tries = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}, 0
    while True:
        try:
            r = _http_get(url, heads, params)
        except OSError as e:                                # dropped connection / timeout: a few retries, then stop (the pulls resume)
            tries += 1
            if tries > 6:
                raise
            print(f"  {type(e).__name__} - retry {tries}", flush=True); time.sleep(RETRY); continue
        if r.status_code == 429:
            time.sleep(BACKOFF); continue
        if r.status_code in (401, 403):
            raise SystemExit(f"AUTH FAILED ({r.status_code}) - check the Alpaca keys")
        if r.status_code >= 500:
            tries += 1
            if tries > 6:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            time.sleep(RETRY); continue
        if r.status_code in (400, 422):
            raise BadRequest(f"HTTP {r.status_code}: {r.text[:300]}")
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        time.sleep(PACE)                                    # ~195 requests a minute, under the free plan's 200
        return r.json()


class BadRequest(Exception):
    pass


def fetch_safe(symbols, *a, **k):
    """fetch_bars, but a 400 that names a symbol is bisected down to the offending symbol(s): logged in bad_symbols.txt and skipped (max 50 a run)"""
    try:
        return fetch_bars(symbols, *a, **k)
    except BadRequest as e:
        if "symbol" not in str(e).lower():
            raise
        if len(symbols) > 1:
            h = len(symbols) // 2
            return fetch_safe(symbols[:h], *a, **k) + fetch_safe(symbols[h:], *a, **k)
        os.makedirs(path_of(), exist_ok=True)
        open(path_of("bad_symbols.txt"), "a").write(f"{symbols[0]}\t{a[0]}\t{a[1]}\t{str(e)[:160]}\n")      # symbol, timeframe, window start, the reply
        BAD.append(symbols[0])
        if len(BAD) > 50:
            raise RuntimeError("more than 50 symbols rejected in one run - check bad_symbols.txt")
        return []


def fetch_bars(symbols, tf, start, end, adj, key, secret):
    """multi-symbol bars (SIP feed), paged on next_page_token -> [(symbol, t, o, h, l, c, v)].  No asof, ever: Alpaca's default mapping (today's
    names) is the one symbol mapping of every pull, daily and intraday alike (prereg addendum 3)"""
    rows, token = [], None
    while True:
        p = {"symbols": ",".join(symbols), "timeframe": tf, "start": start, "end": end, "limit": 10000, "adjustment": adj,
             "feed": "sip", "sort": "asc"}
        if token:
            p["page_token"] = token
        js = _get(BARS_URL, p, key, secret)
        for s, bs in (js.get("bars") or {}).items():
            rows += [(s, b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in bs]
        token = js.get("next_page_token")
        if not token:
            return rows


def utc(day, hh, mm, ss=0):
    return TS(f"{day} {hh:02d}:{mm:02d}:{ss:02d}", tz="US/Eastern").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def chunk_syms(syms, n_max, url_max=None):
    """split a symbol list so the request URL stays short (a comma travels as %2C)"""
    url_max = url_max or URL_MAX
    out, cur, ln = [], [], 0
    for s in syms:
        add = len(s) + 3
        if cur and (len(cur) >= n_max or ln + add > url_max):
            out.append(cur); cur, ln = [], 0
        cur.append(s); ln += add
    return out + ([cur] if cur else [])


def shown(day):
    return f"{day:%Y-%m-%d}" if day < LB0 else "lockbox-day"     # progress lines never print a lockbox date


# ------------------------------------------------------------------ cache files (parquet, csv.gz if pyarrow is missing)
def path_of(*p):
    return os.path.join(CACHE, "siporb", *p)


def have(base):
    return os.path.exists(base + ".parquet") or os.path.exists(base + ".csv.gz")


def save_df(df, base):
    os.makedirs(os.path.dirname(base), exist_ok=True)
    tmp = base + EXT + ".tmp"                               # write then rename: a killed pull never leaves a half file that counts as done
    if EXT == ".parquet":
        df.to_parquet(tmp, index=False, compression="zstd")
    else:
        df.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, base + EXT)


def load_df(base):
    if os.path.exists(base + ".parquet"):
        return pd.read_parquet(base + ".parquet")
    return pd.read_csv(base + ".csv.gz", keep_default_na=False, na_values=[""])   # ticker "NA" is not a missing value


def list_days(kind, t_end):
    """day files of one cache folder dated < t_end (names only - nothing is read)"""
    d = path_of(kind)
    cut = f"{t_end:%Y-%m-%d}"
    return sorted({f[:10] for f in os.listdir(d) if f.endswith((".parquet", ".csv.gz")) and f[:10] < cut}) if os.path.isdir(d) else []


def need_files(kind, days):
    miss = [d for d in days if not have(path_of(kind, f"{d:%Y-%m-%d}"))]
    if miss:
        raise SystemExit(f"{kind}: {len(miss)} of {len(days)} days not pulled yet (first {shown(miss[0])}) - run that pull first")


def frame_daily(rows):
    df = pd.DataFrame(rows, columns=["symbol", "t", "o", "h", "l", "c", "v"])
    df["date"] = pd.to_datetime(df["t"].astype(str).str.slice(0, 10), format="%Y-%m-%d")     # daily bars are stamped at ET midnight
    df = df.astype({"o": float, "h": float, "l": float, "c": float, "v": "int64"})
    return df[["symbol", "date", "o", "h", "l", "c", "v"]]


def frame_min(rows):
    df = pd.DataFrame(rows, columns=["symbol", "t", "o", "h", "l", "c", "v"])
    et = pd.to_datetime(df["t"], utc=True).dt.tz_convert("US/Eastern")
    df["m"] = (et.dt.hour * 60 + et.dt.minute).astype("int16")                              # minute of the ET day (09:30 = 570)
    df = df.astype({"o": float, "h": float, "l": float, "c": float, "v": "int64"})
    return df[["symbol", "m", "o", "h", "l", "c", "v"]].drop_duplicates(["symbol", "m"])


# ------------------------------------------------------------------ assets
def why_not(sym, name, exch):
    if exch.upper() not in EXCH:
        return "exchange"
    if "." in sym or "/" in sym:
        return "symbol:dot_slash"
    if len(sym) >= 5 and sym.endswith(("WS", "W", "U", "R")):
        return "symbol:suffix"
    m = BAD_NAME.search(name or "")
    return f"name:{m.group(0).lower()}" if m else None


def assets():
    """us_equity assets, status active AND inactive (delisted names where Alpaca has them) -> common-stock universe"""
    key, secret = keys()
    rows = []
    for st in ("active", "inactive"):
        for a in _get(ASSETS_URL, {"status": st, "asset_class": "us_equity"}, key, secret):
            rows.append({"symbol": a.get("symbol") or "", "name": a.get("name") or "", "exchange": a.get("exchange") or "",
                         "status": a.get("status") or st, "tradable": a.get("tradable"), "shortable": a.get("shortable"),
                         "easy_to_borrow": a.get("easy_to_borrow")})
    df = pd.DataFrame(rows)
    df["why"] = [why_not(s, n, e) for s, n, e in zip(df["symbol"], df["name"], df["exchange"])]
    keep = df[df["why"].isna()].drop(columns="why")
    ex = df[df["why"] == "exchange"]                                                        # survivorship visibility: today's exchange decides
    cnt = {"total": int(len(df)), "kept": int(len(keep)), "kept_by_status": {k: int(v) for k, v in keep["status"].value_counts().items()},
           "excluded_by_reason": {k: int(v) for k, v in Counter(df["why"].dropna()).most_common()},
           "excluded_exchange_by_status": {st: {(e or "(blank)"): int(n) for e, n in g["exchange"].value_counts().items()} for st, g in ex.groupby("status")}}
    os.makedirs(path_of(), exist_ok=True)
    keep.to_csv(path_of("assets.csv"), index=False)
    df[df["why"].notna()].to_csv(path_of("assets_excluded.csv"), index=False)              # audit: what each rule removed
    for p in (path_of("assets_counts.json"), os.path.join(OUT, "siporb_assets_counts.json")):
        os.makedirs(os.path.dirname(p), exist_ok=True); json.dump(cnt, open(p, "w"), indent=1)
    print(json.dumps(cnt), flush=True)
    print("excluded by exchange (today's listing), by status: " + ", ".join(f"{st} {sum(v.values()):,}" for st, v in cnt["excluded_exchange_by_status"].items())
          + " - an inactive name now on OTC / blank is dropped for its whole listed history (survivorship; see assets_excluded.csv)", flush=True)


def universe():
    if not os.path.exists(path_of("assets.csv")):
        raise SystemExit("run `assets` first")
    return sorted(pd.read_csv(path_of("assets.csv"), dtype=str, keep_default_na=False)["symbol"].unique())


# ------------------------------------------------------------------ daily bars
def consolidate(kind, bases):
    final = path_of(f"daily_{kind}")
    if EXT == ".parquet":
        import pyarrow as pa, pyarrow.parquet as pq
        sch = pa.schema([("symbol", pa.string()), ("date", pa.timestamp("ns")), ("o", pa.float64()), ("h", pa.float64()),
                         ("l", pa.float64()), ("c", pa.float64()), ("v", pa.int64())])
        with pq.ParquetWriter(final + ".parquet.tmp", sch, compression="zstd") as w:     # part by part: never the whole table in memory
            for b in bases:
                w.write_table(pq.read_table(b + ".parquet").select(sch.names).cast(sch))
        os.replace(final + ".parquet.tmp", final + ".parquet")
    else:
        pd.concat([load_df(b) for b in bases]).to_csv(final + ".csv.gz", index=False, compression="gzip")


def daily():
    """raw AND split-adjusted daily bars, 2015-11-01 -> 2026-06-30; one file per batch, so a killed run resumes at the next batch"""
    key, secret = keys()
    batches = chunk_syms(universe(), DAILY_BATCH, 10 ** 9)
    print(f"daily: {sum(map(len, batches)):,} symbols in {len(batches)} batches x 2 adjustments (~2,000 requests each on the full universe)", flush=True)
    for adj in ("raw", "split"):
        bases, fetched = [], False
        for k, b in enumerate(batches):
            base = path_of("daily_parts", f"{adj}_{hashlib.sha1(','.join(b).encode()).hexdigest()[:12]}")
            bases.append(base)
            if have(base):
                continue
            t0 = time.time()
            df = frame_daily(fetch_safe(b, "1Day", D0, D1, adj, key, secret))
            save_df(df, base); fetched = True
            print(f"  {adj} batch {k + 1}/{len(batches)}: {len(df):,} bars, {time.time() - t0:.0f}s", flush=True)
        if fetched or not have(path_of(f"daily_{adj}")):
            consolidate(adj, bases)
            print(f"  daily_{adj}{EXT} written", flush=True)


# ------------------------------------------------------------------ universe filters 1-3 on the RAW daily bars, Relative Volume, selection
def roll14(a):
    """mean of the PREVIOUS 14 sessions, NaN unless all 14 are present"""
    return pd.DataFrame(a).rolling(LOOK, min_periods=LOOK).mean().shift(1).to_numpy()


def read_long(kind, t_end):
    """daily bars of one adjustment, cut to date < t_end AT READ TIME (before anything is computed)"""
    base = path_of(f"daily_{kind}")
    if not have(base):
        raise SystemExit(f"daily_{kind} not found - run `daily` first")
    if os.path.exists(base + ".parquet"):
        import pyarrow.parquet as pq
        df = pq.read_table(base + ".parquet", filters=[("date", "<", t_end.to_pydatetime())], read_dictionary=["symbol"]).to_pandas()
    else:
        df = load_df(base); df["date"] = pd.to_datetime(df["date"]); df = df[df["date"] < t_end]
    if len(df) and not df["date"].max() < t_end:            # belt and braces: nothing on/after the cut is ever in memory
        raise SystemExit(f"daily_{kind}: input not cut - refused")
    df["symbol"] = df["symbol"].astype("category")
    return df


class Data:
    """filters 1-3 on raw daily bars and (open5=True) the 09:30 bar + Relative Volume, on the market calendar of the daily data"""
    def __init__(self, t_end, open5=True):
        self.t_end = t_end
        raw, spl = read_long("raw", t_end), read_long("split", t_end)
        if not (len(raw) and len(spl) and raw["date"].max() < t_end and spl["date"].max() < t_end):
            raise SystemExit("daily bars empty or not cut - refused")
        cnt = raw.groupby("date").size()
        self.days = days = pd.DatetimeIndex(cnt.index[cnt >= max(3, 0.25 * cnt.median())])   # sessions = dates most names have a bar on
        # a name that never trades above $5 or never 1M shares in a day cannot pass filters 1-2 on any day: dropped here, no result changes
        g = raw.groupby("symbol", observed=True).agg(o=("o", "max"), v=("v", "max"))
        self.syms = syms = np.array(sorted(g.index[(g["o"] > PX_MIN) & (g["v"] >= VOL_MIN)].astype(str)))
        S, T, sidx = len(syms), len(days), pd.Index(syms)

        def axes(df):
            m = sidx.get_indexer(df["symbol"].cat.categories.astype(str))[df["symbol"].cat.codes.to_numpy()]
            d = days.get_indexer(pd.DatetimeIndex(df["date"]))
            ok = (m >= 0) & (d >= 0)
            return d[ok], m[ok], ok

        def fill(df, col, ax):
            a = np.full((T, S), np.nan); a[ax[0], ax[1]] = df[col].to_numpy(float)[ax[2]]; return a

        ar, asp = axes(raw), axes(spl)
        O, H, L, C, V = (fill(raw, c, ar) for c in "ohlcv")
        Os = fill(spl, "o", asp)
        with np.errstate(invalid="ignore", divide="ignore"):
            Cp = np.vstack([np.full((1, S), np.nan), C[:-1]])
            TR = np.maximum(H, Cp) - np.minimum(L, Cp)                               # true range, raw bars, needs the prior session's close
            F = O / Os                                                               # raw / split-adjusted OPEN = the split factor (prereg addendum 4: known at 09:30, unlike the close)
            Ff = pd.DataFrame(F).ffill().to_numpy()
            self.chg = chg = np.zeros((T, S), bool)
            chg[1:] = np.abs(F[1:] / Ff[:-1] - 1.0) > 0.01                          # factor moved > 1% since the last session = a split on that session
            # CHOICE: a split on any session in [t-14, t] excludes day t (the prereg's "inside the 14-session look-back" plus the day itself,
            # whose raw open is on the new basis while ATR/volume are on the old one; t-14 is included because TR of t-14 uses the close of t-15)
            self.sw = sw = pd.DataFrame(chg.astype(np.float32)).rolling(LOOK + 1, min_periods=1).max().to_numpy() > 0
            self.atr, v14 = roll14(TR), roll14(V)                                    # CHOICE: all 15 sessions (14 TRs + the prior close) must exist
            self.P = (O > PX_MIN) & (v14 >= VOL_MIN) & (self.atr > ATR_MIN) & ~sw    # filters 1-3
        self.Od = O
        # names to pull a 09:30 bar for on day s: pass filters 1-3 on any of sessions s .. s+14 (so every RV denominator exists)
        self.need = pd.DataFrame(self.P.astype(np.float32)).iloc[::-1].rolling(LOOK + 1, min_periods=1).max().iloc[::-1].to_numpy() > 0
        self.t_days = len(days)
        cov = float(np.isfinite(Os).any(axis=0).mean())
        print(f"universe: {S:,} symbols x {T:,} sessions ({days[0]:%Y-%m-%d} .. {shown(days[-1])}); symbols with split bars {cov:.1%}", flush=True)
        if cov < 0.98:
            print("  WARNING: split-adjusted bars missing for some symbols - splits on them cannot be detected; re-run `daily`", flush=True)
        del H, L, C, V, Cp, TR, F, Ff, Os, raw, spl
        if open5:
            self._open5()

    def _open5(self):
        T, S, sidx = len(self.days), len(self.syms), pd.Index(self.syms)
        self.o5days = list_days("open5", self.t_end)         # day files < t_end are chosen by NAME before any is read
        A = {c: np.full((T, S), np.nan) for c in "ohlcv"}
        for day in self.o5days:
            i = self.days.get_indexer([TS(day)])[0]
            if i < 0:
                continue
            df = load_df(path_of("open5", day))
            m = sidx.get_indexer(df["symbol"].astype(str)); ok = m >= 0
            for c in "ohlcv":
                A[c][i, m[ok]] = df[c].to_numpy(float)[ok]
        self.O5, self.H5, self.L5, self.C5, self.V5 = (A[c] for c in "ohlcv")
        den = roll14(self.V5)                                # mean 09:30-09:35 volume of the previous 14 sessions, all 14 present
        with np.errstate(invalid="ignore", divide="ignore"):
            self.RV = np.where(den > 0, self.V5 / den, np.nan)

    def top20(self, i):
        """filters 1-4, then the 20 highest Relative Volume (ties: symbol order)"""
        with np.errstate(invalid="ignore"):
            ok = np.flatnonzero(self.P[i] & (self.RV[i] >= RVMIN))
        return ok[np.lexsort((ok, -self.RV[i][ok]))][:TOP]


# ------------------------------------------------------------------ pulls that need the daily bars
def open5():
    """the 09:30-09:35 ET 5-minute bar of every name that passes filters 1-3 on the day or on any of the next 14 sessions"""
    key, secret = keys()
    D = Data(END, open5=False)
    days = [d for d in D.days if O5_0 <= d <= O5_1]
    todo = [d for d in days if not have(path_of("open5", f"{d:%Y-%m-%d}"))]
    names = lambda d: D.syms[D.need[D.days.get_loc(d)]]
    est = sum(len(chunk_syms(names(d), 10 ** 9)) for d in todo)
    print(f"open5: {len(days):,} days, {len(todo):,} to pull, ~{est:,} requests (>= {est * PACE / 60:.0f} min at the pacing alone, plus response time)", flush=True)
    for n, d in enumerate(todo):
        day, rows, nm = f"{d:%Y-%m-%d}", [], names(d)
        for ch in chunk_syms(nm, 10 ** 9):
            rows += fetch_safe(ch, "5Min", utc(day, 9, 30), utc(day, 9, 34, 59), "raw", key, secret)
        df = frame_min(rows); df = df[df["m"] == 570].drop(columns="m")                 # the 09:30 bar only
        save_df(df, path_of("open5", day))
        if n % 100 == 0:
            print(f"  {shown(d)} {len(nm)} names asked, {len(df)} bars", flush=True)


def min1(mode="both"):
    """1-minute bars 09:30-16:00: the day's top-20 (every day 2016-01-04 -> 2026-06-30) and, for the raw twin, every name passing
    filters 1-3 on WF days 2024-01-02 -> 2025-06-29.  `min1 est` prints the estimate only."""
    key, secret = keys()
    D = Data(END, open5=True)
    need_files("open5", [d for d in D.days if O5_0 <= d <= O5_1])
    top_days = [d for d in D.days if M1_0 <= d <= O5_1 and not have(path_of("min1_top", f"{d:%Y-%m-%d}"))]
    twin_days = [d for d in D.days if WF0 <= d < LB0 and not have(path_of("min1_twin", f"{d:%Y-%m-%d}"))]
    twin = lambda d: D.syms[D.P[D.days.get_loc(d)]]
    sizes = [len(twin(d)) for d in twin_days]
    n_tw = sum(-(-k * NMIN // 10000) + len(chunk_syms(twin(d), 10 ** 9)) for d, k in zip(twin_days, sizes))    # bars / 10,000 a page + a partial page per chunk
    avg = np.mean(sizes) if sizes else 0
    print(f"min1 estimate: top-20 {len(top_days):,} requests (>= {len(top_days) * PACE / 60:.0f} min at the pacing alone) + raw twin {n_tw:,} requests over "
          f"{len(twin_days)} WF days, {avg:.0f} names a day on average (>= {n_tw * PACE / 60:.0f} min); total ~{len(top_days) + n_tw:,} requests, plus response time", flush=True)
    if mode == "est":
        return
    for kind, days in (("top", top_days if mode in ("both", "top") else []), ("twin", twin_days if mode in ("both", "twin") else [])):
        for n, d in enumerate(days):
            i, day, rows = D.days.get_loc(d), f"{d:%Y-%m-%d}", []
            nm = D.syms[D.top20(i)] if kind == "top" else twin(d)
            for ch in chunk_syms(nm, 10 ** 9):
                rows += fetch_safe(ch, "1Min", utc(day, 9, 30), utc(day, 15, 59, 59), "raw", key, secret)
            df = frame_min(rows); df = df[(df["m"] >= 570) & (df["m"] < 960)]
            save_df(df, path_of(f"min1_{kind}", day))
            if n % 50 == 0:
                print(f"  min1_{kind} {shown(d)}: {len(nm)} names, {len(df):,} bars ({n + 1}/{len(days)})", flush=True)


# ------------------------------------------------------------------ the pre-registered walk on 1-minute bars
def dense(bars, names):
    """(n, 390) open/high/low/close, rows = names, columns = minutes from 09:30, NaN = no bar (no trade that minute)"""
    r = pd.Index(names).get_indexer(bars["symbol"].astype(str))
    m = bars["m"].to_numpy(int) - 570
    ok = (r >= 0) & (m >= 0) & (m < NMIN)
    out = []
    for c in "ohlc":
        a = np.full((len(names), NMIN), np.nan); a[r[ok], m[ok]] = bars[c].to_numpy(float)[ok]; out.append(a)
    with np.errstate(invalid="ignore"):
        bad = np.zeros(out[0].shape, bool)
        for a in out:
            bad |= ~(a > 0)
    for a in out:
        a[bad] = np.nan
    return out


def session_bars(bars, day):
    """the day's regular-session 1-minute bars and the last bar a stop may fill on (column): 15:58, or 12:58 on an NYSE half day (CHOICE above)"""
    if f"{day:%Y-%m-%d}" in EARLY_CLOSE_DATES:
        return bars[bars["m"] < EARLY_CLOSE_MIN], EARLY_CLOSE_MIN - 570 - 2
    return bars, F1


def simulate(O, H, L, C, side, E, atr, f1=F1):
    """entry stop E (buy stop at the first bar's high / sell stop at its low) live on bars 09:35-15:58 (f1 = 12:58 on a half day); fill at the stop or
    the bar's open if it opens through; protective stop 10% of ATR from the fill, assumed hit if the fill bar also reaches it; else exit at the close
    of the last bar (the session's bars only: session_bars cuts a half day at 13:00)"""
    n, ar, col = len(side), np.arange(len(side)), np.arange(NMIN)
    lng = side > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        reach = np.where(lng[:, None], H >= E[:, None], L <= E[:, None]) & ((col >= F0) & (col <= f1))[None, :]
        got = reach.any(axis=1)
        i = reach.argmax(axis=1)                                                     # first bar that reaches the entry stop
        oi = O[ar, i]
        fill = np.where(lng, np.maximum(oi, E), np.minimum(oi, E))                  # opened through the stop -> the open
        dist = STOPF * atr
        ps = np.where(lng, fill - dist, fill + dist)
        hit0 = np.where(lng, L[ar, i] <= ps, H[ar, i] >= ps)                        # fill bar: conservative, stopped at the stop price
        touch = np.where(lng[:, None], L <= ps[:, None], H >= ps[:, None]) & (col[None, :] > i[:, None])
        hit1 = touch.any(axis=1)
        j = touch.argmax(axis=1)                                                     # later bars: opened through -> open, else the stop
        oj = O[ar, j]
        last = NMIN - 1 - (~np.isnan(C))[:, ::-1].argmax(axis=1)                     # 15:59 bar (12:59 on a half day), else the last bar before it
        px = np.where(hit0, ps, np.where(hit1, np.where(lng, np.minimum(oj, ps), np.maximum(oj, ps)), C[ar, last]))
        sh = np.floor(np.minimum(RISK * SLOT / dist, LEV * SLOT / fill) + 1e-9)     # 1% of the slot / stop distance, or 4x slot / price; rounded down
    ok = got & (sh >= 1)
    return {"ok": ok, "entry": fill, "exit": px, "shares": np.where(ok, sh, 0), "fill_min": 570 + i,
            "exit_min": 570 + np.where(hit0, i, np.where(hit1, j, last)), "stopped": hit0 | hit1,
            "gross": np.where(ok, side * (px - fill) * sh, 0.0)}


def empty_tr():
    return pd.DataFrame({c: pd.Series(dtype="datetime64[ns]" if c == "date" else object if c == "symbol" else float) for c in TRCOLS})


def orders(D, i, cols):
    """the names of `cols` that get an order on session i -> (cols, side, stop): close > open -> buy stop at the first bar's high,
    close < open -> sell stop at its low; equal (or no first bar) -> no order, the slot stays empty"""
    o, h, l, c = (a[i, cols] for a in (D.O5, D.H5, D.L5, D.C5))
    with np.errstate(invalid="ignore"):
        side = np.sign(c - o)
    k = np.flatnonzero((side == 1) | (side == -1))
    return cols[k], side[k], np.where(side[k] > 0, h[k], l[k])


def min1_bars(D, i, kind):
    """session i's 1-minute file (min1_top / min1_twin), cut to the regular session -> (bars, last fill column)"""
    day = D.days[i]
    if not day < D.t_end:
        raise SystemExit("day outside the cut - refused")
    return session_bars(load_df(path_of(f"min1_{kind}", f"{day:%Y-%m-%d}")), day)


def day_trades(D, i, cols, kind):
    """orders and simulated fills for the names `cols` (columns of D) on session i; kind = top (A1) or twin
    -> (trades or None, order-names with no 1-minute bar in the day's file: they cannot fill, so they are counted, not hidden)"""
    cols, side, E = orders(D, i, cols)
    if not len(cols):
        return None, []
    bars, f1 = min1_bars(D, i, kind)
    names = D.syms[cols]
    miss = sorted(set(names) - set(bars["symbol"].astype(str)))
    O, H, L, C = dense(bars, names)
    r = simulate(O, H, L, C, side, E, D.atr[i, cols], f1)
    ok = r["ok"]
    if not ok.any():
        return None, miss
    return pd.DataFrame({"date": D.days[i], "symbol": names[ok], "side": side[ok].astype(int), "rv": D.RV[i, cols][ok], "atr": D.atr[i, cols][ok],
                         "entry": r["entry"][ok], "exit": r["exit"][ok], "shares": r["shares"][ok].astype(int), "gross": r["gross"][ok],
                         "fill_min": r["fill_min"][ok], "exit_min": r["exit_min"][ok], "stopped": r["stopped"][ok]}), miss


def run(D, t0, t1, kind):
    """every trade of sessions [t0, t1): kind top = A1 (20 highest RV among filters 1-4), twin = every name passing filters 1-3
    -> (trades, [(day, symbol)] of order-names with no 1-minute bars)"""
    parts, miss = [], []
    for day in D.days[(D.days >= t0) & (D.days < t1)]:
        i = D.days.get_loc(day)
        cols = D.top20(i) if kind == "top" else np.flatnonzero(D.P[i])
        t, m = day_trades(D, i, cols, kind) if len(cols) else (None, [])
        miss += [(day, s) for s in m]
        if t is not None:
            parts.append(t)
    tr = pd.concat(parts, ignore_index=True) if parts else empty_tr()
    tr["pnl"] = tr["gross"] - tr["shares"] * 2 * (COMM + SLIP)                       # both sides
    tr["pnl_stress"] = tr["gross"] - tr["shares"] * 2 * (COMM + SLIP_STRESS)
    return tr, miss


def min1_gaps(D, t0, t1, kind="top"):
    """order-names of sessions [t0, t1) with no 1-minute bar in their day's file (Stage B runs it BEFORE the one read; nothing is simulated)"""
    miss = []
    for day in D.days[(D.days >= t0) & (D.days < t1)]:
        i = D.days.get_loc(day)
        cols = orders(D, i, D.top20(i) if kind == "top" else np.flatnonzero(D.P[i]))[0]
        if len(cols):
            miss += [(day, s) for s in sorted(set(D.syms[cols]) - set(min1_bars(D, i, kind)[0]["symbol"].astype(str)))]
    return miss


# ------------------------------------------------------------------ statistics (r5_nqbrd's ddmax / so / book)
def ddmax(x):
    q = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(q) else 0.0


def so(x):
    x = np.asarray(x, float)
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)) if len(x) else 0.0
    return float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def stats(tr, days, t0, t1, yrs=None):
    """P&L by day = sum of that day's trades, zeros on the stretch's other sessions; t and Sharpe are of that daily series"""
    t = tr[(tr["date"] >= t0) & (tr["date"] < t1)]
    d = t.groupby("date")["pnl"].sum().reindex(days[(days >= t0) & (days < t1)]).fillna(0.0)
    yrs, n, net = yrs or (t1 - t0).days / 365.25, len(t), float(t["pnl"].sum())
    gw, gl, ddv = float(t.pnl[t.pnl > 0].sum()), float(-t.pnl[t.pnl < 0].sum()), ddmax(d.values)
    sd = float(d.std(ddof=1)) if len(d) > 1 else float("nan")
    mo = d.groupby(d.index.to_period("M")).sum()
    return {"n": n, "net": net, "pf": gw / gl if gl > 0 else float("inf"), "dd_daily": ddv,
            "roc30": 30.0 * (net / yrs) / ddv if ddv > 0 else float("nan"), "sortino": so(d.values),
            "sharpe": float(d.mean() / sd * np.sqrt(252)) if sd > 0 else float("nan"),
            "t": float(d.mean() / (sd / np.sqrt(len(d)))) if sd > 0 else float("nan"),
            "months_pos": float((mo > 0).mean()) if len(mo) else 0.0, "net_ex_big": net - (float(t.pnl.max()) if n else 0.0)}


def book(extra, t0, t1, yrs=None):
    b = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date")
    b = b[b.index < t1]                                                              # cut before anything is computed (Stage A: nothing on/after the lockbox)
    idx = b.index.union(extra.index) if extra is not None else b.index
    M, C = b["mtm"].reindex(idx).fillna(0.0), b["close"].reindex(idx).fillna(0.0)
    if extra is not None:
        e = extra.reindex(idx).fillna(0.0); M, C = M + e, C + e
    sel = (idx >= t0) & (idx < t1)
    yrs, net, ddv = yrs or (t1 - t0).days / 365.25, float(C[sel].sum()), ddmax(M[sel].values)
    return {"net": net, "roc30": net / yrs / 1000 * 30000 / ddv, "sortino": so(M[sel].values), "big": float(C[sel].max())}


def row(name, s, stress=None):
    return (f"{name:<19} n {s['n']:>7,} net ${s['net']:>12,.0f} PF {s['pf']:.2f} ROC@30k {s['roc30']:>8.1f} Sortino {s['sortino']:>6.2f} t {s['t']:>5.2f} "
            f"months+ {s['months_pos']:>4.0%} ex-big ${s['net_ex_big']:>11,.0f}" + (f" stress ${stress:,.0f}" if stress is not None else ""))


def dump(obj, name):
    def conv(x):
        return bool(x) if isinstance(x, np.bool_) else float(x) if isinstance(x, (np.floating, np.integer)) else str(x)
    json.dump(obj, open(os.path.join(OUT, name), "w"), indent=1, default=conv)


PREREG_SHA = "bda7220312a49c30d9b6857017cf00ba95d9c80fc7c0dfb9050a7d25bbf4f41d"      # canonical (LF) sha256 of PREREG_ALPACA_R1.txt: main 2ba5b3db + the pre-data addendum


def prereg_ok():
    """the frozen spec this file implements must still be the committed one (a changed spec = a new file, r2): a missing or changed file refuses A and B"""
    p = os.path.join(HERE, "PREREG_ALPACA_R1.txt")
    if not os.path.exists(p):
        raise SystemExit("refused: PREREG_ALPACA_R1.txt is not next to this file - the spec cannot be verified (nothing computed, lockbox NOT read)")
    if hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest() != PREREG_SHA:
        raise SystemExit("refused: PREREG_ALPACA_R1.txt DIFFERS from the committed blob - a changed spec is a new file, r2 (nothing computed, lockbox NOT read)")
    print("prereg check: PREREG_ALPACA_R1.txt sha256 matches the committed blob")
    return True


def stamp():
    """the version Stage A ran with: this file's LF sha256 + the shared half-day list (pre-run review round 2, 2026-10-03: B refuses on any change)"""
    return {"harness_sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read().replace(b"\r\n", b"\n")).hexdigest(),
            "early_close": sorted(EARLY_CLOSE_DATES)}


def counts_by_year(D):
    """survivorship check: names passing filters 1-3 and 1-4 per session, by year (pre-lockbox only)"""
    with np.errstate(invalid="ignore"):
        n4 = (D.P & (D.RV >= RVMIN)).sum(axis=1)
    n3, out = D.P.sum(axis=1), {}
    for y in sorted(set(D.days.year)):
        s = (D.days.year == y) & (D.days >= REP0)
        if s.any():
            out[int(y)] = {"median_1to3": float(np.median(n3[s])), "median_1to4": float(np.median(n4[s])), "days_lt20_selected": int((n4[s] < TOP).sum()), "days": int(s.sum())}
    return out


def coverage_by_year(D):
    """prereg addendum 3: share of the name-days passing filters 1-3 that have a finite 09:30 volume (V5), by year from 2016-01-04 (pre-lockbox only);
    a low share means the intraday symbols do not match the daily ones (a symbol-mapping failure)"""
    out = {}
    for y in sorted(set(D.days.year)):
        s = (D.days.year == y) & (D.days >= REP0)
        if s.any():
            k, k5 = int(D.P[s].sum()), int((D.P[s] & np.isfinite(D.V5[s])).sum())
            out[int(y)] = {"name_days_1to3": k, "with_0930_bar": k5, "share": k5 / k if k else float("nan")}
    return out


def judge(w, tw, stress_net):
    R = RULES
    return {"n>=%d" % R["n"]: w["n"] >= R["n"], "roc>=%g" % R["roc"]: w["roc30"] >= R["roc"], "pf>=%g" % R["pf"]: w["pf"] >= R["pf"],
            "t>=%g" % R["t"]: w["t"] >= R["t"],
            "beats twin ROC and Sortino": (w["roc30"] > tw["roc30"] and w["sortino"] > tw["sortino"]) if R["twin"] else True,
            "stress net>0": stress_net > 0 if R["stress"] else True, "net ex biggest>0": w["net_ex_big"] > 0 if R["exbig"] else True,
            "months+>=%g" % R["months"]: w["months_pos"] >= R["months"]}


# ------------------------------------------------------------------ Stage A (pre-lockbox) and Stage B (lockbox, once)
def stage_a():
    pok = prereg_ok()
    D = Data(LB0)                                   # every input is cut to dates < 2025-06-30 inside this call, before anything is computed
    if not D.days.max() < LB0:
        raise SystemExit("Stage A refused: a session on/after 2025-06-30 is in memory (nothing computed)")
    wf = D.days[(D.days >= WF0) & (D.days < LB0)]
    need_files("open5", [d for d in D.days if O5_0 <= d < LB0])
    cy, cov = counts_by_year(D), coverage_by_year(D)
    print("names passing filters 1-3 / 1-4 per session (median), by year:", "  ".join(f"{y}: {v['median_1to3']:.0f}/{v['median_1to4']:.0f}" for y, v in cy.items()))
    print(f"coverage gate (prereg addendum 3) - name-days passing filters 1-3 that have a 09:30 bar, by year (every year needs >= {RULES['cov']:.0%}):",
          "  ".join(f"{y}: {v['share']:.1%}" for y, v in cov.items()))
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok, **stamp(), "counts_by_year": cy, "coverage_by_year": cov, "judged": False, "A2": None}   # every dump below carries the stamp
    low = [y for y, v in cov.items() if not v["share"] >= RULES["cov"]]
    if low:
        print(f"Stage A is NOT judged: the 09:30 bar is missing for too many name-days passing filters 1-3 in {low} - a symbol-mapping failure "
              f"(the intraday pulls do not see the symbols the daily pull does); the numbers are in siporb_stageA.json")
        dump(out, "siporb_stageA.json"); return
    need_files("min1_top", D.days[(D.days >= REP0) & (D.days < LB0)])
    m = D.P & np.isfinite(D.O5)
    print(f"survivorship / mapping check: names passing 1-3 ever {int(D.P.any(axis=0).sum()):,}; 5-min open differs from the daily open by >5% on "
          f"{float(np.mean(np.abs(D.O5[m] / D.Od[m] - 1.0) > 0.05)):.2%} of {int(m.sum()):,} name-days")
    a1, ms = run(D, REP0, LB0, "top")
    a1.to_csv(os.path.join(OUT, "siporb_trades_A1_pre.csv"), index=False)
    out["no_min1"] = {"A1": len(ms), "A1_first": [f"{d:%Y-%m-%d} {s}" for d, s in ms[:20]]}
    print(f"order-names with no 1-minute bars in their day's file (cannot fill - counted, not hidden): A1 {len(ms):,}"
          + (f", first {', '.join(out['no_min1']['A1_first'][:5])}" if ms else ""))
    rep = stats(a1, D.days, REP0, REP1)
    print(f"REPLICATION 2016-01-04 -> 2023-12-29 (the paper's sample, not out-of-sample): A1 {rep['n']:,} trades, net ${rep['net']:,.0f}, "
          f"annualised daily Sharpe {rep['sharpe']:.2f} (paper 2.81; the pipeline check needs >= {RULES['rep_sharpe']:g})")
    out["replication"] = rep
    if not rep["sharpe"] >= RULES["rep_sharpe"]:
        print("Stage A is NOT judged: the replication Sharpe is below the pipeline check - the data or code is not reproducing the paper; explain the gap first")
        dump(out, "siporb_stageA.json"); return
    if not all(have(path_of("min1_twin", f"{d:%Y-%m-%d}")) for d in wf):                # the replication runs on `min1 top` alone: check the pipeline before the big twin pull
        print("Replication check passed. The raw twin's 1-minute bars are not all pulled yet - run `min1 twin`, then A again (Stage A not judged)")
        dump(out, "siporb_stageA.json"); return
    tw, mt = run(D, WF0, LB0, "twin")
    tw.to_csv(os.path.join(OUT, "siporb_trades_twin_wf.csv.gz"), index=False)
    out["no_min1"].update({"twin": len(mt), "twin_first": [f"{d:%Y-%m-%d} {s}" for d, s in mt[:20]]})
    print(f"order-names with no 1-minute bars: raw twin {len(mt):,}" + (f", first {', '.join(out['no_min1']['twin_first'][:5])}" if mt else ""))
    w, lo, tws = stats(a1, D.days, WF0, LB0), stats(a1[a1["side"] > 0], D.days, WF0, LB0), stats(tw, D.days, WF0, LB0)
    stress = float(a1[(a1["date"] >= WF0) & (a1["date"] < LB0)]["pnl_stress"].sum())
    chk = judge(w, tws, stress)
    ok = all(chk.values())
    print(f"WF 2024-01-02 -> 2025-06-29 ({len(wf)} sessions)")
    print("  " + row("A1 both sides", w, stress)); print("  " + row("A2 long only (info)", lo)); print("  " + row("RAW TWIN (WF only)", tws))
    flags = ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items())
    print(f"  Stage A checks: {flags} -> {'PASS' if ok else 'FAIL'}")
    out.update({"judged": True, "stageA": {"A1": w, "long_only": lo, "twin": tws, "stress_net": stress, "checks": chk, "PASS": bool(ok)}})
    if not ok:
        print("Stage A: FAIL - SIPORB dead; lockbox stays sealed")
        dump(out, "siporb_stageA.json"); return
    dump(out, "siporb_stageA.json")                 # Stage A's PASS is on file before the book is read (A2 still None: B stays refused)
    try:
        base = book(None, WF0, LB0)
        leg = a1.groupby("date")["pnl"].sum()
        by_c = {c: book(leg * c, WF0, LB0) for c in CS}
    except Exception as e:                          # a missing / bad book file: record it, exit non-zero
        out["A2"] = {"pass": False, "error": f"book read failed - {type(e).__name__}: {e}"}; dump(out, "siporb_stageA.json")
        raise SystemExit(f"A2 NOT judged: the book file could not be read ({type(e).__name__}: {e}); Stage A is on file in siporb_stageA.json")
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {base['roc30']:.2f} Sortino {base['sortino']:.3f}")
    if CHECK_BOOK and not (abs(base["roc30"] - BOOK_WF[0]) < 0.006 and abs(base["sortino"] - BOOK_WF[1]) < 0.0006):
        print("A2 NOT judged: the book file does not reproduce #463's prereg numbers - fix the input first")
        out["A2"] = {"pass": False, "error": "book check mismatch", "book_wf": base}; dump(out, "siporb_stageA.json"); return
    cb = max(CS, key=lambda c: by_c[c]["roc30"])     # best c by WF book ROC@30k (ties -> smaller c), then frozen
    alone = w["roc30"] >= RULES["a2_alone"]
    viab = by_c[cb]["roc30"] >= RULES["a2_book"] and by_c[cb]["sortino"] >= RULES["a2_sort"]
    for c, r in by_c.items():
        print(f"  #463 + A1 x{c:g}: WF ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f}")
    print(f"A2: standalone ROC@30k {w['roc30']:.2f} vs {RULES['a2_alone']} -> {'ok' if alone else 'no'}; book add best x{cb:g} ROC@30k {by_c[cb]['roc30']:.2f} "
          f"(needs {RULES['a2_book']}) Sortino {by_c[cb]['sortino']:.3f} (needs {RULES['a2_sort']}) -> {'ok' if viab else 'no'} => {'PASS' if alone or viab else 'FAIL'}")
    out["A2"] = {"c": cb, "pass": bool(alone or viab), "standalone_ok": bool(alone), "book_ok": bool(viab), "book_wf": base,
                 "by_c": {str(k): v for k, v in by_c.items()}}
    dump(out, "siporb_stageA.json")


def stage_b(*a):
    pa_ = os.path.join(OUT, "siporb_stageA.json")
    sa = json.load(open(pa_)) if os.path.exists(pa_) else {}
    a2 = sa.get("A2") or {}
    if not a2.get("pass"):
        print("Stage B refused: no Stage A2 pass on file - the lockbox stays sealed."); return
    bad = [k for k, v in stamp().items() if sa.get(k) != v]      # pre-run review round 2, 2026-10-03: before the flag and before any lockbox data
    if bad:
        print(f"Stage B refused: Stage A was written by a different harness version / early-close list ({', '.join(bad)} differs or is missing) "
              "- run A again (lockbox NOT read)"); return
    flag = os.path.join(OUT, "siporb_stageB_READ.flag")
    if os.path.exists(flag):
        raise SystemExit("Stage B refused: the lockbox was already read once (siporb_stageB_READ.flag)")
    prereg_ok()
    try:                                             # both book files are read BEFORE the flag: a missing / bad file cannot burn the lockbox
        bb = book(None, LB0, LB1, yrs=LBY)          # the book's own LB numbers are public (prereg)
        bt = pd.read_csv(os.path.join(os.path.dirname(BOOK), "book463_trades.csv"), parse_dates=["date"])
        bt_big = float(bt[(bt["date"] >= LB0) & (bt["date"] < LB1)]["pnl"].max())                 # the book's biggest LB trade (LB1 = LBX, exclusive)
        if not np.isfinite(bt_big):
            raise ValueError("no LB trade in book463_trades.csv")
    except Exception as e:
        print(f"Stage B refused: a BOOK #463 file is missing or bad ({type(e).__name__}: {e}) (lockbox NOT read)"); return
    if CHECK_BOOK:
        print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bb['roc30']:.2f} Sortino {bb['sortino']:.3f}")
        if not (abs(bb["roc30"] - BOOK_LB[0]) < 0.006 and abs(bb["sortino"] - BOOK_LB[1]) < 0.0006):
            print("Stage B refused: the book file's LB window does not reproduce #463's prereg LB numbers - settle the end-date convention first (lockbox NOT read)"); return
    c = float(a2["c"])
    D = Data(LB1)                                    # loads bars only; no LB result has been computed or shown yet
    need_files("open5", [d for d in D.days if O5_0 <= d < LB1]); need_files("min1_top", D.days[(D.days >= LB0) & (D.days < LB1)])
    lb = (D.days >= LB0) & (D.days < LB1)                            # prereg addendum 3's coverage rule, applied to the lockbox BEFORE the one read
    k, k5 = int(D.P[lb].sum()), int((D.P[lb] & np.isfinite(D.V5[lb])).sum())
    print(f"coverage on the lockbox: {k5:,} of {k:,} name-days passing filters 1-3 have a 09:30 bar ({k5 / max(k, 1):.1%}; needs >= {RULES['cov']:.0%})")
    if not (k and k5 / k >= RULES["cov"]):
        print("Stage B refused: the 09:30 bar is missing for too many lockbox name-days - a symbol-mapping failure; fix the pull first (lockbox NOT read)"); return
    try:                                             # every lockbox order-name must have 1-minute bars in its day's file (selection only - nothing simulated)
        gaps = min1_gaps(D, LB0, LB1)
    except Exception as e:
        print(f"Stage B refused: a lockbox min1_top file could not be read ({type(e).__name__}: {e}) (lockbox NOT read)"); return
    print(f"lockbox 1-minute files: {len(gaps):,} order-names without 1-minute bars (needs 0)")
    if gaps:
        open(path_of("min1_top_gaps.txt"), "w").write("".join(f"{d:%Y-%m-%d}\t{s}\n" for d, s in gaps))
        if "--gaps-ok" not in a:                     # a gap that survives a re-pull is real (Alpaca has no bars): `B --gaps-ok` counts it as no fill, as Stage A does
            print("Stage B refused: delete the min1_top day files listed in min1_top_gaps.txt (cache) and run `min1 top` again; if the same gaps come back, "
                  "they are real - run `B --gaps-ok` (no fill, as Stage A counts them) (lockbox NOT read)"); return
        print("--gaps-ok: these order-names get no fill (as in Stage A)")
    open(flag, "w").write(pd.Timestamp.now().isoformat())        # the one read starts here (a crash above leaves the lockbox unread)
    tr, ms = run(D, LB0, LB1, "top")
    tr.to_csv(os.path.join(OUT, "siporb_trades_A1_lb.csv"), index=False)
    st = stats(tr, D.days, LB0, LB1, yrs=LBY)
    leg = tr.groupby("date")["pnl"].sum() * c
    r = book(leg, LB0, LB1, yrs=LBY)
    big = max(bt_big, float(tr["pnl"].max() * c) if len(tr) else 0.0)
    r.update({"big": big, "no_min1": len(ms)})
    alone = st["n"] >= RULES["b_n"] and st["roc30"] >= RULES["b_roc"] and st["net_ex_big"] > 0
    viab = r["roc30"] >= RULES["b_roc"] and r["sortino"] >= RULES["b_sort"] and r["net"] - big > 0
    print("Stage B (lockbox, read once)")
    print("  " + row("A1 standalone LB", st))
    print(f"  book #463 + A1 x{c:g}: LB ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f}, without its biggest trade ${r['net'] - big:,.0f}")
    print(f"  standalone route {'ok' if alone else 'no'} (needs n>={RULES['b_n']}, ROC@30k>={RULES['b_roc']}, profitable without its biggest trade); "
          f"book route {'ok' if viab else 'no'} (needs ROC@30k>={RULES['b_roc']}, Sortino>={RULES['b_sort']}, profitable without the biggest trade) -> {'PASS' if alone or viab else 'FAIL'}")
    dump({"standalone": st, "book_add": r, "c": c, "standalone_ok": bool(alone), "book_ok": bool(viab), "pass": bool(alone or viab)}, "siporb_stageB.json")


def mapping_verdict(daily, intraday):
    """FB/META probe verdict. The daily request and the 5-minute request (both Alpaca's default mapping = today's names, no asof) must answer for
    the same symbols, or the intraday pulls would miss names the daily pull has. rows = [(symbol, ...)] -> (True | False | None, text)"""
    d, i = sorted({r[0] for r in daily}), sorted({r[0] for r in intraday})
    if not d and not i:
        return None, "INCONCLUSIVE - neither request returned a bar (check the date, the feed and the keys)"
    if d == i:
        return True, f"SAME MAPPING - the daily and the 5-minute requests answer for the same symbols {d}; the intraday pulls see what the daily pull sees"
    return False, f"MAPPING DIFFERS - daily bars for {d}, 5-minute bars for {i}; the coverage gate would fail - do NOT run open5 / min1, tell the lane"


def probe():
    """a handful of real requests that settle the API questions before the long pulls (needs keys; saves nothing)"""
    key, secret = keys()

    def go(label, syms, tf, s, e, adj="raw"):
        try:
            rows = fetch_bars(syms, tf, s, e, adj, key, secret)
            print(f"  {label}: {len(rows)} bars" + (f", first {rows[0]}" if rows else ""), flush=True)
            return rows
        except (BadRequest, RuntimeError) as ex:
            print(f"  {label}: FAILED {str(ex)[:200]}", flush=True)
            return []
    print("probe (a few requests, nothing is saved; no request sends asof):")
    r = go("daily AAPL raw (4:1 split on 2020-08-31)", ["AAPL"], "1Day", "2020-08-26T00:00:00Z", "2020-09-02T23:59:59Z")
    s = go("daily AAPL split-adjusted", ["AAPL"], "1Day", "2020-08-26T00:00:00Z", "2020-09-02T23:59:59Z", "split")
    if r and len(r) == len(s):
        print("  raw/split OPEN factor by session:", [round(a[2] / b[2], 3) for a, b in zip(r, s)], "(a >1% jump = the split rule fires on the first post-split session)")
    d, sy, dd, m5 = "2019-01-02", ["AAPL", "MSFT", "FB", "META"], [], []
    for x in sy:                                           # one symbol a request: an unknown name (FB today) may be a 400 that would hide the others
        dd += go(f"daily {x} on {d}, default mapping (the daily pull's)", [x], "1Day", f"{d}T00:00:00Z", f"{d}T23:59:59Z")
        m5 += go(f"5-min 09:30 {x} on {d}, default mapping (open5 / min1's)", [x], "5Min", utc(d, 9, 30), utc(d, 9, 34, 59))
    ok, text = mapping_verdict(dd, m5)
    have = lambda rows: {r[0] for r in rows}
    print(f"  FB/META RESULT for {d} (FB was renamed META in June 2022; neither request sends asof):")
    for x in ("FB", "META"):
        print(f"    {x:<5} daily bar: {'yes' if x in have(dd) else 'NO '} | 5-min 09:30 bar: {'yes' if x in have(m5) else 'NO '}")
    print(f"    -> {text}", flush=True)
    go("1-minute AAPL 2024-03-11 09:30-09:36 (expect 7 bars, first stamp 13:30Z)", ["AAPL"], "1Min", utc("2024-03-11", 9, 30), utc("2024-03-11", 9, 36))
    if os.path.exists(path_of("assets.csv")):
        u = universe()
        for n in (100, 500, 1000, 1500):
            if n <= len(u):
                go(f"{n} symbols in one request (URL {sum(len(x) + 3 for x in u[:n]):,} chars), 5-min 09:30 bars 2024-03-11", u[:n], "5Min",
                   utc("2024-03-11", 9, 30), utc("2024-03-11", 9, 34, 59))


# ------------------------------------------------------------------ smoke: offline self-test on synthetic bars (fake Alpaca transport, no network, no keys)
class _Reply:
    def __init__(self, code, body):
        self.status_code, self._b, self.text = code, body, json.dumps(body)[:300]

    def json(self):
        return self._b


class Fake:
    """stand-in for the two endpoints: synthetic bars in Alpaca's JSON shape, small pages, a 429 now and then, one dropped connection; a request that
    carries asof fails the test (one symbol mapping for every pull, prereg addendum 3)"""
    def __init__(self, days, page=2500):
        self.days, self.D, self.page, self.n, self.auth_fail, self._st = [f"{d:%Y-%m-%d}" for d in days], len(days), page, 0, False, {}
        rng = np.random.default_rng(11)
        self.names = names = [f"S{k:02d}" for k in range(1, 35)] + ["LOWP", "LOWV", "LOWA", "SPL", "RVS", "DLST"]
        self.k, N, ix, dx = {n: k for k, n in enumerate(names)}, len(names), names.index, self.days.index
        self.p0, self.sig, self.vol = rng.uniform(20, 150, N), rng.uniform(0.02, 0.04, N), rng.uniform(1.5e6, 6e6, N)
        self.p0[ix("LOWP")], self.vol[ix("LOWV")], self.p0[ix("LOWA")], self.sig[ix("LOWA")], self.p0[ix("SPL")], self.p0[ix("RVS")] = 3.0, 3e5, 10.0, 0.004, 60.0, 150.0
        self.first, self.last = np.zeros(N, int), np.full(N, self.D - 1)
        self.first[ix("S33")], self.first[ix("S34")], self.last[ix("DLST")] = dx("2016-02-01"), dx("2024-02-01"), dx("2024-05-31")
        self.gday = {ix("SPL"): (dx("2024-03-15"), 2.0), ix("RVS"): (dx("2016-02-17"), 0.2)}   # k: (first post-split session, raw/adjusted price factor before it)
        self.daily, self.f5, self.opx = np.full((N, self.D, 5), np.nan), np.full((N, self.D, 5), np.nan), np.full((N, self.D), np.nan)
        for k in range(N):
            px, gr = self.p0[k], np.random.default_rng([k, 6])
            for d in range(self.first[k], self.last[k] + 1):
                self.opx[k, d] = px
                o, h, l, c, v, has = self.minutes(k, d)
                self.daily[k, d] = (o[has][0], h[has].max(), l[has].min(), c[has][-1], v[has].sum())
                a = has[:5]; self.f5[k, d] = (o[:5][a][0], h[:5][a].max(), l[:5][a].min(), c[:5][a][-1], v[:5][a].sum())
                px = c[has][-1] * (1 + gr.normal(0, 0.003))

    def minutes(self, k, d):
        rng = np.random.default_rng([k, d, 5]); px, sg = self.opx[k, d], self.sig[k] / np.sqrt(NMIN)
        news, sgn = rng.random() < 0.3, rng.choice([-1.0, 1.0])
        z = rng.standard_normal(NMIN) * sg
        z[:5] += sgn * sg * (0.8 if news else 0.1); z[5:] += sgn * sg * (0.03 if news else 0.0)     # a mild lean in the opening bar's direction
        c = px * np.exp(np.cumsum(z)); o = np.r_[px, c[:-1]]
        w = np.abs(rng.standard_normal(NMIN)) * sg * 0.6
        h, l = np.maximum(o, c) * (1 + w), np.minimum(o, c) * (1 - w)
        wt = 1 + 5 * np.exp(-np.arange(NMIN) / 8.0); wt[:8] *= 3.0 if news else 1.0
        v = np.round(self.vol[k] * rng.lognormal(0, 0.25) * (2.0 if news else 1.0) * wt / wt.sum()) + 1
        has = rng.random(NMIN) > 0.02; has[:5] = True; has[-1] = has[-1] and rng.random() > 0.05     # a few minutes with no trade, sometimes no 15:59 bar
        return o, h, l, c, v, has

    def g(self, k, d, adj):
        gd = self.gday.get(k)
        return gd[1] if (adj == "raw" and gd and d < gd[0]) else 1.0

    def sc(self, k, d, a, adj):
        g = self.g(k, d, adj)
        return [round(float(x * g), 4) for x in a[:4]] + [int(round(a[4] / g))]

    def stamps(self, d):
        if d not in self._st:
            t0 = TS(f"{self.days[d]} 09:30", tz="US/Eastern").tz_convert("UTC")
            self._st[d] = [(t0 + pd.Timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ") for m in range(NMIN)]
        return self._st[d]

    def bars(self, p):
        syms, tf, adj, rows = sorted(s for s in p["symbols"].split(",") if s in self.k), p["timeframe"], p["adjustment"], []
        if tf == "1Day":
            d0, d1 = p["start"][:10], p["end"][:10]
            for s in syms:
                k = self.k[s]
                for d in range(self.D):
                    if d0 <= self.days[d] <= d1 and not np.isnan(self.daily[k, d, 0]):
                        rows.append((s, TS(self.days[d], tz="US/Eastern").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), *self.sc(k, d, self.daily[k, d], adj)))
        else:
            a, b = TS(p["start"]).tz_convert("US/Eastern"), TS(p["end"]).tz_convert("US/Eastern")
            d, m0, m1 = (self.days.index(f"{a:%Y-%m-%d}") if f"{a:%Y-%m-%d}" in self.days else -1), a.hour * 60 + a.minute, b.hour * 60 + b.minute
            for s in syms:
                k = self.k[s]
                if d < 0 or np.isnan(self.daily[k, d, 0]):
                    continue
                if tf == "5Min":
                    if m0 <= 570 <= m1:                                                   # only the opening 5-minute bar is served
                        rows.append((s, self.stamps(d)[0], *self.sc(k, d, self.f5[k, d], adj)))
                else:
                    o, h, l, c, v, has = self.minutes(k, d)
                    for m in np.flatnonzero(has):
                        if m0 <= 570 + m <= m1:
                            rows.append((s, self.stamps(d)[m], *self.sc(k, d, np.array([o[m], h[m], l[m], c[m], v[m]]), adj)))
        off = int(p.get("page_token") or 0)
        out = {}
        for r in rows[off:off + self.page]:
            out.setdefault(r[0], []).append({"t": r[1], "o": r[2], "h": r[3], "l": r[4], "c": r[5], "v": r[6]})
        return {"bars": out, "next_page_token": str(off + self.page) if off + self.page < len(rows) else None}

    def assets(self, p):
        st = p["status"]
        rows = [(n, f"{n} Inc", "NASDAQ" if k % 2 else "NYSE") for k, n in enumerate(self.names) if (n == "DLST") == (st == "inactive")]
        if st == "active":
            rows += [("SPYX", "Fake S&P 500 ETF Trust", "ARCA"), ("ABCDW", "Abcd Inc Warrants", "NASDAQ"), ("BRK.B", "Berk Class B", "NYSE"), ("OTCX", "Otc Corp", "OTC"),
                     ("NFXX", "Netflix Like Inc", "NASDAQ"), ("FNDX", "Fundamental Holdings", "NYSE"), ("ZZBAD", "Zzbad Corp", "NYSE")]
        return [{"symbol": s, "name": nm, "exchange": ex, "status": st, "tradable": st == "active", "shortable": True, "easy_to_borrow": True} for s, nm, ex in rows]

    def handle(self, url, heads, params):
        self.n += 1
        if self.auth_fail:
            return _Reply(401, {"message": "unauthorized"})
        assert heads.get("APCA-API-KEY-ID") and heads.get("APCA-API-SECRET-KEY")
        if self.n == 50:
            raise ConnectionError("blip")
        if self.n % 37 == 0:
            return _Reply(429, {"message": "too many requests"})
        if url.endswith("/v2/assets"):
            return _Reply(200, self.assets(params))
        assert url == BARS_URL and params["feed"] == "sip" and int(params["limit"]) <= 10000
        assert "asof" not in params, "no pull may send asof: daily and intraday bars use the same (default) symbol mapping"
        if "ZZBAD" in params["symbols"].split(","):                                   # a symbol the endpoint rejects outright (400) -> the pull bisects it out
            return _Reply(400, {"message": "invalid symbol: ZZBAD"})
        return _Reply(200, self.bars(params))


def selftest():
    """rules on hand-made bars, name filters, chunking"""
    def one(spec, side, E, atr):
        a = [np.full((1, NMIN), np.nan) for _ in range(4)]
        for m, (o, h, l, c) in spec.items():
            for arr, x in zip(a, (o, h, l, c)):
                arr[0, m] = x
        return simulate(*a, np.array([side], float), np.array([E], float), np.array([atr], float))
    cases = [
        ("long, opens through the stop, stopped on the fill bar", one({10: (101, 101.5, 100.6, 101.2)}, 1, 100, 2.0), 101, 100.8, 198, True),
        ("long, fills at the stop, fill bar also reaches the protective stop", one({7: (99.5, 100.3, 99.4, 100.2)}, 1, 100, 2.0), 100, 99.8, 200, True),
        ("long, later bar opens through the stop", one({7: (99.9, 100.3, 99.9, 100.2), 20: (99.5, 99.9, 99.4, 99.6)}, 1, 100, 2.0), 100, 99.5, 200, True),
        ("long, later bar touches the stop", one({7: (99.9, 100.3, 99.9, 100.2), 30: (100.5, 100.6, 99.7, 100.1)}, 1, 100, 2.0), 100, 99.8, 200, True),
        ("long, never stopped, exit at the 15:59 close", one({7: (99.9, 100.3, 99.9, 100.2), 389: (102, 103.5, 101.9, 103)}, 1, 100, 2.0), 100, 103, 200, False),
        ("long, 15:59 bar missing -> last bar's close", one({7: (99.9, 100.3, 99.9, 100.2), 380: (101, 102.5, 100.9, 102)}, 1, 100, 2.0), 100, 102, 200, False),
        ("short, fills at the stop, fill bar also reaches the protective stop", one({6: (100.4, 100.6, 99.9, 100.0)}, -1, 100, 2.0), 100, 100.2, 200, True),
        ("short, opens through the stop (shares capped by 4x slot)", one({6: (99.0, 99.1, 98.5, 98.9), 389: (98, 98.5, 97.5, 97.8)}, -1, 100, 2.0), 99, 97.8, 202, False),
        ("fill on the 15:58 bar counts", one({388: (99.9, 100.3, 99.9, 100.1), 389: (100.1, 100.2, 100.0, 100.15)}, 1, 100, 2.0), 100, 100.15, 200, False),
    ]
    for name, r, entry, ex, sh, stopped in cases:
        assert r["ok"][0] and np.isclose(r["entry"][0], entry) and np.isclose(r["exit"][0], ex) and r["shares"][0] == sh and bool(r["stopped"][0]) == stopped, (name, r)
    assert not one({389: (99.9, 100.3, 99.9, 100.2)}, 1, 100, 2.0)["ok"][0], "15:59 bar must not fill"
    assert not one({4: (99.9, 100.3, 99.9, 100.2)}, 1, 100, 2.0)["ok"][0], "bars before 09:35 must not fill"
    assert not one({7: (99.0, 99.5, 98.9, 99.2)}, 1, 100, 2.0)["ok"][0], "no touch, no fill"
    assert not one({7: (100.9, 101.0, 100.8, 100.9)}, 1, 100, 1e6)["ok"][0], "shares < 1 -> no trade"
    hb = pd.DataFrame({"symbol": "X", "m": [575, 600, 779, 840, 959], "o": [99.9, 100.2, 100.4, 100.6, 97.0], "h": [100.3, 100.4, 100.5, 100.7, 97.0],
                       "l": [99.9, 100.1, 100.3, 100.5, 97.0], "c": [100.1, 100.3, 100.4, 100.6, 97.0], "v": 100})     # 14:00 / 15:59 = after-hours prints on a half day
    hs = lambda b, day: (lambda s: simulate(*dense(s[0], np.array(["X"])), np.array([1.0]), np.array([100.0]), np.array([2.0]), s[1]))(session_bars(b, TS(day)))
    for day, ex, em in (("2024-11-29", 100.4, 779), ("2024-11-27", 97.0, 959)):                  # half day: the 12:59 close; a full day: the 15:59 bar (stopped)
        r = hs(hb, day); assert r["ok"][0] and np.isclose(r["exit"][0], ex) and r["exit_min"][0] == em, (day, r)
    assert not hs(hb.iloc[[2, 3]], "2024-11-29")["ok"][0] and hs(hb.iloc[[2, 3]], "2024-11-27")["ok"][0], "half day: no fill on the 12:59 bar or after 13:00"
    for sym, name, exch, bad in (("BRK.B", "x", "NYSE", True), ("ABCDW", "x", "NASDAQ", True), ("ABCD", "x", "NASDAQ", False), ("NEWS", "x", "NYSE", False), ("ABCDU", "x", "NYSE", True),
                                 ("ABCDR", "x", "NYSE", True), ("ABCWS", "x", "NYSE", True), ("NFLX", "Netflix, Inc.", "NASDAQ", False), ("QQQ", "Invesco QQQ Trust, Series 1", "NASDAQ", True),
                                 ("SPY", "SPDR S&P 500 ETF Trust", "ARCA", True), ("TQQQ", "ProShares UltraPro QQQ", "NASDAQ", True), ("UCTT", "Ultra Clean Holdings, Inc.", "NASDAQ", True),
                                 ("UGNX", "Ultragenyx Pharmaceutical Inc.", "NASDAQ", False), ("XYZ", "Xyz Corp", "OTC", True), ("FXX", "Fundamental Holdings", "NYSE", False)):
        assert (why_not(sym, name, exch) is not None) == bad, (sym, name, why_not(sym, name, exch))
    ch = chunk_syms([f"S{k:04d}" for k in range(500)], 10 ** 9, 200)
    assert sum(map(len, ch)) == 500 and all(sum(len(s) + 3 for s in c) <= 200 for c in ch) and len(ch) > 10
    assert [len(c) for c in chunk_syms(list("abcdefg"), 3, 10 ** 9)] == [3, 3, 1]
    mv = lambda a, b: mapping_verdict([(s, 1) for s in a], [(s, 1) for s in b])
    assert mv(["AAPL", "META"], ["META", "AAPL"])[0] is True and mv(["AAPL", "META"], ["AAPL"])[0] is False and mv(["META"], ["FB"])[0] is False and mv([], [])[0] is None
    print("selftest ok: simulate (9 paths + 4 no-fill cases), the half-day cut (12:59 exit, no fill from 12:59 on), name/symbol filters, chunking, the FB/META mapping verdict")


def smoke_refusal(root):
    """why the smoke may not wipe `root` (None = it may): its name must contain 'smoke', and it may not be or hold OUT, CACHE, the repo, this
    harness, the working directory or C:\\EdgeLog"""
    real = lambda p: os.path.normcase(os.path.realpath(p))

    def holds(p, q):                                                             # p is q or a folder above q
        try:
            return os.path.commonpath([real(p), real(q)]) == real(p)
        except ValueError:                                                       # another drive
            return False
    hit = [n for n, q in (("OUT", OUT), ("CACHE", CACHE), ("the repo", REPO), ("this harness", HERE), ("the working directory", os.getcwd())) if holds(root, q)]
    hit += [r"C:\EdgeLog"] if root.lower().startswith(r"c:\edgelog") else []
    if "smoke" in os.path.basename(root).lower() and not hit:
        return None
    return f"smoke refused: {root} - its name must contain 'smoke' and it may not be or hold OUT, CACHE, the repo or the working directory (holds: {', '.join(hit) or 'none'})"


def smoke(*a):
    import contextlib, io, shutil, tempfile
    global OUT, CACHE, BOOK, SMOKE, PACE, BACKOFF, RETRY, URL_MAX, DAILY_BATCH, CHECK_BOOK, EXT, _http_get
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "siporb_smoke"))
    why = smoke_refusal(root)
    if why:                                                                      # the dir is wiped below: only a smoke dir, never real data
        raise SystemExit(why)
    if a[1:2] == ("csv",):                                                       # `smoke <dir> csv` = the no-pyarrow cache format (csv.gz)
        EXT = ".csv.gz"
    shutil.rmtree(root, ignore_errors=True); os.makedirs(root)
    OUT, CACHE, BOOK = os.path.join(root, "out"), os.path.join(root, "cache"), os.path.join(root, "r4", "book463_daily.csv")
    os.makedirs(OUT); os.makedirs(os.path.dirname(BOOK))
    SMOKE, PACE, BACKOFF, RETRY, URL_MAX, DAILY_BATCH = True, 0.0, 0.0, 0.0, 150, 15
    CHECK_BOOK = os.environ.get("SIPORB_BOOK_CHECK", "0") == "1"            # the override is read HERE ONLY (a real run never sees it): smoke starts with the book check off - its
                                                                                 # synthetic book cannot reproduce #463 - unless =1; the stages below then set it by hand
    BAD.clear()
    selftest()
    spans = (("2015-11-02", "2015-12-31"), ("2016-01-04", "2016-03-31"), ("2023-10-02", "2023-12-29"), ("2024-01-02", "2024-06-28"),
             ("2025-04-01", "2025-06-27"), ("2025-06-30", "2025-08-29"))       # warm-up, replication, WF, lockbox days: the cut has something to cut
    days = pd.DatetimeIndex(sorted(set().union(*[pd.bdate_range(x, y) for x, y in spans])))
    t0 = time.time(); fk = Fake(days); _http_get = fk.handle
    print(f"synthetic market: {len(fk.names)} names x {len(days)} sessions built in {time.time() - t0:.0f}s")
    fk.auth_fail = True
    try:
        _get(BARS_URL, {"symbols": "A"}, "k", "s"); raise AssertionError("401 must stop the pull")
    except SystemExit:
        pass
    fk.auth_fail = False
    assets(); assert len(universe()) == 43 and json.load(open(path_of("assets_counts.json")))["excluded_by_reason"]["exchange"] == 1
    daily(); n1 = fk.n; daily(); assert fk.n == n1, "daily resume must not re-request"
    assert {l.split("\t")[0] for l in open(path_of("bad_symbols.txt")).read().splitlines()} == {"ZZBAD"} and set(BAD) == {"ZZBAD"}, "a rejected symbol is bisected out and logged"
    victim = sorted(os.listdir(path_of("daily_parts")))[0]; os.remove(path_of("daily_parts", victim)); daily(); assert fk.n > n1 and victim in os.listdir(path_of("daily_parts"))
    r0 = read_long("raw", LB0); assert r0["date"].max() == TS("2025-06-27") and (r0.groupby("symbol", observed=True).size() > 0).all()
    open5(); n2 = fk.n; open5(); assert fk.n == n2, "open5 resume must not re-request"
    min1("est"); min1(); n3 = fk.n; min1(); assert fk.n == n3, "min1 resume must not re-request"
    os.remove(path_of("min1_twin", "2024-03-20.parquet" if EXT == ".parquet" else "2024-03-20.csv.gz")); min1("twin"); assert fk.n > n3
    probe()                                                                      # the probe runs against the fake too (it only knows the synthetic names)
    print(f"pulls ok through the fake transport ({fk.n:,} requests; 429s and a dropped connection were retried; not one request carried asof)")
    # split window on the synthetic split names
    D = Data(LB0)
    ix = list(D.syms)
    i, k = D.days.get_loc(TS("2024-03-15")), ix.index("SPL")
    assert D.chg[i, k] and not D.P[i:i + 15, k].any() and D.P[i + 15:i + 40, k].any() and D.sw[i, k] and not D.sw[i + 15, k], "forward split window"
    i, k = D.days.get_loc(TS("2016-02-17")), ix.index("RVS")
    assert D.chg[i, k] and not D.P[i:i + 15, k].any(), "reverse split window"
    assert not any(n in ix and D.P[:, ix.index(n)].any() for n in ("LOWV", "LOWA", "LOWP")), "filters 1-3"
    assert D.P[:, ix.index("DLST")][D.days > TS("2024-05-31")].sum() == 0 and D.days.max() < LB0
    print("universe ok: filters 1-3, split window [t-14, t] both directions, delisted name, cut before the lockbox")
    cv = coverage_by_year(D)                                                     # every synthetic name-day passing filters 1-3 has its 09:30 bar
    assert cv and all(v["share"] == 1.0 and v["name_days_1to3"] > 0 for v in cv.values()), cv
    # the split rule reads the OPEN ratio (prereg addendum 4): double only the split-adjusted CLOSE of one name-day and only the split-adjusted OPEN of another
    sb = path_of("daily_split"); orig = load_df(sb); doc = orig.copy(); doc["date"] = pd.to_datetime(doc["date"])
    for sym, day, col in (("S05", TS("2024-04-10"), "c"), ("S06", TS("2024-04-12"), "o")):
        mk = (doc["symbol"] == sym) & (doc["date"] == day); assert mk.sum() == 1; doc.loc[mk, col] *= 2.0
    save_df(doc, sb); D2 = Data(LB0, open5=False); save_df(orig, sb)
    ix2 = list(D2.syms)
    assert not D2.chg[D2.days.get_loc(TS("2024-04-10")), ix2.index("S05")], "a CLOSE-only mismatch must not read as a split"
    assert D2.chg[D2.days.get_loc(TS("2024-04-12")), ix2.index("S06")], "an OPEN mismatch must read as a split"
    print("coverage by year ok (100% on the synthetic market); split rule ok: read from the raw / split-adjusted OPEN, not the close")
    rng = np.random.default_rng(5)                                               # synthetic BOOK #463 files (the real ones are never touched)
    bd = pd.bdate_range("2010-06-07", "2026-06-30"); c = rng.normal(40, 700, len(bd))
    pd.DataFrame({"date": bd, "close": c, "mtm": c + rng.normal(0, 150, len(bd))}).to_csv(BOOK, index=False)
    k = rng.random(len(bd)) < 0.35
    pd.DataFrame({"date": bd[k], "pnl": c[k], "strategy": "FAKE"}).to_csv(os.path.join(os.path.dirname(BOOK), "book463_trades.csv"), index=False)
    stage_b()                                                                    # nothing on file yet: must refuse
    waive = dict(n=1, roc=-1e9, pf=0.0, t=-1e9, months=0.0, twin=False, stress=False, exbig=False, a2_alone=-1e9, a2_book=-1e9, a2_sort=-1e9, b_n=1, b_roc=-1e9, b_sort=-1e9)
    print("--- coverage gate: half of the 2024 opening bars removed (a symbol-mapping failure): Stage A must stop before simulating a single trade")
    o5 = {f[:10]: load_df(path_of("open5", f[:10])) for f in os.listdir(path_of("open5")) if f.startswith("2024-")}
    for day, df in o5.items():
        save_df(df.iloc[::2], path_of("open5", day))
    stage_a(); stage_b()
    res = json.load(open(os.path.join(OUT, "siporb_stageA.json")))
    assert not res["judged"] and res["coverage_by_year"]["2024"]["share"] < RULES["cov"] <= res["coverage_by_year"]["2016"]["share"] and res["A2"] is None, res
    assert {k: res.get(k) for k in stamp()} == stamp(), "an early-exit Stage A dump carries the harness stamp too"
    assert not os.path.exists(os.path.join(OUT, "siporb_trades_A1_pre.csv")), "the coverage gate must stop Stage A before any trade is simulated"
    for day, df in o5.items():
        save_df(df, path_of("open5", day))
    print("--- replication gate set out of reach: Stage A must stop before judging")
    RULES["rep_sharpe"] = 1e9; stage_a(); stage_b()
    print("--- replication waived, ROC bar set out of reach: the Stage A FAIL path")
    RULES.update(rep_sharpe=-1e9, roc=1e9); stage_a(); stage_b()
    print("--- every threshold waived, book check ON (the synthetic book cannot reproduce #463): A2 must refuse to judge")
    RULES.update(waive); CHECK_BOOK = True; stage_a(); stage_b()
    assert not json.load(open(os.path.join(OUT, "siporb_stageA.json")))["A2"]["pass"]
    print("--- book check OFF: the pass path, A2 and Stage B run end to end")
    CHECK_BOOK = False
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        stage_a()
    txt = buf.getvalue(); print(txt.rstrip())
    dates = re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    assert all(d < "2025-06-30" for d in dates), "Stage A printed a lockbox date"
    assert pd.read_csv(os.path.join(OUT, "siporb_trades_A1_pre.csv"))["date"].max() < "2025-06-30" and pd.read_csv(os.path.join(OUT, "siporb_trades_twin_wf.csv.gz"))["date"].max() < "2025-06-30"
    res = json.load(open(os.path.join(OUT, "siporb_stageA.json"))); assert res["A2"]["pass"] and res["A2"]["c"] in CS and res["no_min1"]["A1"] == 0 == res["no_min1"]["twin"]
    assert {k: res.get(k) for k in stamp()} == stamp() and len(res["harness_sha256"]) == 64 and "2024-11-29" in res["early_close"], "A2 pass dump carries the stamp"
    half = lambda f, d: (lambda t: t[t["date"].astype(str).str[:10] == d])(pd.read_csv(os.path.join(OUT, f)))
    hd = half("siporb_trades_A1_pre.csv", "2023-11-24"); assert len(hd) and (hd["fill_min"] <= 778).all() and (hd["exit_min"] <= 779).all(), "half day: nothing after 12:59"
    flag = os.path.join(OUT, "siporb_stageB_READ.flag")
    CHECK_BOOK = True; stage_b(); assert not os.path.exists(flag), "a refused Stage B must not burn the lockbox"      # LB baseline mismatch -> refused
    CHECK_BOOK = False
    bt = os.path.join(os.path.dirname(BOOK), "book463_trades.csv"); os.replace(bt, bt + ".away")          # the book's trade file is read BEFORE the flag
    stage_b(); assert not os.path.exists(flag), "a missing book463_trades.csv must refuse before the flag"; os.replace(bt + ".away", bt)
    Dl = Data(LB1); i = next(i for i in range(len(Dl.days)) if Dl.days[i] >= LB0 and len(orders(Dl, i, Dl.top20(i))[0]))
    mb = path_of("min1_top", f"{Dl.days[i]:%Y-%m-%d}"); keep = load_df(mb)                               # an order-name with no 1-minute bars: refused before the flag
    save_df(keep[keep["symbol"].astype(str) != str(Dl.syms[orders(Dl, i, Dl.top20(i))[0][0]])], mb)
    stage_b(); assert not os.path.exists(flag) and os.path.exists(path_of("min1_top_gaps.txt")), "a lockbox 1-minute gap must refuse before the flag"
    save_df(keep, mb)
    sa = os.path.join(OUT, "siporb_stageA.json"); sa_txt = open(sa).read(); sa_js = json.loads(sa_txt)       # pre-run review round 2, 2026-10-03
    for why, edit in (("another harness version", lambda j: j.update(harness_sha256="0" * 64)), ("another half-day list", lambda j: j.update(early_close=j["early_close"][1:])),
                      ("no stamp (an older Stage A)", lambda j: [j.pop(k) for k in stamp()])):
        j = json.loads(sa_txt); edit(j); json.dump(j, open(sa, "w"), indent=1)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            stage_b()
        assert "different harness version / early-close list" in buf.getvalue() and not os.path.exists(flag), f"Stage A from {why} must refuse B before the flag"
    open(sa, "w").write(sa_txt); assert json.load(open(sa)) == sa_js
    print("Stage B refuses before the flag when Stage A was written by another harness version, another half-day list, or without the stamp")
    stage_b()
    assert os.path.exists(flag) and os.path.exists(os.path.join(OUT, "siporb_stageB.json")) and json.load(open(os.path.join(OUT, "siporb_stageB.json")))["book_add"]["no_min1"] == 0
    hd = half("siporb_trades_A1_lb.csv", "2025-07-03"); assert len(hd) and (hd["exit_min"] <= 779).all(), "lockbox half day: nothing after 12:59"
    try:
        stage_b(); raise AssertionError("second Stage B read must be refused")
    except SystemExit as e:
        assert "already read" in str(e)
    assert all(smoke_refusal(p) for p in (HERE, REPO, os.getcwd(), root, os.path.join(root, "x"))) and smoke_refusal(os.path.join(root, "x_smoke")) is None
    print("half days cut at 13:00; Stage B refuses before the flag on a missing book trade file, a lockbox 1-minute gap or a stale harness stamp; the smoke dir guard holds")
    print("SMOKE OK - synthetic numbers mean nothing; every command ran end to end offline")


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"assets": assets, "daily": daily, "open5": open5, "min1": min1, "A": stage_a, "B": stage_b, "probe": probe, "smoke": smoke}.get(cmd)
    if fn is None:
        print("usage: r5_siporb.py assets | daily | open5 | min1 [top|twin|est] | A | B   (also: probe = a few real requests to settle API questions; smoke = offline self-test)"); return
    if cmd != "smoke":
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
