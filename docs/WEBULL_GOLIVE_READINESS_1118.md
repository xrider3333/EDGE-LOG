# WEBULL PAPER go-live readiness: every way paper differed from the book (PAPER-WB, 2026-11-18)

## STATUS 2026-11-19 (supersedes the rows below where they differ)
- **PDT rule:** replaced. SEC approved FINRA SR-FINRA-2025-017 on 2026-04-14, effective 2026-06-04: an intraday margin standard, $2,000 margin minimum (to confirm on the first read-only balance call). The must-fix is now a **buying-power check: BUILT** (v91.01: refuse when an open is over buying power or BP is unread).
- **Sizing + rails for a $3-8k margin account:** SHIPPED v91.01 271e5da8 (equity tiers, 1.5x notional cap, refuse on stale equity, day 2% / week 5% of equity, weekly counts LIVE rows only, adapter daily rail % in LIVE). Owner config; defaults only. Paper replay table in `WEBULL_LIVE_SIZING_1119.md`.
- **Hatch verdict:** SHIPPED v91.00 c11a0cb2 (latency-scaled band, outside-minute flag, ORB breakout = design, book-only broker vs infra). 8 of the 19 old hatched days remain. Page side: TRADING-LOG.
- **ORB late entry (row 7):** FIXED v90.82 04dc5a74, on the box since 11-18.
- **Order latency:** qqqfast v90.93 (about 8 s down to an estimated 3-5 s). Box deploy Fri 11-20 after 16:05 ET, with the ENGU-Q guards, hatch verdict and sizing.
- **Lease / Firestore 429 (row 3):** local lease built (v90.88), not on yet. Rehearsal Fri 11-20 before 09:25 ET. 429 recurred 11-19 01:38 ET (stale web-app tabs).
- **PICK6:** stays PAPER (cannot run at $100k a side in a $3-8k account). One-sided basket and probe-gate fixes are being built.
- **PICK6 MUST-FIX BEFORE LIVE (proposal):** a restart hook for the PICK6 unit (systemd Restart=on-failure or a watchdog, plus a HIGH alert), so a box restart between 15:30 and 16:00 resumes the basket at once instead of at the next 15:27 ET timer. The paper fixes (pair unwind, filled-qty exits at 15:59:00 / 15:59:35, 15:31 late-reject check, saved basket, half-day refusal) shipped with pick6fix.
- **Runbook:** `WEBULL_LIVE_RUNBOOK.md`; the ARM_LIVE end-to-end paper test passes.
- **Owner open:** account choice (separate account recommended), `stock_last4` entry, size tier, OK for one read-only live balance call.

This is a read-only audit. Nothing was deployed or changed.

**What it covers**
- Paper history: 2026-09-03 to 2026-11-18, which is 161 book trades.
  - NOISE 112, ORB 27, ENGU-Q 5, DIP 17.
- 326 broker order rows: 299 sent to Webull in PAPER mode, 27 blocked by our own code.

**Sources**
- The box's `qqq_exec/` CSV files: trades, orders, broker_orders, eod_fill_gap, reprice.
- `corrections.log` and the `FLATTEN_BROKER` markers.
- `journalctl` for `edgelog-qqq-exec`.
- The box's own parity and book-only code (`_apply_broker_parity` and `_apply_book_only`), run against today's files. These produce exactly the caveats the WEBULL PAPER page reads.

**Related reports**
- Slippage statistics: `WEBULL_SLIPPAGE_1118.md`.
- Cause of the 11-13 lease outage: `LEASE_429_1113.md`.
- KEEL sizing: `WEBULL_SIZING_1118.md`.

## Hatch rule (what makes a WEBULL PAPER day yellow)

The rule lives in `index.html`, in `qbCalCav`. A day is hatched if any trade that closed that day has one of these caveats:
- **Failed parity:** a Webull fill more than 15 cents a share worse than the backtest price (`PARITY_TRADE_TOL_PS = 0.15`), or a fill that does not fit the price tape.
- **Book only:** the OPEN never reached Webull.
- **Tape-priced exit:** the exit was priced from the 1-minute price feed instead of a Webull fill.
- **Feed invalid:** the price feed was flagged invalid that day.

The day's trades still count either way.

