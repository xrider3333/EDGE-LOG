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
| 200 requests/minute, **per account** | `augur_engine/alpaca_rate.py` paces every request in every process against one shared budget (180/min, leaving headroom); still sleeps 20s and retries on a 429 |

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

## Keys — one lookup, in `augur_engine/alpaca_keys.py`

Nothing resolves the key for itself. The order, first hit wins:

1. `os.environ` → `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`
2. **`HKCU\Environment` via `winreg`** — the same Windows *user* variables, read straight
   from the registry
3. `C:\EdgeLog\secrets\alpaca_keys.json` → `key` / `secret`
4. `augur_config.json` → `alpaca_key` / `alpaca_secret`
5. `tools/.alpaca_keys.json` → `key` / `secret`

**Why the registry is in there.** The owner saved the key as Windows *user* environment
variables. A process only inherits those if it started afterwards, so every runner process
and every open session was blind to them, and restarting the fleet to pick up a variable is
a poor trade. Windows keeps user variables in the registry, so reading `HKCU\Environment`
is the same fact from the same place with no restart. Read-only, exactly those two value
names, and every failure (not Windows, no such value, no permission) is simply "not found".

The value is returned to the caller and **never printed, logged or written**.
`alpaca_keys.describe()` says *where* a key came from for a diagnostic line, never what it
is — not even a prefix, because an Alpaca key id identifies the account on its own.

`tools/backfill_qqq_5m_alpaca.py` used to prefer the out-of-repo secrets file over the
environment. The environment wins now: the argument for that file was about where a key is
*stored* (outside the repo, so it cannot be committed by accident), not about which source
should win when two disagree — and an environment variable is the only override you can
apply to one command without editing a file.

Every JSON file is read `utf-8-sig`, never `utf-8`: PowerShell 5.1's `Set-Content
-Encoding utf8` writes a BOM, and `utf-8` raises "Unexpected UTF-8 BOM" on it.

## The 200/min cap is per ACCOUNT, not per process

Five lanes pull through the same key (NQBRD, TTM 20c, TBIS r3, TRANSFER r2, SIPORB). Each
tool used to pace itself at ~195/min on the assumption that it was alone, so two at once
was already over the cap and five was five times over — and the symptom is not a clean
error but every lane 429ing, sleeping 20s, and colliding again on the way back.

`augur_engine/alpaca_rate.py` is a token bucket in one small file
(`%EDGELOG_HOME%\state\alpaca_rate.json`) that every request in every process passes
through, so the lanes can all run at once and the **account** stays under the cap.
`ALPACA_RATE_PER_MIN` raises the budget if the plan ever does. It fails **open** — a
corrupt state file, a lock it cannot take, no state directory: the request goes through
rather than raising, because a limiter that can kill a six-hour pull is worse than the
429s it exists to avoid. Each tool's own `sleep(0.31)` is still there underneath as the
floor.

`python tools/alpaca_rate_check.py` proves it across real processes in about a minute, and
is worth running after any change to the locking or the window arithmetic — it is what
caught the two defects the single-process tests could not: a lock whose stale-breaker fired
later than its own timeout, so a lane waited ten seconds and then sent an **unrecorded**
request (ten requests at a cap of six put nine in one window). The lock is an OS lock now,
which the kernel releases when a process dies, so there is no leftover to break.

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

- Keys are saved (2026-10-02, Windows user environment). No live call has been made from
  this repo yet.
- Nothing schedules this. Which symbols to hold, at which timeframes, and how often to top
  them up are open questions for whoever consumes them first.
- Dividend adjustment is available (`--adjustment all`) but unused. For intraday breakout
  work `split` is the right default; a total-return study would want `all`, and would need
  its own source tag so the two never mix.
