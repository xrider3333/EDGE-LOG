# item 39 - Evening-session tests read a few hours past their cutoff

- **status:** done
- **who:** Data chat (TBIS); ENGU-Q confirms after
- **date:** 2026-10-17
- **status text:** LIVE 11:00 AM SAT; RUNNER RESTARTED 11:24

## What was decided / done
Found 10-16 (data chat, checked by a second reviewer): on the 23-hour NQ data the engine kept the Sunday evening that opens the sealed year inside every tuning window, so 27 stored tests (26 ENGU-Q, 1 CBU-Q) saw one sealed-year session they should not have. For ENGU-Q #335 (your Webull tracker leg and the book's ENGU-Q seat) that evening added about $2,660 of move to its tuning total, out of nine years. Fix built and reviewed: windows now end at the session roll; sealed-year labels unchanged. Ships tonight after the two NQ data fixes. Then #335 is checked two ways: its frozen settings re-scored on the corrected cut (before vs after, four numbers), and all 527 stored candidate settings re-scored to see whether the winner changes; a full 900-trial re-run only if it does. Nothing on Webull paper changes meanwhile. First check done 6:33 pm: with its frozen settings, #335 goes from 18.62 to 18.51 ROC/yr on the test years, same trades and same drawdown; only the last open trade's end mark moved. Second check done 6:40 pm: every candidate setting loses the same 133 points of that one evening, so the ranking is identical and #335's settings stand. The leak was real but changed nothing; the fix still ships tonight so it cannot recur. The update died in the lock queue at 11:40 pm with the sign-out; re-queued 9:12 am Saturday. After it lands: runner restart, then the Super Scalper 900-trial validate starts.

## History
- 2026-10-30: recorded from the board as [done] (row date 2026-10-17)
- 2026-10-30: board changed to [done] LIVE 11:00 AM SAT; RUNNER RESTARTED 11:24
