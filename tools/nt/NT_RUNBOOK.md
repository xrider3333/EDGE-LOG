# NinjaTrader 8 — unattended ops runbook

The one page for "NinjaTrader is down / stuck / needs a restart" — written because this
knowledge kept living in chat sessions and getting lost. **Claude can do ALL of this
without the owner present.** The owner should never need to be asked to log in, connect
the sim, or re-enable the roster.

## The one command

```
powershell -ExecutionPolicy Bypass -File C:\EdgeLog\nt_recover.ps1
```

Safe to run any time (add `-WhatIf` to preview). It only goes as far as it needs to:

1. Bridge answers + expected strategies Realtime → exits, touches nothing.
2. NinjaTrader down or at the login window → runs `C:\EdgeLog\nt_login.ps1`:
   - reads the password from **Windows Credential Manager** (target `EdgeLog_NT8`,
     written once by the owner — the password never appears in any script, log, or chat),
   - fills the Welcome screen, clicks through to the live/sim selector,
   - **always picks "Start Trading" (Live)** — that is the owner's normal flow; the
     safety against touching the real account is NOT this choice, it is the bridge's
     compiled L1 hard-lock on account 1810769 + L2 allowlist (DEMO7240108/Sim101).
3. Dials the **Simulation** connection — the one that owns DEMO7240108. ("Live"
   being connected does NOT mean the demo account is: each account belongs to one
   connection, and enabling a strategy on a disconnected account raises a MODAL
   assertion that freezes the whole platform until a human clicks Ignore.)
4. Re-enables every roster strategy not already Realtime (`$expected` in nt_recover.ps1).
5. Prints a REAL vs SIM readout; exits non-zero if the end state is still wrong.

## Guards that make enabling safe (bridge ≥ 2026-08-17, v73.99+)

- `GET /strategy/check?name=X` — pre-flights every parameter against its `[Range]`;
  NinjaTrader enforces ranges at STARTUP, so an out-of-range value silently finalizes
  the strategy with only a popup (no trace-file or Log-tab entry — the ENGU-Q lesson).
- `POST /strategy/enable` refuses if the account's connection is not `Connected`
  (prevents the freeze-everything assertion) or any param is out of range.
- `GET /dialogs` — reads open popup text across BOTH UI threads, so a modal error can
  be read remotely instead of screenshotted.
- `GET /accounts` — per-account `connection` / `connected` fields; cash is NOT a
  usable connected-proxy (a connected demo can read 0 before sync).
- **Framework settings are writable too** (v73.101): `/strategy/params` returns a
  `base_settings` list — StartBehavior, Calculate, IsExitOnSessionCloseStrategy,
  ExitOnSessionCloseSeconds, BarsRequiredToTrade — and `/strategy/setparam` accepts
  them by name (disable → set → enable, same as any knob; enums list their options).
  First use 2026-08-17: ENGU-Q was on **ImmediatelySubmit**, which places REAL
  protective orders for its warm-up replay position (the EQx stop that re-armed after
  every cancel — never fight that loop, flip the mode). `StartBehavior=WaitUntilFlat`
  ended it; verified by re-enable with an empty /orders next to a virtual Long 1.

## Compiling NinjaScript — the safe way

