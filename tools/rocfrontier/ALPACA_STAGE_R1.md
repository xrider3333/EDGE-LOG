# Alpaca staging for the new-family lane (2026-09-30)

Owner decision via MANAGER (inbox #9): Databento declined; stage Alpaca's free Basic plan instead. **Nothing runs
until the owner says "Alpaca keys saved".** Pre-registration: `PREREG_ALPACA_R1.txt` (stocks-in-play opening-range
breakout, NQ breadth trigger). Claude never creates the account and never sees the keys.

## 1. What the owner does (about 10 minutes, free, no money)

1. Go to **alpaca.markets** and click **Sign up**. Use your own email and password. A **paper-trading account is
   enough** - no funding and no brokerage application are needed for market data.
2. Log in. On the dashboard, make sure the account switcher (top left) shows **Paper**.
3. On the right of the dashboard find **API Keys** and click **Generate New Keys**. Alpaca shows two values: the
   **API Key ID** and the **Secret Key**. The secret is shown only once - keep that window open for the next step.
4. Save both on this PC: press Start, type **environment variables**, open **Edit environment variables for your
   account**. Under **User variables** click **New...**:
   - Variable name `ALPACA_API_KEY` - value: the API Key ID - OK.
   - **New...** again: variable name `ALPACA_SECRET_KEY` - value: the Secret Key - OK, then OK to close.
5. Restart the Claude app so it sees the new settings.
6. Tell MANAGER only **"Alpaca keys saved"**. Never paste either key into a chat, a file or a message.

Those two names are the ones every Alpaca path in the repo already reads first: the shared loader
`tools/import_alpaca_stocks.py` (ELWA-FEATURES), PAPER-WB's `tools/backfill_qqq_5m_alpaca.py` and `api/spy_daily.py`;
a test pins them. (PAPER-WB's earlier instruction wrote a key file to `C:\EdgeLog\secrets\alpaca_keys.json`; the
shared loader does not read that file, so the environment variables are the one method that works everywhere.)

## 2. The loader interface this lane needs (agreed with ELWA-FEATURES)

The shared loader stays the single place that talks to Alpaca and registers library masters (`alpaca_split_rth` /
`alpaca_split_eth`). Research pulls call its fetch functions and keep their own cache outside git and outside
OneDrive (`C:\EdgeLog\alpaca_cache\`); they never register masters. Asked of the loader:

- `fetch_bars_multi(symbols, timeframe, start, end, key, secret, feed="sip", adjustment="split")` - many symbols per
  request (Alpaca's `symbols=A,B,C`), paged on `next_page_token`, the loader's own pacing (<= 195 requests a minute,
  back off on 429). Returns one DataFrame: `symbol, time` (POSIX seconds, bar START), `open, high, low, close,
  volume, trade_count, vwap`. The existing single-symbol `fetch_bars` can wrap it.
- `list_assets(key, secret, status="all")` - US equities incl. inactive names (the stocks-in-play universe must see
  delisted stocks where Alpaca has them): `symbol, name, exchange, status, tradable, shortable, easy_to_borrow`.
- `adjustment` stays a parameter: research needs RAW daily bars for as-of price and ATR filters (a later reverse split
  would otherwise push a $0.50 stock past a $5 filter); library masters stay split-adjusted.

## 3. Data plan once the keys exist (estimates at 195 requests a minute)

| Pull | Size | Requests | Time |
|---|---|---|---|
| Asset list, active + inactive | ~12k names | 2 | seconds |
| Daily raw bars, all US equities, 2015-12 -> now | ~7k names x 2,700 days | ~2,000 | ~10 min |
| 09:30-09:35 bar for names passing the daily filters, every day | ~1-2k names a day | ~2,700 | ~15 min |
| 1-minute RTH bars for the <= 20 picks a day | 20 x 390 bars a day | ~2,700 | ~15 min |
| 5-minute 09:30-10:00 bars, Nasdaq-100 members | ~200 names | ~2,700 | ~15 min |

## 4. Open

- Point-in-time Nasdaq-100 membership file (`tools/data/ndx_members.csv`) - built from public sources before any bar
  is read; this lane owns it.
- Nothing is scheduled; the first pull runs once, by hand, after "Alpaca keys saved".

## Update 2026-09-30 - NQBRD is ready to run
- Membership: `tools/data/ndx_members.csv` (built before any stock bar; see `build_ndx_members.py`).
- Harness: `tools/rocfrontier/r5_nqbrd.py pull` then `A` - one multi-symbol request per day (09:30-10:00 bars of that day's members, `asof` maps renamed tickers), about 2,600 requests = ~15 minutes on the free plan.