## Hatched days: 20 in the whole history

| Day | Cause |
|---|---|
| 09-03 | 2 failed parity, no trade id yet (start-up day; corrected in `corrections.log`) |
| 09-23 | 8 book only (Webull refused NOISE opens; see below) |
| 09-24, 09-25, 09-30, 10-05, 10-19, 10-22, 10-23, 10-29, 11-02, 11-09, 11-11, 11-17, 11-18 | 1 failed parity each |
| 10-16, 11-16 | 2 failed parity each |
| 11-04 | 9 failed parity: 8 NOISE + 1 ORB, 10-20 shares each, $34.85 net cost in total |
| 11-05 | 3 failed parity |
| 11-13 | 8 book only (lease 429) and 4 failed parity |

None of the 20 hatched days came from a tape-priced exit or an invalid feed: 0 trades were priced from the tape.

## Ledger

| # | Category | N | $ cost (paper vs book) | Live too? | Fix | Status |
|---|---|---|---|---|---|---|
| 1 | **Failed parity (fill > 15c a share worse)** | 33 trades (26 NOISE, 8 ORB, 1 ENGU-Q), plus 2 start-up rows on 09-03 | -$26.96 net on the 33. Across all 127 compared trades: -$135.50, or -$1.07 a trade | Partly. A market order at the bar close pays spread and a moving quote live as well. Paper fills come off Webull's simulated quote. Mean slip is within the cost model; see the SLIPPAGE report | Nothing to fix in code. Re-check the slip after the first 20 live fills | Watch item, not a blocker |
| 2 | **BOOK ONLY: Webull refused the NOISE open (09-23)** | 8 trades (2 `GENERATE_NEW_SHORT_POSITION`, 6 `ORDER_SIDE_NOT_MATCH_WITH_POSITION_OPEN`) | Book -$24.50. Paper skipped those losers, so paper was +$24.50 better | Yes, without the fix: opposite legs on one symbol collide at the broker | The legs are netted into one broker position | FIXED d14e2a38 (09-23). 0 repeats since |
| 3 | **BOOK ONLY: lease unverifiable, Firestore 429 (11-13)** | 8 NOISE trades, 14:35-15:45 ET | Book -$25.50. Paper skipped them, so paper was +$25.50 better | Yes: the same quota is shared live | Fail-closed stays. The cause is reads from other callers on the shared project (the box uses under 4%). Read-fail grace d40e3006 shipped 11-14, a day too late. It would not have helped, because the writes were refused too | **OPEN**: proposal in `LEASE_429_1113.md`. Needs a read budget per caller, or a separate Firebase project for the box, and a phone alert |
| 4 | **Close refused at 16:00 (`FIXGW_NOT_READY_MARKET`)** | 3 (09-17 ENGU-Q, 09-18 ENGU-Q + ORB) | Positions stranded overnight. They were sold the next Monday by the FLATTEN_BROKER marker (10 ENGU-Q + 10 ORB shares) | Yes | The flat time is clamped to 15:59, with an after-hours fallback | FIXED 5a92806d and d5f0b564 (10-14). 0 repeats |
| 5 | **Close refused as a duplicate order (`DUPLICATE_ORDER_CHECK`)** | 5 (09-21, 10-05, 10-20, 11-09 ×2) | $0 seen: each close was re-queued and filled | Yes | Re-queue the close, and wait out an identical order | FIXED 60fa741a, 4850a997, b2211bf4. The 11-09 pair still hit it but recovered in its tick |
| 6 | **Box order refused (`OPEN_ORDER_HAS_BOX_ORDER`)** | 1 (09-28 ENGU-Q close) | $0 seen | Yes: Webull blocks a buy and a sell-to-open on one stock at once | Covered by the netting in #2. PICK6 must never hold a stock long and short | FIXED for QQQ. A rule for PICK6 |
| 7 | **Late orders (one 5-minute bar late)** | 3 of 83 orders where we have the timing (11-05 ORB entry, 11-09 ORB entry, 11-11 ORB exit, each about 308 s after the bar close). Median 8.4 s, p90 11.4 s | Included in #1. The 11-05 and 11-09 ORB entries were 130c and 145c a share worse | Yes | NOISE was fixed 481ba5c5 (09-26). **ORB still has 3 cases of a whole bar late in November** | **OPEN**: find why ORB sometimes misses its bar |
| 8 | **Exits with nothing to close (our block)** | 17 | $0. These are the closes of the book-only trades in #2 and #3 | Same as #2 and #3 | Correct behaviour: never sell what Webull never got (60fa741a) | Fine |
| 9 | **Reconcile halt** | 1 (`QQQ broker=10 shadow_sent=0`, 09-21) | $0 | Yes | Re-send after a false halt (60fa741a). Since 11-16 the reconcile also ignores the PICK6 book's symbols (v89.76) | FIXED |
| 10 | **One leg already open (our block)** | 1 (ENGU-Q) | $0 | n/a, a rule | Rule: one open position per leg | Fine |
| 11 | **DIP loss rail** | Tripped 11-05 (-$801.27). The 11-06 IBS and GAPDN entries were refused | Book and paper match: the rail is part of both | n/a | DIP retired: config 11-06, code 05ad86e8, deployed ad2c4142 11-18 | CLOSED |
| 12 | **Partial fills** | 0 seen. Fill check: 125 OK, 1 suspect (ENGU-Q 09-24, "fill does not fit the tape") | $0 | Possible at size, but QQQ at 10-20 shares is no risk | none | Fine |
| 13 | **Restarts during market hours** | 0. There were 20 stop/start pairs, all deploys outside RTH or on weekends. One crash loop of about 98 restarts on 09-21 00:29-02:3x UTC (Sunday evening, market closed) | $0 | n/a | Deploys only go through box_deploy, which refuses 09:25-16:05 ET | Fine |
| 14 | **Clock problems** | 0 found in the journal | $0 | none | none | Fine |
| 15 | **EOD fill vs the 16:00 close** | 42 EOD exits. Fill vs close: mean -$0.168 a share, median -$0.075 (exits are at 15:59, before the close print) | Part of #1 | Yes, by design | none | Fine |
| 16 | **Data fixes (`corrections.log`)** | 30 entries, all 09-03 to early Oct: start-up backfills, the entry-price EOD bug (pre-v73.469), the feed-uptime seed | Fixed in the files | No | Code fixed | FIXED |
| 17 | **KEEL sizing (10 vs 15 shares)** | See `WEBULL_SIZING_1118.md`: the size multiplier does reach the order. KEEL trust is 0 today, by design | n/a | n/a | none | Not a blocker |

