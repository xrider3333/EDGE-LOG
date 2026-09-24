# PRE-REGISTRATION — NOISE on mega-cap earnings reaction sessions (NOISE round 60, 2026-09-24)

Written and committed BEFORE any NOISE trade was tagged with this calendar. Nothing below may be changed
after the first result is read; anything learned afterwards goes in a clearly marked POST-HOC section.

## Why this test
The KEEL study (2026-09-09) found that ~175 feature and calendar candidates built from information NOISE
already had produced nothing, and that the first genuinely NEW input (the Fed's own FOMC calendar) passed on
the first try. It named the next new inputs: the BLS release calendar (done 2026-09-09, a no for RTH), the
earnings calendar, and order flow. Ten calendars already tested (FOMC, CPI, payrolls, FOMC minutes, quad
witching, month and quarter starts and ends) do not include earnings. This is the earnings calendar.

## The calendar (fixed before any outcome was read)
`tools/data/megacap_earnings.csv`, built by `tools/fetch_megacap_earnings.py` from the SEC's filing index:
every Form 8-K with Item 2.02 (results of operations) for Apple, Microsoft, NVIDIA, Amazon, Alphabet (Google
Inc before 2015), Meta and Tesla since 2010 — 461 releases after removing Tesla's quarterly delivery reports
(which use the same item). The list of seven companies was fixed before any data was read.

**Reaction session** = the first NQ regular session that starts after the filing's acceptance time: accepted
at or after 16:00 ET (or on a non-session day) → the next session; before 09:30 ET → that day's session;
between 09:30 and 16:00 → that same session.

## The tag
A NOISE trade is TAGGED when its SIGNAL bar (the bar before the fill) lies in a reaction session. The tag is a
calendar date, so it cannot read the trade's own outcome ([[tag at the signal bar]] is satisfied by
construction; re-tagging one bar earlier cannot change a whole-session date tag except at 09:30 fills, and the
signal bar of a 09:30 fill is the prior session's last bar — handled by using the signal bar's date).

## Bases and stretches
- PRIMARY: the live NOISE crown, run #304's champion (lookback 40, bands 0.75 / 1.5, stop 1.75 bandwidths,
  volatility skip 95, skip weak-close shorts), NQ 5-minute RTH, no-adjust Databento master, cost 0.533,
  2010-06-07 to 2026-09-16 (the last Databento bar; the few Yahoo-appended sessions after it are excluded).
- REPLICATION: the retired crown #243 (lookback 44, volatility skip 90), same everything else.
- Stretches = run #304's own validate windows: IS before 2016-05-02; WF 2016-05-02 to 2025-02-11; LB from
  2025-02-11 (which now includes the sessions after run #304's window ended, unseen by any validate).

## Hypothesis H1 (the only adoptable one)
NOISE is an intraday noise-boundary BREAKOUT. A mega-cap earnings reaction session carries fresh index-level
information, so moves that break the noise boundary should persist more often. **H1: tagged trades earn MORE
per trade, and sizing them 1.5x (the house multiplier, never tuned) improves the crown.**

## The bar (all of it, on BOTH bases)
`tools/tilt_guard.guard(..., mult=1.5)` returns passed=True on the primary AND the replication base, which
means: better net in every stretch with drawdown not materially worse (MONEY); beats the exposure-matched
uniform control on MAR (C1); the real calendar beats random day-sets of the same size (C2) AND random
sessions drawn from the SAME earnings seasons (C3 — subgroup = every session in a calendar week that contains
at least one reaction session, because earnings cluster in late Jan / Apr / Jul / Oct and the season itself
might be what differs); no single trade is most of any stretch's gain (C4); and the PLACEBO — the session
BEFORE each reaction session — does not pay the same way (C5). Under-powered stretches (under 25 tagged
trades) are reported as such, not passed.

## What happens to a NO
- If the bucket is instead NEGATIVE in all three stretches on both bases, a 0.5x shrink is run through the
  same battery and reported as POST-HOC (the direction was not pre-registered). Like the BLS round, a
  post-hoc pass is a forward-test idea at most, never an adoption.
- Per-company and multi-release-day splits are DESCRIPTIVE only; none of them can be adopted from this
  round — picking the best company after the fact is exactly the selection the permutation cannot price.

## Not changed by this round
Nothing live moves. The Webull NOISE leg and every paper leg are untouched whatever the result.
