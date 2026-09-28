# Databento transfer test r1 - Step 1: data spec, price, owner steps

Owner decision 2026-09-28 (via MANAGER, inbox #5): run ORB, NOISE and TTM unchanged on ZN, 6E, CL and GC
1-minute data. **Step 1 only**: this spec, the exact public price, the owner's own account and key steps, and the
pre-registration (`PREREG_TRANSFER_R1.txt`, same folder). Nothing has been bought, and no account or key has been
touched by Claude.

## 1. The data order

| Field | Value |
|---|---|
| Dataset | `GLBX.MDP3` (CME Globex MDP 3.0 - covers CME, CBOT, NYMEX, COMEX) |
| Schema | `ohlcv-1m` (1-minute open/high/low/close/volume, trade-based) |
| Symbols | `ZN.FUT`, `6E.FUT`, `CL.FUT`, `GC.FUT`, plus `RTY.FUT` and `YM.FUT` (added 2026-09-28, MANAGER inbox #7 - ORB #314 cells, `PREREG_TRANSFER_R1B.txt`; RTY exists on CME only since July 2017) |
| Symbology | `stype_in = parent` (every contract month + calendar spreads), `stype_out = instrument_id` |
| Dates | start 2010-06-06 00:00 UTC (the dataset's first day, same as the June ES/NQ order) -> end 00:00 UTC on the order day |
| Delivery | batch download, CSV, zstd compression (same price, ~10x less disk), split by symbol (one file per contract), `map_symbols` on, `pretty_px` on |
| Storage | `C:\EdgeLog\databento\<job id>\` - outside git and outside OneDrive |

This mirrors the June 2026 ES/NQ order (job GLBX-20260608-B6AGM6RSLW, `databento_raw/metadata.json`) so the same
tooling applies.

**Roll handling (the build, Step 2).** Calendar spreads (symbols with a `-`) are dropped. Contracts are keyed by
`instrument_id`, never by symbol (the one-digit year code repeats every decade). The front month is picked by the
house rule in `tools/stitch_databento.py`: daily volume dominance, forward-only, switch at the UTC day boundary -
which falls outside every trading window below. Every switch gets an EXACT offset from the last minute both
contracts traded (Panama back-adjustment), written as a house roll table `tools/data/rolls_<ROOT>.csv`. Two
masters per market: the raw stitch (what the ORB and NOISE crowns read on NQ) and the back-adjusted one.
Prices keep full tick precision (6E 0.00005, ZN 1/64); the June tool's 4-decimal rounding is not reused. Masters
are registered only under the new instrument names, after checking that no unpinned lookup re-points.

**Sessions** (the owner's NinjaTrader 8 templates): ZN 08:20-15:00 ET, 6E 08:20-15:00 ET, CL 09:00-14:30 ET,
GC 08:20-13:30 ET; RTY and YM 09:30-16:00 ET (the equity-index clock the ORB crown uses on NQ); 5-minute and
30-minute bars anchored at the session open.

**Contract economics** (house cost = $5.66 round-trip commission + 1 tick): ZN $1,000/pt, tick 1/64 = $15.625,
cost $21.29; 6E $125,000/pt, tick 0.00005 = $6.25, cost $11.91; CL $1,000/pt, tick 0.01 = $10, cost $15.66;
GC $100/pt, tick 0.10 = $10, cost $15.66; RTY $50/pt, tick 0.10 = $5, cost $10.66; YM $5/pt, tick 1 = $5, cost $10.66.

## 2. The exact price (Databento's public pricing page, read 2026-09-28)

| Route | Price | Source |
|---|---|---|
| Pay-as-you-go (usage-based) | **$434.13** for the four markets (6.7 GB): CL $323.54 · GC $57.68 · 6E $28.30 · ZN $24.61; **+$36.97 for RTY + YM** (567 MB: YM $23.76, RTY $13.21) = **$471.10** in all | pricing-page estimator: CME, OHLCV-1m, "Entire history" 2010-06-06 -> 2026-09-27 (5,958 days), "No subscription required"; OHLCV-1m rate **$70.00 per GB** |
| **Standard CME plan (recommended)** | **$199 for one month**, then cancel - covers all six markets, RTY and YM add nothing | pricing page: "$199 per month · Monthly subscription · No license fees · 16+ years of L0 history"; L0 = "Aggregate bars (OHLCV-1s/1m/1d/1h), instrument definitions, statistics, status" |

- The per-market split is the difference between the estimator's running totals as each market was added. CL is
  most of the bill because the parent symbol brings every monthly contract and spread it has ever listed.
- Calibration: the same estimator prices ES alone at 487.5 MB / $31.78; our real June ES order holds 8.52 M
  records = 477 MB through 2026-06-07, so it is right to about 1%. Databento bills the uncompressed binary size,
  whatever format is downloaded.
- New accounts get $125 of free credit (expires 6 months after sign-up, one set per team). If any is left from
  June it comes off the pay-as-you-go price.
- The Standard plan is cheaper for this order and also covers every other CME market's 1-minute and 1-second
  history for 16+ years during that month, at no extra cost.

## 3. What the OWNER does (Claude never creates accounts, never sees passwords or keys)

1. Go to databento.com and log in with the account used for the June ES/NQ download (or "Sign up" with your own
   email if you cannot get in).
2. Choose how to pay: **Standard CME plan, $199/month** (recommended - put a reminder to cancel it before the
   renewal date), or pay-as-you-go with a card and a monthly budget cap of $450 set in the portal.
3. In the portal open **API keys** and create a key (or copy the existing one). It starts with `db-`.
4. Save it on this PC: Start -> type "environment variables" -> "Edit environment variables for your account" ->
   under **User variables** click **New...** -> Name `DATABENTO_API_KEY` -> Value: paste the key -> OK -> OK.
5. Restart the Claude app so it sees the new setting, then tell MANAGER only **"Databento key saved"**. Never
   paste the key into any chat, file or message.

## 4. Step 2 (only after "key saved")

1. Claude runs Databento's free price check for exactly this order (no data is bought) and reports the figure.
2. Standard plan: Claude pulls only if that check shows $0.00; any other figure stops and goes back to MANAGER.
   Pay-as-you-go: nothing is bought by Claude - the owner places the download himself in the portal with the
   fields in section 1 (same screen as the June order).
3. Build and data gates (roll tables, sessions, precision, a spot-check against NinjaTrader) - then the
   pre-registered test, `PREREG_TRANSFER_R1.txt`.

Side note for the owner's journal (not this lane): `api/nt_sync.py` and `index.html` value a ZN tick at $31.25;
ZN's 1/64 tick is $15.625 ($31.25 is ZB's 1/32 tick). It only matters if ZN trades are ever logged.