### What paper missed vs the book in dollars

- **Book-only trades:** 16 trades, book total -$50.00. Paper skipped them all, so this happened to help paper.
- **Fill difference:** -$135.50 across 127 compared trades.
- **Net:** paper ran about -$85.50 vs the book over 11 weeks, or about -$0.53 a book trade.

## MUST FIX BEFORE LIVE

1. **Firestore quota and lease** (#3). Give the box its own read budget or its own Firebase project. Add a phone alert the first minute a 429 or "lease unverifiable" happens. Proposal: `LEASE_429_1113.md`.
2. **ORB orders one bar late** (#7). There were 3 in November, and two of them cost about 1.3-1.5 dollars a share. Find the cause the way it was found for NOISE (481ba5c5).

## FINE TO GO

- Broker refusals 09-17 to 10-20: all fixed, no repeats.
- Duplicate closes recover by themselves.
- No partial fills. No clock problems. No restarts during market hours.
- Fill slippage is within the cost model. Keep watching it once live.
- KEEL sizing is wired.
- DIP retired.
- The 11-13 fail-closed behaviour was correct and stays.

## ORB orders one bar late - cause found (PAPER-WB, 11-18, read-only)

**Cause (all entries): a strategy-file guard, not the feed, the loop, the API or the lease.**
`augur_strategies/ORB_3_6.py` evaluates a session only when it has `m > or_bars + 1` bars (or_bars = 2, so 4 or more).
The box re-runs the engine on a GROWING intraday window. At 09:45:07 the day has 3 closed bars (09:30, 09:35, 09:40), so the whole session is skipped, even when the 09:40 bar already broke out.
At 09:50:07 the 09:45 bar makes 4. The engine then finds the 09:40 breakout and the box sends it a full bar late.
The backtest always has the whole day (about 78 bars), so the book takes the 09:40 bar on time.
The rule: **every ORB signal on the first eligible bar (09:40) goes one bar late; every later bar is on time.**

| Day | Signal bar | Sent | On-time price (09:40 bar close) | Webull fill | Cost per share | Cost per trade (10 sh) |
|---|---|---|---|---|---|---|
| 11-03 long | 09:40 | 09:50:11 | 686.94 | not captured | ? | ? |
| 11-04 long | 09:40 | 09:50:10 | 697.59 | 697.40 | -0.19 (better) | +$1.90 |
| 11-05 short | 09:40 | 09:50:07 | 671.10 | 669.80 | 1.30 worse | -$13.00 |
| 11-09 long | 09:40 | 09:50:07 | 670.55 | 672.00 | 1.45 worse | -$14.53 |

- **Late entries:** **4**, not 3. 11-03 and 11-04 were late too; their orders.csv rows predate the latency column. 11-06 and 11-10 (09:45 and 09:50 signal bars) and the October 09:45 entries were on time.
- **Total cost:** **-$25.63** on the 3 with a captured fill. The cost is direction-random: one bar of drift, either way.
- **Live:** yes, the same engine call runs live. The expected cost is zero on average, but each late entry is a coin flip of about one bar's range (about $1-1.5 a share on QQQ at the open).
- **11-11 ORB exit (15:30:07, after_close 307 s):** this is a different case. The exit filled 5c *better* than book (691.15 vs 691.10), so it cost $0. The likely cause is a stop/breakeven level touched inside an earlier bar, which bar-close execution only sees at the close. Not verified; the resting-stop path is still log_only.

**Fix PROPOSAL (no code yet; needs MANAGER GO):**
1. In ORB_3_6, change the session guard from `m > or_bars + 1` to `m > or_bars`. It then evaluates as soon as the first post-range bar (09:40) has closed.
   - Backtest-neutral: full sessions always have more than 3 bars. Re-run the ORB #314 or R6 golden parity to prove 0 trades differ.
   - Alternative, with the strategy file untouched: in the box's live engine call, pad the growing window with one placeholder bar (never tradeable).
2. Add a box alert: an ORB order whose after_close is over 60 s gets logged as LATE with its signal bar. Today it only shows in the latency column.
3. Optional, for exits: arm the resting stop (now log_only) so ORB stops fill at the stop level, not at the next bar close.

## LIVE cutover: the VERIFIER's list, checked against the code (2026-11-18)

Source: `C:/EdgeLog/_anatomy_cache/ttm_w119/GOLIVE_SKEPTIC_1118.md`. Read-only check. No login, no broker call, nothing on the box.
**OWNER Q** = a question only the owner can answer.

| # | Item | Verdict | Code evidence | Fix proposal | Bucket |
|---|------|---------|---------------|--------------|--------|
| 1 | One state.json for PAPER and LIVE | **REFUTED** (fixed by B1, d72b59f2) | LIVE uses `state.LIVE.json` (api/webull_orders.py:1166-1175). It refuses to arm while the paper state still holds shares (1269-1274). Disarm with live shares held = close-only (1250-1260). Tests at tests/test_webull_orders_live_switch.py:34,44,55. | None needed for the adapter. See 1b. | fine |
| 1b | Residual: the qqq_exec loss stops mix modes | CONFIRMED (small) | The realised-P&L reader takes PAPER and LIVE rows of broker_orders.csv alike (api/qqq_exec.py:~5466). The `loss_stop` anchors sit in one qqq_exec state (qqq_exec.py:778). The paper-held check reads our own state only, not the Webull paper account. | When LIVE, count only `mode==LIVE` rows. Cut over after the close on a Friday, both books flat. Archive the qqq_exec `loss_stop` block. | should-fix |
| 2 | Pattern-day-trader rule | **CONFIRMED** | No PDT, day-trade or buying-power code anywhere in api/. The balance read takes only net_liq and cash (webull_orders.py:4280-4292). SDK 2.0.12 has `account_v2.get_account_balance` (GET /trading/assets/balances/get) and `preview_order` (v2/v3). Both return untyped dicts. The public reference page lists no fields, so a day-trades-left / PDT field name is UNVERIFIED. | **OWNER Q:** is live equity at least $25k plus a buffer, and is the account margin or cash? Then log the raw keys of one live balance response, add a pre-open check (day trades left or equity under $25k + buffer = refuse the open and push an alert). | must-fix |
| 3 | Buying power at live size | **CONFIRMED** | No buying-power read or check before a send (same lines as 2). Paper is $1M (webull_orders.py:297). | Read buying power once a session plus before each PICK6 basket. If the planned gross is over 80 pct of it, refuse and push an alert. Write planned size per leg vs equity in this doc. **OWNER Q:** live equity and PICK6 size per side. | must-fix |
| 4 | PICK6 short refused leaves a one-sided long basket | **CONFIRMED** (latent: PICK6 runs PAPER only, api/eodrev_exec.py:228-229) | Refused entries only trigger a phone alert (eodrev_exec.py:340-343). The other names stay open, and their MOCs go out (349). No borrow or SSR check exists. | On any refused short: close the matching long at once (or the whole basket; **OWNER Q:** which one), push an alert with the reason, and log refusal reasons. | must-fix (before PICK6 live) |
| 5 | PICK6 exit is MOC; live refuses MOC | **CONFIRMED** | MOC exit (eodrev_exec.py:349), MARKET fallback at 15:58 (DEFAULTS, eodrev_exec.py:40-53). Webull refuses MOC/AT_AUCTION live (417). The 11-18 probe's MARKET exits went at 15:57 and filled 0-8c vs that minute, but -45c to +30c vs the close. `probe_ok` needs `moc_ok` (202-210), so a live probe could never pass: the gate holds. | Keep PICK6 PAPER. Rewrite the exit as a 15:57 MARKET order, run a 1-share live probe, and re-score #511 with a 15:57 exit before PICK6 counts in a live book. | must-fix (before PICK6 live) |
| 6 | Loss rail sized for paper | CONFIRMED | `daily_loss_limit_usd: 150` (qqq_exec.py:281). PICK6 has its own rail of $400 (eodrev_exec.py:45). | Set both to the live size. **OWNER Q:** rail $ per book. | should-fix |
| 7 | SEC/TAF fees | CONFIRMED (not modelled) | Fees are read from Webull's order record (webull_orders.py:501-547), but they are not in the cost line. eodrev_exec has no fee term. | Add the SEC fee + TAF on sells to the PICK6 cost line (about $700 a year at $100k a side). Log fees from the first live fills. | should-fix |
| 8 | Live token never exercised | CONFIRMED | The expiry gate exists (198d9beb; tools/webull_freshness.py:1088), but no live call has run on the box. | **OWNER Q:** run one read-only live balance call on the box the day before arming. Re-auth stays manual. | should-fix |
| 9 | ARM_LIVE removal end to end + runbook | PARTLY | Unit tests cover close-only on disarm (test_webull_orders_live_switch.py:44,55). There is no end-to-end run and no runbook. | Run a PAPER dry run with a simulated arm file. Write a 5-line owner runbook (KILL = stop; KILL + check the app = flatten; what the phone says). | should-fix |
| 10 | Half days for PICK6 | CONFIRMED | eodrev_exec has no calendar. It skips only on a `SKIP` signal, which comes from missing bars (eodrev_exec.py:127). | Call market_calendar in eodrev_exec and skip half days. | should-fix |
| 11 | DST / tzdata | fine | qqq_exec.py:97-99, 448-453 | none | fine |
| 12 | LULD halts | noted | No halt code path. FLATTEN_BROKER catches a position stranded overnight. | Add a line to the runbook. | fine |
| 13 | Duplicate signal process | fine | host slot + serving_hosts | none | fine |
| 14 | First-day size | noted | No doc names it. | Days 1-5: 1 share per QQQ leg, PICK6 off. | fine |

**Counts:** must-fix 4 (2, 3, 4, 5) · should-fix 6 (1b, 6, 7, 8, 9, 10) · fine 5 (1, 11, 12, 13, 14).

**Owner questions:** (a) live equity, margin or cash, and PDT status; (b) PICK6 size per side live; (c) on a refused short, drop the matching long or the whole day; (d) loss rail $ per book at live size; (e) run one read-only live balance call on the box before arming.
