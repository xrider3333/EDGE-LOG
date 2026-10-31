# item 30 - NQ data: stop Yahoo overwriting NT prices

- **status:** done
- **who:** Data chat + NT8 chat
- **date:** 2026-10-16
- **status text:** BOTH FIXES LIVE 8:59 PM

## What was decided / done
Found: the every-4-hours refresh rewrote the last 7 days with Yahoo prices (up to 2 pts off) and wiped NT repairs. Done 10-15: that refresh is off; NT prices for 10-05..10-14 restored twice. 10-16: the trading box carried Yahoo prices for 10-14 and 10-15 until 5:59 pm ET, when NT prices were re-spliced and re-pushed; KEEL rebuilt on the corrected data. 7:15 pm: fix 1 landed (Yahoo may only ADD new bars; every row carries its source and repair history), runner restarted. 8:59 pm: fix 2 landed (a NinjaTrader bar is never overwritten by Yahoo; the daily NT splice tool with repair of stub bars). 9:20 pm: one last refresh ran on the old code minutes before fix 2 landed and pushed three NQ files on the PC back to Yahoo for 10-14/15 (the trading box was not touched); the re-splice is running and the guard holds from here. Left: the weekday NT splice task (data chat registers it) and the 2012-14 / 2026 holiday session fills.

## History
- 2026-10-30: recorded from the board as [done] (row date 2026-10-16)
- 2026-10-30: board changed to [done] BOTH FIXES LIVE 8:59 PM
