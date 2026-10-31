# item 43 - Gate AI-written strategy code before it runs

- **status:** done
- **who:** MANAGER (built); Custom ML chat (lab side)
- **date:** 2026-10-17
- **status text:** LIVE ON MAIN SAT 2:10 PM

## What was decided / done
Your task 10-17. Until now the engine would load ANY file placed in the strategies folder, including files the local AI (Qwen Lab) wrote; the rule that a Claude chat must review such a file first lived only in the lab's own code. Built: a gate inside the engine's loader, the job runner's own file check and the engine's AI code validator. A file counts as AI-written when it sits in the qwen_lab folder, is named QL_..., or carries an AUGUR-SOURCE marker. It runs only if (1) the reviewing chat stamped it in a review ledger with the file's fingerprint (one command) and (2) its source passes a strict whitelist: numpy / pandas / math only, no disk, network or interpreter access, no hidden state. Anything else is refused before a single line of it executes; there is no override switch. Hand-written strategies are untouched. 39 new tests; the strategy-contract and lint suites pass. Update queued 9:45 am Saturday behind the six relaunched ones. Custom ML chat asked to point the lab's own review check at the same ledger.

## History
- 2026-10-30: recorded from the board as [done] (row date 2026-10-17)
- 2026-10-30: board changed to [done] LIVE ON MAIN SAT 2:10 PM
