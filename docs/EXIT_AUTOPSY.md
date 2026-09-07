# EXIT AUTOPSY

Per crowned strategy leg: how far trades went in favour (MFE) and against (MAE)
while open, how much of the favourable move winners actually kept, and how often
losers were first up a meaningful amount. R = the leg's own average losing trade
in dollars, pre-lockbox — the same denominator the board's EV R uses.

**Exit is a lever on:** none of the six
**Exit is not the lever on:** ORB #314 (crown), ORB #234 (crown, pinned card), NOISE #243 (crown, paper leg), NOISE #316, ENGU-Q #309 (crown), NQDIP #307

## ORB #314 (crown)
- NQ 5m rth, window 2010-06-07..2026-08-13, lockbox from 2025-08-13. side from tuple. parity OK.
- R unit (avg losing trade, pre-lockbox) = $771
- Pre-lockbox (n=2131): winners capture 71% of MFE (p25 48%), losers reach 0.5R 40% of the time and 1R 24% of the time.
- Give-back (a perfect-exit ceiling, NOT achievable): 0.62R median, ~$136,182/yr pre-lockbox.
- Lockbox (n=168, small sample): winners capture 60%, losers reach 1R 65% of the time.
- Read: winners keep 71% of their best move and 24% of losers were ever up 1R, so the exit is not where the money is.

## ORB #234 (crown, pinned card)
- NQ 5m rth, window 2010-06-07..2026-06-30, lockbox from 2025-07-01. side from tuple. parity n/a (no doc to check against).
- R unit (avg losing trade, pre-lockbox) = $831
- Pre-lockbox (n=2411): winners capture 70% of MFE (p25 45%), losers reach 0.5R 33% of the time and 1R 19% of the time.
- Give-back (a perfect-exit ceiling, NOT achievable): 0.55R median, ~$151,339/yr pre-lockbox.
- Lockbox (n=173, small sample): winners capture 63%, losers reach 1R 55% of the time.
- Read: winners keep 70% of their best move and 19% of losers were ever up 1R, so the exit is not where the money is.

## NOISE #243 (crown, paper leg)
- NQ 5m rth, window 2010-06-07..2026-08-12, lockbox from 2025-02-12. side from tuple. parity OK.
- R unit (avg losing trade, pre-lockbox) = $296
- Pre-lockbox (n=4054): winners capture 53% of MFE (p25 27%), losers reach 0.5R 40% of the time and 1R 22% of the time.
- Give-back (a perfect-exit ceiling, NOT achievable): 0.86R median, ~$137,864/yr pre-lockbox.
- Lockbox (n=375, small sample): winners capture 50%, losers reach 1R 70% of the time.
- Read: winners keep 53% of their best move and 22% of losers were ever up 1R, so the exit is not where the money is.

## NOISE #316
- NQ 5m rth, window 2010-06-07..2026-08-12, lockbox from 2025-08-12. side from tuple. parity OK.
- R unit (avg losing trade, pre-lockbox) = $311
- Pre-lockbox (n=3556): winners capture 56% of MFE (p25 26%), losers reach 0.5R 38% of the time and 1R 21% of the time.
- Give-back (a perfect-exit ceiling, NOT achievable): 0.84R median, ~$121,690/yr pre-lockbox.
- Lockbox (n=228, small sample): winners capture 49%, losers reach 1R 75% of the time.
- Read: winners keep 56% of their best move and 21% of losers were ever up 1R, so the exit is not where the money is.

## ENGU-Q #309 (crown)
- NQ 1m eth, window 2010-06-07..2026-06-30, lockbox from 2025-06-30. side from tuple. parity OK.
- R unit (avg losing trade, pre-lockbox) = $766
- Pre-lockbox (n=1504): winners capture 45% of MFE (p25 23%), losers reach 0.5R 37% of the time and 1R 22% of the time.
- Give-back (a perfect-exit ceiling, NOT achievable): 1.12R median, ~$166,760/yr pre-lockbox.
- Lockbox (n=100, small sample): winners capture 46%, losers reach 1R 62% of the time.
- Read: winners keep 45% of their best move and 22% of losers were ever up 1R, so the exit is not where the money is.

## NQDIP #307
- NQ 5m rth, window 2010-06-07..2026-08-24, lockbox from 2025-08-24. side from tuple. parity OK.
- R unit (avg losing trade, pre-lockbox) = $2,396
- Pre-lockbox (n=847): winners capture 85% of MFE (p25 62%), losers reach 0.5R 28% of the time and 1R 8% of the time.
- Give-back (a perfect-exit ceiling, NOT achievable): 0.17R median, ~$68,462/yr pre-lockbox.
- Lockbox (n=60, small sample): winners capture 74%, losers reach 1R 6% of the time.
- Read: winners keep 85% of their best move and 8% of losers were ever up 1R, so the exit is not where the money is.
