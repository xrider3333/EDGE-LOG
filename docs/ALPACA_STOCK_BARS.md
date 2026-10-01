# Alpaca stock bars — the shared loader

Status as of 2026-09-30: **staged, not running.** The loader and its master registration are
complete and tested against a mocked client. Nothing talks to Alpaca until the owner saves a
key and says so.

## What it is

`tools/import_alpaca_stocks.py` pulls intraday US **stock** OHLCV from Alpaca and registers
it in the AUGUR library as masters, the same way `tools/import_nt_ohlc.py` does for the
NinjaTrader capture. It is the one place stock bars enter the library — the ROC-frontier
lane (stocks-in-play ORB, NQ breadth), TRADING-LOG (charts for the owner's own stock trades)
and DISCRECTIONALRY-TO-ALGO (setup scoring) all read what it writes rather than each pulling
their own.

## The free plan, and why it is enough

Alpaca's Basic plan serves **historical** bars from the full SIP consolidated tape (100% of
volume) back to 2016. The "IEX only, ~2.5% of volume" limit people quote applies to
**real-time streaming**, not to historical queries. The three limits that do bite:

| Limit | What the loader does |
|---|---|
| `end` must be ≥15 minutes old | defaults `end` to now−20min |
| 10,000 bars per request | pages on `next_page_token` |
| 200 requests/minute | paces at ~195/min, sleeps 20s and retries on 429 |

## Splits, and the source tag

Stock history **must** be split-adjusted. Unadjusted, every split reads as a crash (NVDA
10:1 in 2024, AAPL 4:1 in 2020) and any breakout or gap rule fires on garbage. Alpaca does
this server-side via `adjustment=split`, so there is no custom back-adjust code here — unlike
the futures roll handling in `augur_engine/rolls.py`.

That makes the stock convention the **opposite** of the futures one, which is deliberately
NON-adjusted (`db_noadj_*`, `nt_noadj_*`) so a contract roll stays visible. The two must
never blend inside one master, so stock masters carry their own tag:

    alpaca_split_rth   alpaca_split_eth

Read a stock master by naming that source. The registry key is
`(instrument, timeframe, source)`, so an Alpaca `AAPL 5m` and any futures master coexist
without either touching the other.

## Keys — the agreed names

Read in this order, and never hardcoded:

1. env `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`
2. `augur_config.json` → `alpaca_key` / `alpaca_secret`
3. `tools/.alpaca_keys.json` → `key` / `secret`

**These names are shared, not local to this tool.** `tools/backfill_qqq_5m_alpaca.py`
(PAPER-WB) and `api/spy_daily.py` already read the same two variables, and
`tests/test_import_alpaca_stocks.py` fails if any of the three drifts. Renaming them is a
cross-lane change, not a local one.

## When the keys are saved

```
python tools/import_alpaca_stocks.py --check
python tools/import_alpaca_stocks.py --symbols AAPL,MSFT,NVDA --timeframe 5Min --start 2016-01-01
python tools/import_alpaca_stocks.py --symbols AAPL --timeframe 1Min --start 2024-01-01 --rth
```

`--check` fetches a handful of daily AAPL bars and exits, which is the cheapest proof that a
key works.

Re-running an import is additive while the overlap AGREES: it extends the matching master and
the rows already stored win on a duplicate timestamp.

**When the overlap DISAGREES, the split basis has changed and the master is rebased, not
extended.** `adjustment=split` re-adjusts the whole history as of the moment of the query, so
after a split lands between two pulls the stored bars are on the old basis and the new ones on
the new basis. Splicing them leaves a 10:1 cliff mid-series that every breakout and gap rule
reads as a real crash, and because rows only grow the write guard never sees it. So a
disagreement beyond 0.5% on the shared bars replaces the stored history wholesale, says so in
the log, and is recorded as a deliberate rewrite. If the new pull does not reach as far back as
the stored one, it refuses instead and tells you which `--start` to re-run with, rather than
dropping history.

(An earlier version of this page promised that "a repeat pull can never rewrite history". That
was the wrong promise for split-adjusted data and it is what the rebasing check fixes.)

## What is NOT done

- No account, no key, no live call has been made from this repo.
- Nothing schedules this. Which symbols to hold, at which timeframes, and how often to top
  them up are open questions for whoever consumes them first.
- Dividend adjustment is available (`--adjustment all`) but unused. For intraday breakout
  work `split` is the right default; a total-return study would want `all`, and would need
  its own source tag so the two never mix.
