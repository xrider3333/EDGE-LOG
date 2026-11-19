# Webull LIVE sizing + loss rails (2026-11-19)

Code: `api/qqq_exec.py` (`DEFAULT_CONFIG["live"]`, `_live_*`, `_daily_loss_limit`), `api/webull_orders.py`
(`get_stock_account_balance` now returns `buying_power`; raw reply keys logged once per process).
LIVE mode only. PAPER sizing (10 x plugin tilt x KEEL, cap 60) and the $ rails are unchanged.

## Config (owner defaults, all overridable in config.json `live`)

| key | default |
|---|---|
| `live.tiers` | `3000`: NOISE 1/3, ORB 2/6 - `5000`: NOISE 2/6, ORB 3/9 - `8000`: NOISE 3/9, ORB 5/15 (base/max) |
| `live.base_shares`, `live.max_shares` | `{}` - per-leg override of the tier |
| `live.max_open_notional_pct_equity` | 1.5 (multiple of equity; all open non-DIP lots + the order) |
| `live.daily_loss_pct` | 2.0 (pct of session-start equity) |
| `live.weekly_loss_pct` | 5.0 (pct of session-start equity, LIVE broker rows only) |

Tier = highest floor <= session-start equity (`first_net_liq_today`); below $3k or unread = lowest tier.
A leg in no tier (ENGUQ) gets 1/3. ORB max is not in the brief: 3x base chosen.

## Rounding rule

live shares = round HALF UP (live base x size), at least 1 share for any open the book takes, then
clipped to the leg's live max. 1 x 1.5 = 2, 1 x 1.4 = 1, 1 x 0.2 = 1, 3 x 4 = 12 -> 9.

## Refusals (REFUSED row in orders.csv, `live_cap` event, one `_say` push per leg per day)

- open notional (held + order) > 1.5 x equity
- order notional > last-read buying power
- equity not read yet

## PAPER replay at the live tiers

Box `trades.csv` read-only, 139 NOISE/ORB paper trades 2026-09-03..2026-11-19 (1 nan-pnl row
dropped; DIP / ENGUQ not live legs, left out). Per-share P&L of each paper trade x the live share
count; equity held flat at the tier (no compounding); buying power not in the history (not modelled).

| equity | shares sent (leg+shares: trades) | total P&L | worst day | worst week | notional refusals |
|---|---|---|---|---|---|
| $3,000 | NOISE1:73 NOISE2:37 NOISE3:3 ORB2:26 | +$103 (+3.4%) | -$19 (-0.6%) | -$23 (-0.8%) | 0 |
| $5,000 | NOISE2:73 NOISE3:24 NOISE4:13 NOISE6:3 ORB3:26 | +$187 (+3.7%) | -$32 (-0.6%) | -$39 (-0.8%) | 0 |
| $8,000 | NOISE3:73 NOISE5:24 NOISE6:13 NOISE9:3 ORB5:26 | +$290 (+3.6%) | -$51 (-0.6%) | -$62 (-0.8%) | 0 |

Worst day/week sit well inside the 2 pct / 5 pct rails; the 1.5x cap never bound (max two
QQQ lots of <= 9 shares open together).
