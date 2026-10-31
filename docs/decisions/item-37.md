# item 37 - Paper NOISE short left open when NinjaTrader died

- **status:** done
- **who:** NT8 chat
- **date:** 2026-10-16
- **status text:** FLAT 1:31 PM; GUARD LIVE

## What was decided / done
NinjaTrader died 11:56 with the demo NOISE short (11 MNQ) still open, protected only by the broker stop. Your call ('flatten at the close, as backtested'): NT brought back 1:26 pm, position and stop confirmed, flattened 1:31 pm at 29,390 for +$324.50 gross; no orders left; live account untouched. Fixed 9:55 pm: the night-mode switch now refuses to call the account flat unless the paper account is actually connected and shows no position, so it can never again close NinjaTrader over an unseen trade. Paper legs end every day flat as backtested.

## History
- 2026-10-30: recorded from the board as [done] (row date 2026-10-16)
- 2026-10-30: board changed to [done] FLAT 1:31 PM; GUARD LIVE
