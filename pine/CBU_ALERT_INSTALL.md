# EDGELOG CBU Alert - install (TradingView)

This adds your CBU setup to a TradingView chart as an alert. It fires when a 1-minute candle closes at a fresh high of the day with your conditions met. The rule is the final CBU alert in `SETUPS_PREREG_R3_CBU_V1.md` section 11, with your answers of 2026-10-02 applied. It is an alert, not an auto-trader.

## Which chart

Use two charts: a **1-minute NQ1!** and a **1-minute ES1!**. The alert was measured on NQ and ES volume; MNQ1! and MES1! show the same prices, but their volume differs a little.

- Extended hours must be **ON** (the 24-hour session). The EMAs and the premarket high need it.
- Back-adjustment must be **ON** (the **B-ADJ** button at the bottom of the chart).

## Install (3 steps)

1. On the 1-minute NQ1! chart:
   - Open the **Pine Editor**, choose **Open > New indicator**, delete the template text, and paste the whole of `CBU_ALERT_1_0.pine`.
   - Click **Save** (name it `EDGELOG CBU Alert`), then **Add to chart**.
   - Add it to the ES1! chart as well (Indicators > My scripts).
2. Leave the settings at their defaults: range 1.2, body 0.7, volume 1.5, window 0930-1544. **Use 10-second data** is off by default, so the label's score reads out of 8. If your plan has seconds charts, tick it to get the full 9-point score that EDGE LOG records. The alert rule never uses it.
3. On each chart:
   - Click **Create Alert** and set Condition to `EDGELOG CBU Alert`.
   - Choose **Any alert() function call** and **Once per bar close**. Set up only this one alert per chart; adding the plain "CBU long" condition as well would alert you twice.
   - Turn on the phone and desktop notifications.
   - The message reads: market, time, close, point score, stop, the +1R breakeven level, "then ride".

## What you will see

- **A label above each alert candle:** `CBU 7/9`, a stop one tick under the candle's low, the breakeven level at +1R measured from the close, and "then ride".
- **A table at the bottom right, for the last closed candle:** a tick or a cross for each condition, with the candle's range, body and volume against their minimums. The last line shows how many 5- and 30-minute bars are loaded.
- **Warming up:** the alert cannot fire until both EMAs have 600 bars. For the 30-minute one that is about 13 trading days of history.
- **How often:** expect about 3 alerts a day across the two charts. Usually it is 1; on a strong trend day it can be 9 or more.
- **Once per run:** back-to-back qualifying candles alert once.

## Checking it against EDGE LOG

`python tools/cbu_v1_alerts.py` replays the same rule on EDGE LOG's bars. Any alert you get, or one you think it missed, can be checked candle by candle. Add any CBU you see and do not take to **SHOULD HAVE TRADED**: each one becomes a new test of the alert. The holiday list inside the script must be extended each December, together with the point score's.
