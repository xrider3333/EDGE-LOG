# item 56 - Webull NOISE: is its volatility filter running on too little history?

- **status:** done
- **who:** Webull chat
- **date:** 2026-10-25
- **status text:** DONE - LIVE ON THE BOX 20:05: alert when NOISE's history top-up fails; a missing QQQ daily file = ONE pre-open phone note (no trade changed, replay identical)

## What was decided / done
Checked 10-20: no NOISE signal or size has ever been changed. The 252 sessions feed only the volatility skip, and a daily-bar bridge tops the box's 94 five-minute sessions up to the full 252 every day since the code went live (09-28). All 20 boots 09-27..10-21 match a full-history replay; 23 trades identical on side, times, tilt and KEEL. The one risk: if that bridge ever fails, the filter silently falls back to the short window (about 1 day in 28 would flip) and nothing watches for it. Being added: a phone push and a monitor finding whenever the window runs short.

## History
- 2026-10-30: recorded from the board as [done] (row date 2026-10-25)
