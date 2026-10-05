# What a new leg must earn to lift BOOK #463 (MDL r1, 2026-10-04)

A planning map, not a test. We added 224,000 made-up legs to #463's real daily results and counted how often each kind lifted the book past the bars every lane is judged on: walk-forward 98.5 %/yr at a $30k drawdown with Sortino 3.82, and the sealed year 155.5 with Sortino 4.15. "Half the time" below means at least half of those made-up legs got there. The legs were given fat-tailed losses and volatility that rises when the book's does, and trade 100 to 250 times a year; the figures below pool those versions (each version's own thresholds are in MAP.txt and thresholds.csv).

**The dollars sentence.** A new leg must earn about **$15,000 a year at a $30,000 worst drawdown of its own**, and stay unconnected to #463 in the weeks #463 is falling, to lift the walk-forward past the bar half the time. Four times in five takes about **$30,000 a year**. To also clear the sealed year's bar half the time it needs **$20,000 to $30,000 a year**. A leg that tends to fall with the book in those weeks needs **$20,000 to $30,000** for the walk-forward and **$30,000 to $40,000** for both. One that falls hard with it needs about **$40,000** for the walk-forward and **$60,000 to $80,000** for both. A leg that earns while the book falls helps at almost any positive return: under $5,000 a year.

**What no leg can do.** A leg that falls hard with the book in its drawdown weeks does not clear both stretches four times in five even at $80,000+ a year at a $30k drawdown of its own; it gets there about two times in three. That prunes "more of the same": another NQ/ES momentum leg falls in the same weeks the book does. A leg with little edge of its own (under $5,000 a year at a $30k drawdown) almost never lifts the book unless it earns while the book falls. A leg trading only 25 times a year cannot be adopted whatever it earns, because it cannot reach the 50 sealed-year trades every final check needs.

**The first-order rule, in dollars.**
- **Walk-forward:** #463's worst drawdown was 2 to 27 March 2020: $44,849, against $140,235 a year. A leg helps only if it earns more than **$3,127 a year for every $1,000 it lost in those weeks**.
- **Sealed year:** the worst drawdown was 18 to 26 June 2026: $49,855, against $258,472 a year. A leg needs **$5,185 a year per $1,000 lost** in that window.

**Re-sizing: the yardstick a tilt has to beat.**
- **ORB, ENGU-Q and TTM:** simply trading a quarter more of any of them lowers the walk-forward return. TTM helps the sealed year but not the walk-forward.
- **NOISE:** it is the only leg whose plain upsizing lifts both stretches.
  - A quarter more gives 99.8 / Sortino 3.97 walk-forward and 156.3 / 4.24 sealed.
  - Double gives 116.4 and 158.2.
- **What this means for tilts:** a NOISE tilt must beat plain extra NOISE. A tilt on the other three starts from a baseline that falls.
- **Caution:** re-weighting has shown no forward skill before (book round 56), so this is a yardstick, not a recommendation.

**Where today's candidates sit, at their real size.**
- **ORB #239 in the ORB seat** lifts both stretches: 101.8 / 158.7, the same as the ORB lane's own figures. It is the only shadow that clears both bars.
- **ORB #257 in the ORB seat** lifts the walk-forward (108.5) but loses the sealed year (146.3).
- **The ENGU-Q cash-session gate** (S1, S2) gives a worse walk-forward (82.7, 81.3) and a better sealed year (186.7, 168.1).
- **DIP on NQ #433** gives a worse walk-forward (69.3) and a better sealed year (164.5).
- **DIP on ES #452** is worse in both (51.8, 141.1). DIP loses in the same weeks the book does (2020).
- **NQBRD 0.70** (dead) gives a worse walk-forward (73.2); its sealed year stays sealed.
- **#463's own legs:** taking any one out lowers the sealed year. On the walk-forward:
  - NOISE and ENGU-Q carry the return.
  - ORB and TTM each cost a little return but buy their seats with a higher Sortino.

**Seat test for the forward shadows.** When a shadow reaches 50 closed trades, the paper lanes post it and this lane runs the read:
- the shadow added to #463 in both backtest stretches;
- whether it earned or lost while the forward book was falling (unreadable until the forward book has fallen at least $14,950).

A seat is an owner question, never automatic.

**Limits.** #463 has one realised history, so the map is a necessary condition, not a sufficient one. The sealed year is one year, so its half of the map is mostly noise.

Files: `tools/rocfrontier/PREREG_MDL_R1.txt` (with pre-data addendum 1), `r12_mdl.py`, `r12_refs.py`. Results in `C:\EdgeLog\_anatomy_cache\rocfrontier\mdl_r1` (MAP.txt, thresholds.csv, resizing.json, refs.json, leave_one_out.json).

**New-type candidates placed on this map (MANAGER #40, 2026-10-05).** Each states its row and its power line before any real-direction number.
- **HALFHOUR r1** (NOISE lane; `docs/PREREG_halfhour_r1_2026-10-05.md`): same-half-hour seasonality on NQ, long and short every day. Row: uncorrelated (about $15k a year at a $30k own drawdown). Power line on the book add: minimum detectable lead 12.9 points, 19.5 for four times in five, so a pass needs a leg nearer $25-30k a year.
- **ROUND r1** (NOISE lane; `docs/PREREG_round_r1_2026-10-05.md`): stop cascades when NQ closes across a multiple of 100 (Osler 2003/2005), null = the same grid moved off the round numbers. Row: uncorrelated, possibly mild on trend days. Power line: minimum detectable lead 10.3 points, 15.6 for four times in five.