NinjaTrader rescans `bin\Custom` at startup and **adopts any .cs it finds into its own
.csproj** — including generated satellite-resource sources under `obj\` that a plain
headless `dotnet build` leaves behind. Those carry duplicate assembly attributes and
break BOTH builds with CS0579 (happened 2026-08-17). So:

- Always build with intermediates OUT of the tree:
  `dotnet build NinjaTrader.Custom.csproj -p:BaseIntermediateOutputPath=<scratch>\ntobj\`
- If CS0579 appears: delete `<Compile Include="obj\...">` lines from the csproj and
  move any `obj\**\*.cs` / `bin\**\*.cs` out of the tree, then recompile (F5) in NT.
- A headless build hot-reloads ADDONS (bridge restarts, logged in `C:\EdgeLog\bridge.log`)
  but NOT already-instantiated strategies — they keep the old type until NT restarts.

## Known strategy quirks

- **EdgeLogENGUQ1m**: ETH config (#226) = TlLen 170 / EmaLen 1380 / AtrLen 106 on the
  24h session template; ranges widened v73.99 to fit. Warm-up replay can leave a REAL
  working stop order (`EQx`) guarding a position that only exists in its replay —
  check `/orders` after enable and cancel the orphan.
- **EdgeLogORBV2**: deliberately OUT of the recover roster since 2026-08-16 — it runs
  retired look-ahead-era params while the engine crown moved to run #230. Its fills
  measure a dead config. `EdgeLogORB230.cs` is the honest port (compiled, in the
  csproj); it needs a grid/chart row added in the NT UI once, then the bridge can
  manage it. Re-add to the roster only after its fills reconcile against the engine.

## Running while nobody is signed in (2026-08-19)

**NinjaTrader cannot run without a Windows session.** It is a desktop app; with nobody
signed in there is no desktop to run on. Everything in this stack inherits that:

- `StartNinjaTrader.vbs`, `EdgeLogGate.vbs`, `EdgeLogRunner.vbs` all live in the Startup
  folder, which runs **at interactive logon only**.
- The recover watchdog task is registered `LogonType = Interactive` -- "run only when the
  user is logged on". Setting it to "whether logged on or not" does NOT help: that runs in
  session 0 with no desktop, so NinjaTrader would launch invisibly and the UI-automation
  login would have no window to drive.

So the machine was ON but signed OUT on 2026-08-19 and nothing ran until the owner logged
in, ~1h40m into the session. The fix is to remove the human from the boot path:

1. **Windows auto-logon** (owner does this -- it needs the Windows password, which Claude
   never handles): run `netplwiz`, uncheck "Users must enter a user name and password to
   use this computer", enter the password once. The machine then boots straight into the
   session and every Startup item runs.
2. **Auto-lock after that logon** so an unattended boot does not leave an open desktop:
   copy `C:\EdgeLog\lock_after_logon.vbs` into the Startup folder. The session stays
   alive (strategies keep running); the screen requires the password.
3. **Stop the machine sleeping.** Idle sleep was 180 min on AC, which would kill the
   overnight ETH session: `powercfg /change standby-timeout-ac 0`.

**LOCK, never SIGN OUT.** Locking (Win+L) keeps the session and everything in it alive.
Signing out destroys the session and kills NinjaTrader, the gate and the runner -- and
auto-logon only applies at BOOT, so it will not bring them back. Shutting down is fine;
the next boot logs itself in.

## Powering the PC off overnight (2026-08-19)

The owner shuts the machine down at night. That is workable, because the SHADOW layer
already backfills every leg: `api/paper.py` re-runs each config nightly on the 24-hour
1-minute master, which carries full overnight bars (verified 2026-08-19: continuous
coverage every ET hour except the 17:00 maintenance break, source=yahoo, current to the
minute). So the performance RECORD stays complete whether the PC was on or not.

What the backfill does NOT replace:

- **Fill realism.** Slippage, rejections and latency only exist on the live NinjaTrader
  leg, so those are measured on DAYTIME trades only. The reconcile already scores
  slippage on matched pairs only, so this degrades coverage, not correctness.
- **An open position.** A real demo position left on the broker at shutdown keeps its
  resting stop but nothing trails it or takes its exit, and next morning `nt_recover`
  (correctly) refuses to enable into that mismatch. NOISE and ORB230 flatten at the
  session close so they are never exposed; ENGU-Q holds across sessions by design --
  6 of its last 11 trades were still open at the hour the PC goes off.

So before powering down:

```
powershell -ExecutionPolicy Bypass -File C:\EdgeLog
t_eod_safe.ps1
```

It flattens the demo account if anything is open, stops the three strategies, verifies no
working orders remain, and refuses to say "safe" if any of that fails. `-WhatIf` previews.

ONE DEPENDENCY WORTH KNOWING: the 1-minute master is topped up from Yahoo, which only
serves ~7 days of intraday history. If the machine stays off for more than a week the gap
becomes permanent (that is exactly how the 2026-07-01..08-05 hole happened). Running the
PC on weekdays is enough; a two-week holiday with it switched off is not.
