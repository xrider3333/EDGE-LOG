# ORB rounds 61-62 — the "more alpha" hunt (2026-09-28)

Owner ask via MANAGER: brainstorm ORB variations for more alpha, judged on the owner yardstick (ROC %/yr
at a $30k worst drawdown, beat the raw twin and its Sortino). #314 stays crown. Both triages were
pre-registered and pushed before any number existed; both read pre-lockbox data only.

## The idea list (read against the dead-hunt notes first)

| # | Idea | Mechanism | Data / cost | Main way it could fool us | Status |
|---|---|---|---|---|---|
| 1 | **Carry trend-day winners to the next open** | Trend days keep going overnight; the crown flattens them at 16:00 | Have it; local | Overnight drift, not continuation | **RAN — round 61, DEAD** |
| 2 | **1.5x after a mega-cap earnings report** | The open must price a big information shock to the largest NQ weights → trend day | Free (Yahoo calendar, frozen) | Any 1.5x on 15% of days adds size; survivorship in the name list | **RAN — round 62, DEAD** |
| 3 | **#314 unchanged on RTY and YM** | Opening-auction momentum is an equity-index effect; NQ has it, RTY is the other high-vol index | Databento RTY/YM 5m, owner $ | ES says ORB is point/clock-measured and travels badly (ES PF 1.06) | **Needs the owner (data)** |
| 4 | Compression / Friday / FOMC fixed tilts (already on paper) | Fixed calendar/regime sizing | Have it | On ORB they are leverage: +13% walk-forward money at +14% drawdown | Leave to the paper legs |
| 5 | First-30-min or short-side size tilts | Real ORB edges in the anatomy | Have it | Cost +49% / +57% lockbox drawdown = leverage | Not run — fails the yardstick by construction |
| 6 | #314 tree-model sizing | Learned size | Have it | Learned ML is a coin flip out of sample | Custom ML's forward test (d14b53a8) |
| 7 | ORB on ES / NQ 24h / London-Asia range | Transfer | Have it | — | **Already DEAD**: ES PF 1.06 (top-10 174%), NQ 24h −$69,681, London PF 1.11 |
| 8 | An ORB variant as a new book leg | Diversify BOOK #463 | Have it | Same opening-momentum factor (the GAPGO lesson: a new trigger, not a diversifier) | Not run |

## Round 61 — carry the crown's trend-day winners past the close (DEAD)

`tools/orb_r61_overnight_carry.py` (pre-registered 9bebb399), roll-corrected master; the crown matches the
raw master exactly (2,131 trades, $310,018.54). 72% of crown trades are still open at the close.

| Variant | Carried | Carry money | Longs / shorts | ROC@$30k late half | WF stretch | Verdict |
|---|---:|---:|---|---:|---:|---|
| Raw twin #314 | — | — | — | 41.9%/yr | 35.3%/yr | — |
| C1 carry ≥1R | 206 | +$15,035 | −$7,695 / +$22,730 | 36.9 | 31.2 | **FAIL** — drawdown $28,857 → $34,056 |
| C2 carry ≥2R | 39 | −$21,295 | −$8,585 / −$12,710 | 32.1 | 27.0 | **FAIL** |
| C0 carry all (control) | 1,531 | +$47,390 | +$113,035 / −$65,645 | 25.4 | 21.0 | control — plain overnight drift |
| P1 carry <1R (placebo) | 1,325 | +$32,355 | +$120,730 / −$88,375 | 31.1 | 25.6 | control |

The carry makes some money and buys it with more drawdown than it earns. The controls show the plain
overnight drift: carried longs gain and carried shorts lose.

## Round 62 — 1.5x on the session after a mega-cap earnings report (DEAD)

`tools/orb_r62_earnings_tilt.py` (pre-registered 746f4b2a), calendar `tools/data/megacap_earnings_dates.csv`.

| Calendar | Tilted trades | Extra money | ROC@$30k early / late / WF | Sortino late |
|---|---:|---:|---|---:|
| Raw twin #314 | — | — | 0.7 / 41.9 / 35.3 | 3.22 |
| All 7 names | 204 | +$14,541 | 1.2 / 44.8 / 37.6 | 3.05 (loses) |
| 4 names that were top weights throughout | 121 | +$8,266 | 1.5 / 48.3 / 40.6 | 3.09 (loses) |
| Placebo: the session before | 209 | −$5,885 | 0.7 / 40.6 / 34.3 | 2.89 |

Bar: 1 PASS, 2 **FAIL** (Sortino in the late half), 3 PASS, 4 PASS, 5 **FAIL** (the real calendar's
walk-forward gain of +2.32 pts sits at the **77th percentile** of 2,000 random same-size calendars;
the 95th is +5.14), 6 PASS. **DEAD.** The direction is right (the placebo loses, and the four
long-standing names read stronger), but random calendars of this size do as well about one time in
four, so this is not distinguishable from noise on this history.

## Where that leaves ORB

The NQ ORB tape is mined out for entries, exits, filters and fixed tilts on the data we have. The one
idea with a real prior left is a **new instrument**: #314 unchanged on RTY (and YM as a check). That
needs Databento data, which is an owner call. The ROC-frontier lane's pre-registered Databento transfer
(`tools/rocfrontier/PREREG_TRANSFER_R1.txt`) already includes ORB #314, but only on ZN/6E/CL/GC, where
an equity-open mechanism is least likely to work. Adding RTY/YM to that order is the ORB lane's
recommendation.
