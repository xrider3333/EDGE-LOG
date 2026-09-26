# The 2026 summer holes in the 1-minute masters: what can and cannot be filled (2026-09-26)

Companion to `ROLL_AUDIT.md` section 2.7, which established the holes. This answers the
next question - **can we fill them from data already on this machine?** - with measured
numbers, so the decision does not have to be made on a hunch.

## The holes, re-verified against the files

Confirmed row-to-row: a hard jump with no filler rows in between.

| Master | Last bar before | First bar after | Length |
|---|---|---|---|
| `NOADJ_ES_1m_RTH.csv` | 2026-06-30 10:49 ET | 2026-08-06 09:30 ET | ~36.9 days |
| `NOADJ_NQ_1m_RTH.csv` | 2026-07-16 15:59 ET | 2026-08-06 09:30 ET | ~20.7 days |
| `NOADJ_ES_1m_ETH.csv` | 2026-06-30 10:49 ET | 2026-08-06 00:09 ET | ~36.7 days |
| `NOADJ_NQ_1m_ETH.csv` | 2026-06-30 10:49 ET | 2026-08-06 00:09 ET | ~36.7 days |

The 5-minute masters have no July hole. NQ 1m RTH's shorter hole is because roughly 4,599
extra rows exist for 06-30..07-16 that ES does not have; who wrote them is still unknown.

## What could fill them

**`databento_raw` cannot.** It is one batch job, `GLBX-20260608-B6AGM6RSLW`, whose query end
is 2026-06-07 16:30 UTC; the last row in a per-contract file is 2026-06-05 20:59 UTC. That is
three weeks before the hole starts. **A fresh Databento pull for 2026-06..09 is the only
source of independent, authoritative data for this window.** Nothing already on disk is
Databento-sourced for these dates.

**The NinjaTrader capture can cover most of it.** Coverage measured minute by minute against
each master's own gap, counting only minutes the capture actually holds:

| Hole | Source | Trading minutes covered |
|---|---|---|
| NQ 1m RTH | `master_b3bf23b6.csv` (NQ 1m, built from the 10s capture) | 5,147 of 5,460 (94.3%) |
| NQ 1m ETH | same | 34,820 of 34,821 |
| ES 1m RTH | `master_c279374a.csv` (ES 10s) aggregated to 1m | 9,747 of 10,450 (93.3%) |
| ES 1m ETH | same | 34,821 available |

The shortfalls are explained, not mysterious: **2026-07-24** is a real capture outage (only 77
of 390 RTH minutes on both roots) and **2026-07-03** is a genuine holiday closure before
July 4th, which `ROLL_AUDIT.md` already documents as a gap in the capture too. No local file
can supply either.

## Why filling from the capture is not a free repair

The capture and the masters are **different feeds**, and they disagree. Measured on real
overlapping minutes outside the holes, requiring an exact match:

| Overlap | Minutes compared | OHLC exact | OHLCV exact | Worst close difference |
|---|---|---|---|---|
| NQ RTH, before the hole | 6,240 | 96.8% | 92.1% | 16.00 |
| NQ RTH, after the hole | 1,987 | 92.2% | 78.2% | 5.25 |
| NQ ETH, before / after | 6,479 / 7,664 | 95.2% / 96.8% | 87.3% / 90.5% | 85.25 / 18.00 |
| ES RTH, before the hole | 1,640 | 95.4% | 64.6% | 4.00 |
| ES ETH, before the hole | 6,478 | 98.1% | 86.5% | 4.50 |

So a capture fill would put rows into a `db_noadj_*` master that differ from what that feed
would have recorded on 2 to 8 percent of prices and on anywhere from 8 to 52 percent of
volumes. `ROLL_AUDIT.md` 2.7 reached the same conclusion from the other direction: prices
mostly match, volumes do not.

**The house tooling already refuses to cross that line on purpose.**
`tools/backfill_1m_from_10s.py` writes only into a `nt_noadj_<session>` master and says so in
its own words - same feed in, same feed out, never into the `db_noadj_*` series, no source
mixing inside one file. Mixing feeds inside a master is exactly what made the June 2026
Databento-to-Yahoo hand-off hard to reason about.

It also **cannot be pointed at ES today**: it requires an existing `nt_noadj_eth` 1-minute
master for the instrument, and there is none for ES. No raw ES 1-minute NinjaTrader export
exists locally to seed one either - `C:\EdgeLog\ohlc` has ES only at 10 seconds.

## What this means

1. **NQ could be filled to about 94% of the RTH hole and effectively all of the ETH hole
   from `master_b3bf23b6.csv` today**, at the cost of mixing feeds inside a `db_noadj_*`
   master.
2. **ES could reach a similar level only after seeding an ES 1-minute capture master**, which
   is new work, and at the same cost.
3. **A Databento re-pull fills both holes exactly and fixes the two in-bar splices at the
   same time** (`ROLL_AUDIT.md` 6.3 wants it anyway, to replace the estimated +293 / +64 /
   +295 / +68 offsets with measured ones). One purchase settles four problems.

So the recommendation is to **price a Databento pull for 2026-06-01..2026-09-30 before
filling anything from the capture.** A capture fill is available as a fallback and is clearly
better than a hole, but it trades a known absence for an unknown 2-8% price disagreement
spread invisibly across five weeks, inside masters that 254 saved runs read.

## Owner calls

1. **Re-pull Databento for 2026-06..09?** This is the clean fix for the holes and the
   splices together. Needs a purchase decision.
2. **Failing that, fill from the NT capture anyway?** If yes, decide whether it goes into the
   `db_noadj_*` masters (mixing feeds, which the tooling currently forbids) or into separate
   `nt_noadj_*` masters that strategies would have to be pointed at deliberately.
3. **Either way, which saved runs get restated?** `ROLL_AUDIT.md` names #295 (ES 1m 24h to
   2026-08-24), #345 and #360 (NQ 1m RTH to 2026-08-12) as the runs crossing the July hole.
   That list is self-consistent across five places in the document but was not independently
   re-derived here - the run history is in Firestore, not the local sqlite `runs` table, which
   stops at id 125 and date_to 2026-06-30.
4. **The 2026-07-24 capture outage and the NQ 06-30..07-16 rows of unknown origin** stay
   unexplained. Neither blocks a Databento pull, which would supersede both.
