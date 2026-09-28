# Round 4 ideas - new families that could beat BOOK #463 at matched drawdown (2026-09-28)

Owner ask via MANAGER (inbox #6). Read first: MEMORY "Dead hunts", RESEARCH_LEDGER 2.1-2.30, rounds 13-19, 24-25,
32-42 (~350 dead cells: every intraday fade, the public classics, calendar/VIX, scalpers, session-range breaks,
pairs, ML direction models, overnight drift). The bar: BOOK #463 = 60.34 %/yr at a $30k drawdown before the
lockbox, 164.76 in it; a new leg helps only if it earns when the book does not (Sharpe ~1 at low correlation).

| # | Idea (mechanism) | Data | Expected effect on #463 at $30k DD | Cost | How it could fool us | Status |
|---|---|---|---|---|---|---|
| 1 | **Weekend gap on the Sunday reopen** - weekend news priced in thin Sunday liquidity, finished by Europe/US | NQ/ES 5m ETH, have | +0-5% if real | minutes | a few crash weekends; roll weekends | **RAN - dead** (0/18; best t 1.85 vs null 2.71; ROC@30k <= 8.6) |
| 2 | **FOMC-cycle even weeks** (Cieslak-Morse-Vissing-Jorgensen 2019) - Fed news clusters in even weeks | RTH closes + Fed calendar, have | +0-5% | minutes | beta in disguise; post-publication decay | **RAN - dead**: even weeks won 2010-16, ODD weeks won 2016-25 (NQ $197k vs $118k) |
| 3 | **Mega-cap earnings nights** - NQ prices 7 reports 16:00-17:00; hold the reaction overnight | NQ/ES 5m ETH + SEC calendar, have | +0-5% | minutes | 20 events a year; one big night | **RAN - dead**: continuation loses (NQ -$26k..-$52k WF); fade PF ~1.2, t <= 1.1 (post-hoc only) |
| 4 | Overnight reversal: long close -> next open after a DOWN RTH session | NQ/ES, have | +2-5% | minutes | its pre-lockbox number was already seen (ledger 2.13, $90/trade 8 of 12 years) - only the lockbox would be clean | not run (tainted read) |
| 5 | **Stocks-in-play ORB** (Zarattini, Barbon & Aziz 2024) - 5-min ORB on the ~20 US stocks with the highest relative volume each day | Alpaca SIP 1m/5m since 2016 (free Basic plan) - **owner key needed** | potentially large and near-zero correlation (stock-specific news) - a stocks-account leg | ~1 day data pull, minutes to triage | survivorship (needs delisted names), small-cap slippage, the paper's Sharpe is in-sample | needs the owner's Alpaca key |
| 6 | Breadth thrust on NQ - share of Nasdaq-100 stocks above their open at 10:00 ET as the trend-day trigger | Alpaca constituents | 0-5% | ~1 day | overlaps NOISE's trend days; constituent list changes | needs Alpaca key |
| 7 | Transfer of ORB / NOISE / TTM to ZN, 6E, CL, GC | Databento | the only data-level diversifier | pre-registered (TRANSFER r1) | see PREREG_TRANSFER_R1.txt | waits for the owner's Databento key |
| 8 | Same-slot intraday seasonality (Heston-Korajczyk-Sadka 2010) - flows repeat at the same half hour | NQ/ES, have | ~0 after costs | minutes | 26 slots x lookbacks = multiple testing | not run (expected cost-dead) |
| 9 | TTM squeeze on the 24-hour ES tape | ES 30m ETH, have | 0-3% | a validate | overnight breakouts were weak (Asia/London PF 1.11) | TTM lane's family - routed, not run |
| 10 | ES / NQ calendar-spread roll pressure (market-neutral) | Databento spreads to 2026-06, have | tiny $, near-zero correlation | a scan | 8 rolls a year - cannot meet 100 walk-forward trades | parked |

Pre-registrations: `PREREG_WKND_FOMCWK_R1.txt` (sha256 c0b92c9d...1921), `PREREG_EARN_R1.txt` (2e3148a8...decf).
Harnesses: `r4_book463.py` (BOOK #463 daily legs, reproduces 60.34 / 164.76 exactly), `r4_triage.py`, `r4b_earn.py`.
Results (outside git): `C:\EdgeLog\_anatomy_cache\rocfrontier\r4\`. No lockbox read; nothing reached a runner job.
