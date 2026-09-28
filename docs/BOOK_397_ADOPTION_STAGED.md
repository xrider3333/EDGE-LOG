# Adopting BOOK #397 (FRONTIER) over #366 - DROPPED 2026-09-28 (staged 2026-09-27)

**Status: DROPPED on 2026-09-28** (owner via MANAGER). The owner adopted BOOK #449 on the fixed legs
(run #463) instead - BOOK.md section 10n. Nothing in this file was applied, and branch
`stage/adopt-397` is dead; it is kept only as a record.

## 1. What BOOK #397 is, in five lines

1. #397 is the same four-strategy account as the adopted #366: one NQ contract each of ORB, ENGU-Q and NOISE, plus three ES contracts of TTM.
2. Two legs change. ORB keeps its rules but tightens two entry filters (run #297's settings), so it takes fewer, pickier trades. TTM moves to its newest validated version (run #369), which adds size on its best trades and waits one more bar before exiting.
3. ENGU-Q #335 and NOISE #304 do not change.
4. On roll-corrected prices (run #437) it makes 88.1 % a year before the lockbox and 293.3 % in the lockbox year, against 84.4 % and 277.1 % for #366 (run #435). Its worst drawdown is about the same ($40,971 against $40,854), and its lockbox drawdown is smaller ($25,893 against $28,066).
5. It is not a new strategy: it is #366 with two validated leg upgrades, and it held all 8 stretches both before and after the roll correction.

## 2. What changes: legs, weights and sizes

| Leg | #366 (adopted) | #397 (staged) | Change |
|---|---|---|---|
| ORB, 1 NQ | `ORB_3_6_C2.py` = run #234: volume-pace filter 0.70, ATR filter 0.70 | `ORB_3_6.py` at run #297's settings: volume-pace filter **0.80**, ATR filter **0.75**; every other setting identical | Two filters tighter. 2,278 trades against 2,584 over the window |
| ENGU-Q, 1 NQ | `ENGUQ_1M_ETH_R2_1_0.py` = run #335, 0.783 points a round trip | same | none |
| TTM, 3 ES | `TTMSQZ_3_0_ES30SS20.py` = run #353: structural stop and the deep-squeeze tilt, so 3 ES base and 4.5 on deep-squeeze trades | `TTMSQZ_3_0_ES30SSOF2.py` = run #369: adds the session open-bar tilt and the exit on the second fading bar, so 3 ES base, **4.5** with one tilt, **6.75** with both | 355 trades against 358 |
| NOISE, 1 NQ | `NOISE_1_1_NBHD.py` = run #304 | same | none |

Where #397's lead comes from. **#396 is the half-step:** it is #366 with only the TTM swap, and it reads
89.1 / 294.4 % a year roll-corrected (run #436). The ORB swap on top of it gives back about one point of
return a year and buys a lower drawdown in both stretches: before the lockbox $40,971 against $43,967, and
in the lockbox $25,893 against $27,506. One caution from the ORB chat's own work (ORB round 59): on
#257's settings, a tighter volatility filter earns less by calendar year. The #297 filters cost the ORB
leg $16,778 over the window here ($356,527 against $373,305), and they are kept for their drawdown, not
their money.

## 3. Paper and live: exactly what changes at the flip

**Paper** (`api/paper.py`, owned by the PAPER-NT8 chat; staged in the branch for its review):
- **New paper leg `ORB_297`:** `ORB_3_6.py` at #297's settings, NQ 5m RTH, same costs and source as the
  `ORB` leg. No #297 paper leg exists today. The #234 leg (`ORB`) keeps running as its matched control.
- **TTM: no paper change.** The book-weight TTM paper leg is already `TTM_299_SSOF2` (#369).
- **ENGU-Q (`ENGUQ_335`) and NOISE (`NOISE_304`): no change.**
- **The nightly report's book figure changes.** Today it adds ORB #234 x1 + ENGU-Q **#309** x1 + TTM #369
  x3 and names run #371. It never followed the #366 adoption: it has no NOISE leg, and it still uses
  ENGU-Q #309. After the flip it adds ORB #297 x1 + ENGU-Q #335 x1 + TTM #369 x3 + NOISE #304 x1 and
  names run #397.
- **Cost note, no change made:** the book prices ENGU-Q at 0.783 points a round trip (24-hour convention),
  while the paper leg prices it at 0.533.

**Live** (NinjaTrader sim strategies):
- The NT ORB strategy (`EdgeLogORBV2`) has **no volume-pace or ATR filter inputs**. It cannot express
  #234's filters today, and it cannot express #297's. Trading #397's ORB leg on NinjaTrader needs those two
  inputs added (PAPER-NT8 chat). Until then, the flip changes the paper and backtest book only.
- TTM has no NinjaTrader strategy; it stays paper-only. ENGU-Q and NOISE on NinjaTrader are unchanged.
- The Webull QQQ book is a separate account with its own legs (ORB #314, ENGU-Q #335, NOISE #382). It is
  not affected.

## 4. Before and after

ROC %/yr is net a year on a $100k account. Pre = 2010-06-07..2025-06-29, lockbox = 2025-06-30..2026-06-30.
Sortino uses daily at-close book P&L on $100k, every weekday counted, times the square root of 252.

| Book | ROC %/yr pre / lockbox | Pre DD at close / valued daily | Lockbox DD at close / valued daily | Sortino pre / lockbox | Stretches |
|---|---|---|---|---|---|
| #366 stored (adopted) | 92.7 / 290.0 | $36,562 / $37,444 | $28,066 / $49,855 | - | 8/8 |
| #397 stored (staged) | 97.4 / 306.3 | $33,567 / $34,449 | $25,357 / $49,855 | - | 8/8 |
| **#435 = #366 roll-corrected** | 84.4 / 277.1 | $40,854 / $41,736 | $28,066 / $49,855 | 3.80 / 5.85 | 8/8 |
| **#437 = #397 roll-corrected** | **88.1 / 293.3** | $40,971 / $41,853 | **$25,893** / $49,855 | **3.98 / 6.31** | 8/8 |

- At the same risk (each scaled to #435's pre-lockbox drawdown, $40,854), #437 reads 87.9 / 292.5 against
  #435's 84.4 / 277.1.
- #437 makes more than #435 in 10 of the 15 full years 2011-2025.
- Both worst stretches are the same Feb-Mar 2020 crash (2020-02-25 to 2020-03-27).
- The stored figures are on the no-adjust masters. Read the roll-corrected rows (ROLL_AUDIT.md; BOOK.md 10i).

**CORRECTION 2026-09-28 - read BOOK.md 10m first.** The TTM stop bug (b3242e77) inflated every book above
that carries a structural-stop TTM leg. Re-run on the fixed files, #437 (#397's twin) reads 80.8 / 256.3 %/yr
against #435 (#366's twin) 79.4 / 252.1. The advantage section 4 describes has mostly gone, and #437 fails the
lockbox concentration clause against #449. The staged flip below is unchanged and still ready, but its
evidence is weak.

## 5. The TTM chat's staged leg, as variants on #437

All variants swap only the TTM leg of #437. The #437 TTM leg (the #369 cell on the back-adjusted master)
**is already the roll-guarded #369 cell**: 355 trades, $121,491 per unit of weight, the exact figure the
roll-guard file measured at #369's settings. Whole contracts are priced the way TTM round 18 priced them:
contracts x (points - 0.363) x $50, with 3 / 4 / 7 ES for zero, one or two tilts. A parity gate first
rebuilt the fractional ladder from the recomputed tilt flags and matched the engine's own leg dollars to
the cent on both TTM cells.

| Variant | TTM leg | ROC %/yr pre / lockbox | Pre DD at close / valued daily | Lockbox DD at close | Sortino pre / lockbox | At #435's DD |
|---|---|---|---|---|---|---|
| #437 as run | #369 cell, 3 / 4.5 / 6.75 | 88.1 / 293.3 | $40,971 / $41,853 | $25,893 | 3.98 / 6.31 | 87.9 / 292.5 |
| V347 | #369 cell, **3 / 4 / 7** | 88.3 / 290.7 | $40,971 / $41,853 | $25,893 | 4.00 / 6.26 | 88.0 / 289.9 |
| V428 (= run #445) | **#428 cell** (roll guard, entry cutoff 5), 3 / 4.5 / 6.75 | 87.6 / 295.6 | **$33,567** / $34,449 | $25,893 | 4.02 / 6.37 | 106.6 / 359.8 |
| V428_347 | #428 cell, **3 / 4 / 7** | 87.8 / 292.7 | $33,567 / $34,449 | $25,893 | 4.03 / 6.31 | 106.8 / 356.3 |

Reading:
- **Whole contracts (3 / 4 / 7) are an execution detail, not a decision.** They make half contracts
  tradable and change the book by about a point a year: +0.2 before the lockbox, -2.6 in it. Drawdowns
  are unchanged. Under 3 / 4 / 7 the #369 leg averages 4.05 ES a trade.
- **The #428 cell trades 246 times against 355** and removes $7,404 of the Feb-Mar 2020 drawdown. The
  other three legs are identical, so the whole gain is in the TTM leg. The lockbox is +2.3 points at the
  same lockbox drawdown.
- **Two cautions on #428.** Its entry cutoff (5 bars against 1) was chosen by its own search over the
  pre-lockbox years, so part of the pre-lockbox drawdown gain is in-sample. It also PASSED 6 of 6 (overfit
  0.036) but missed its own pre-registered return-per-drawdown clause (1.29 against 1.31, TTM.md round 18).
- **Suggested split (the owner decides):** adopt #397 as #437 runs it, which changes no TTM paper leg. Treat
  the #428 cell and 3 / 4 / 7 as the TTM chat's separate leg decision, which can follow on its own evidence.

V428 is persisted as real run #445 (BOOK.md 10k), equal to this figure to the cent. Script, log and parity: `C:\EdgeLog\_anatomy_cache\stage397\` (`variants.py`, `variants.log`,
`variants.json`, `legs_diff.py`). #435 and #437 were reproduced to the dollar before any variant was
read.

## 6. The flip (ready, not applied)

Branch `stage/adopt-397` holds one commit that, on the owner's confirm:
- marks #397 as the adopted book in BOOK.md (banner), BOOKMARKS.md (a new ADOPTED section above #366's)
  and BACKTESTING_STACK.md (the headline);
- adds the `ORB_297` paper leg and points the nightly book figure at #397's four legs (`api/paper.py`);
- sets this file's status to ADOPTED.

The flip date is a placeholder (`@@FLIP_DATE@@`) that the flip script fills in. The script refuses to push
while the placeholder remains, while any paper test fails, or when the diff touches more than those five
files.

After the push:
- Restart the runner with `tools/fleet_restart.py --keep`, outside market hours. The paper change runs in
  the runner, and a shipped change is not running until then.
- Set these RUNBOARD verdicts:
  - `#366` Adopted until the flip date; replaced by #397
  - `#397` ADOPTED BOOK
  - `#437` Adopted book #397, roll-corrected
  - `#396` Half-step to #397: the TTM swap only
- The owner's star on #366 is web-owned; moving it is the owner's click.
- The NinjaTrader ORB filter inputs are a separate PAPER-NT8 task (section 3).
