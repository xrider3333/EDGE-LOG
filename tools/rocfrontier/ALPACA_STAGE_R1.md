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
5. (No longer needed - see below. A saved key is picked up without restarting anything.)
6. Tell MANAGER only **"Alpaca keys saved"**. Never paste either key into a chat, a file or a message.

Those two names are the ones every Alpaca path in the repo reads, and since 2026-10-02 they are read in ONE
place: `augur_engine/alpaca_keys.py`. Two things above are now out of date:

- **A saved key works without restarting anything** (step 5 above). The variables are Windows *user*
  variables, which a process only inherits if it started afterwards, so every runner process and every open
  session was blind to them. The shared lookup reads `HKCU\Environment` out of the registry when `os.environ`
  lacks the keys - the same fact from the same place, no restart.
- **`C:\EdgeLog\secrets\alpaca_keys.json` IS read**, by every path, third in the order. The claim that the
  shared loader ignored it was true when written and is not now.

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

## 3. Data plan once the keys exist

**The times below assume 195 requests a minute, which assumed this lane was pulling alone.** The 200/min cap
is per ACCOUNT and five lanes share the key, so `augur_engine/alpaca_rate.py` paces every request in every
process against one shared budget of 180/min. Lanes can run at the same time - nobody needs to sequence them -
but the budget is shared, so two lanes pulling together each take roughly twice as long as this table says.

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
- `r5_nqbrd.py` and `r5_siporb.py` each gained one line, `alpaca_rate.wait()` before their HTTP request, so
  they draw from the shared budget. A pace half the callers bypass paces nothing, which is why those two were
  edited from outside this lane; a test fails if a new Alpaca request path skips it.

## Update 2026-09-30 - NQBRD is ready to run
- Membership: `tools/data/ndx_members.csv` (built before any stock bar; see `build_ndx_members.py`).
- Harness: `tools/rocfrontier/r5_nqbrd.py pull` then `A` - one multi-symbol request per day (09:30-10:00 bars of that day's members, `asof` maps renamed tickers), about 2,600 requests = ~15 minutes on the free plan.
- SIPORB: `tools/rocfrontier/r5_siporb.py` - order `probe`, `assets`, `daily`, `open5`, `min1 top`, `A` (replication check), `min1 twin`, `A` again; `B` only after an A2 pass. Roughly 3-4 hours of pulls on the free plan, most of it the raw twin's 1-minute bars.
- TRANSFER r2 (ETF proxies): `tools/rocfrontier/r8_transfer_etf.py pull`, `gates`, `A` - six funds x 5-minute and 30-minute bars through the shared loader (library masters under the fund tickers), minutes of pulls.

## Update 2026-10-03 - pre-run review fixes (code brought to the registered text; no spec change)
An independent review of every Alpaca harness ran BEFORE the box's first real Stage A or B, from a cloud session that
holds no Alpaca bar and no result. Each fix makes the code do what the prereg text already says, or closes a way the
one lockbox read could be wasted; no threshold, window, cell or pass rule moved.
- **Shared loader** (`tools/import_alpaca_stocks.py`): 2016-12-23 removed from the early-close list. NYSE traded a
  full session that day (only the bond market closed early), so `--rth` was cutting 13:00-16:00 off a WF session.
  A pull made before this fix keeps the cut; re-pull that fund/day and re-run `gates`.
- **NQBRD** (`r5_nqbrd.py`):
  - breadth exactly 0.20 now shorts at theta 0.80 (float tolerance; prereg "B <= 1 - theta");
  - the control is counted and picked on WF days only, and ranks by RETURN (raw 09:30 open from the no-adjust
    master as the denominator; the adjusted master is Panama-shifted), as prereg line 65 says;
  - the null flips ONE coin per day, shared by both thetas (prereg "each traded day's direction");
  - Stage B reads `book463_trades.csv` and checks the NQ master reaches 2026-06-30 BEFORE the read-once flag, and
    cuts the book's biggest trade to the lockbox.
  - **CHOICE (written before any Stage A result):** if both thetas pass Stage A, A2 takes the one with the higher WF
    ROC @ $30k (the prereg is silent; this is what the code always did).
- **SIPORB** (`r5_siporb.py`): on NYSE half days the 1-minute bars stop at 12:59, so fills end at 12:58 and the
  exit is the 12:59 close, not an after-hours print at 15:59 (CHOICE clarifying prereg lines 27/30: "15:59" means
  the session's last regular bar). Stage B reads the book's trade file and checks every order-name has 1-minute
  bars BEFORE the flag; if the same gaps survive a re-pull of those days they are real, and `B --gaps-ok` counts
  them as no fill, exactly as Stage A does. A missing or changed prereg now refuses A and B. The keyword filters'
  known false positives (IVZ, PFBC, APTS, DJCO, UPL, UCTT, BSF, BRK.B) are a logged CHOICE.
- **TRANSFER r2** (`r8_transfer_etf.py`): Stage B refuses, before the flag, unless the strategy files, the harness,
  the TTM check and every master fingerprint are the ones Stage A ran on.
- **All:** the read-once and lockbox-cut guards raise instead of `assert` (which `python -O` strips).
- **If any Stage A already ran on the box before these fixes**, keep its output and report it beside the corrected
  run in the ledger; the corrected run is the registered one.

## Update 2026-10-03 (later) - pre-run review round 2 (fresh reviewers; each finding checked by 2-3 skeptics)
- **NQBRD:** no change. Its r1 Stage A already ran on the round-1 code (2737f8a7) and is DEAD (ledger 2.48), so the
  harness stays exactly as run. The round-2 items for it (a version stamp, a 429 cap, the A2 bar written as the formula
  value 97.335 instead of the printed 97.3) were dropped; A2 was never reached, so none of them could change the result.
- **SIPORB:** Stage B refuses unless Stage A was written by this exact harness version and early-close list.
- **TRANSFER r2:**
  - Before the read-once flag, Stage B re-runs every passing cell on the pre-lockbox data and requires Stage A's
    trades back exactly, and also the WF numbers stageA.json judged. This catches any change to the engine, a
    strategy file or a trade-relevant price, including a split-rebased re-pull, and a stopped Stage A re-run. The old
    date-and-count fingerprint ignored prices.
- **Shared loader:** the early-close list now holds only true NYSE 13:00 closes (holidays and full sessions removed).
