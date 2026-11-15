# AUGUR-SOURCE: claude-review
"""MISC ESALONE 1.0 - the ENGU-Q R2 trend-resumption breakout run on ES 1m ETH, optionally only while NQ ENGU-Q is flat.

Provenance: OPUS-HUNT futures strategy 73 "ES-ALONE" (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S73:
PREREG.md, RESULTS.md, s73_run.py, trades_73*_eval.csv, series.pkl). DEFAULTS = CELL 73d EXACTLY: the UNGATED ES
twin, i.e. augur_strategies/ENGUQ_1M_ETH_R2_1_0.py at its own DEFAULT_PARAMS walked on ES 1m ETH db_adj_eth
(73d = 73a + 73c of the prereg). Cell 73d was report-only in its prereg; the hunt's verdict cell 73a (NQ-flat
shadow gate) FAILED (net t 1.28 / 1.26). NOT A BLIND READ for 2016-07..2025-06: the hunt measured it. The engine's
lockbox (2025-07-01..2026-06-30) is the first look at those bars for this rule.

-- The rule (identical to ENGUQ_1M_ETH_R2_1_0.py, transcribed; long only) ---------------
A bar i is a SIGNAL when, all at its close: close > open; close > EMA(ema_len); close > the trailing
regime_len x 390-bar simple average (regime_len 0 = off); volume >= vol_mult x its 20-bar average (0 = off);
the least-squares line through the highs of the tl_len bars BEFORE i slopes down; close clears that line by
buf_atr x ATR(atr_len) and clears the prior bar's high; (close - line) / max(ATR, 0.25) >= min_brk; the
efficiency ratio of the last er_len bars >= er_th (er_th 0 = off).
ENTRY: a resting limit at close - limit_atr x ATR, live for the next 10 bars; first bar whose low touches it
fills at min(limit, that bar's open) (gap-honest). No touch in 10 bars = no trade. limit_atr 0 = fill at the
signal close. risk = fill - lowest low of bars i-tl_len .. i; risk < 0.5 pt = no trade.
EXIT: stop at fill - stop_mult x risk; once the high reaches act_R x risk the stop trails trail_frac x risk under
the running high; once it reaches breakeven_R x risk the stop is at least the fill. Updates use the bar's own
high, then the stop is checked against the bar's low (stop-first); a bar that opens below the stop fills at the
open. Management starts the bar after the fill. One position at a time. No time cap (multi-day holds).
The last open trade closes at the final bar's close.

-- The NQ gate (nq_gate; 0 = off = cell 73d) -------------------------------------------
NQ FLAG: 1 on every NQ 1m bar from the fill bar to the exit bar (inclusive) of the SAME R2 file at its
DEFAULT_PARAMS walked on NQ 1m ETH db_adj_eth from 2010-06-07; mapped to an ES bar by as-of join on bar START
(the NQ bar with start <= the ES bar's start). The flag of an NQ bar is known at that bar's close, so the flag
read on ES bar k is known at ES bar k's close.
  nq_gate 1 = SHADOW (prereg cell 73a): the ES walk runs exactly as with the gate off; a trade is KEPT only if the
              flag at the close of the bar before its fill bar is 0. A dropped trade still holds the slot until
              its own exit (the hunt's definition).
  nq_gate 2 = RELAY (prereg cell 73b): a signal whose bar carries flag 1 is skipped and does not hold the slot.
The NQ trade intervals are PINNED inside this file (_NQ_PANEL, built by tools/esalone_nq_panel.py from the
masters on disk 2026-11-14, NQ bars with start < 2026-06-30 17:00 ET). ES bars at or after the panel end read
flag 1 (unknown -> no trade). With nq_gate 0 the panel is never read.

INFORMATION TIMES: every signal input is a completed bar <= i; swing low includes bar i; the limit is placed
at bar i's close and only bars after i can fill it; stops move on the bar's own high before its low is tested
(the parent's convention). The NQ flag on ES bar k uses NQ bars that started at or before k's start, i.e. NQ
bars completed by k's close.

-- Costs, units ---------------------------------------------------------------------------
PnL is ES points (db_adj, differences only). The job charges cost_pts 0.61 (the prereg's ES round trip) x mult 50.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC ESALONE 1.0 · ENGU-Q R2 breakout on ES 1m ETH (opus hunt 73d; NQ-flat gate as a knob)'
DESCRIPTION = ("The ENGU-Q R2 trend-resumption breakout (descending-trendline break, shallow limit entry, "
               "breakeven + trailing stop, multi-day holds) on ES 1m ETH. Defaults = hunt cell 73d (ungated ES twin). "
               "nq_gate 1 / 2 take ES trades only while the NQ ENGU-Q R2 leg is flat (pinned NQ panel).")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "ES", "timeframe": "1m", "session": "eth", "source": "db_adj_eth"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_R2_1_0.py"

DEFAULT_PARAMS = {
    "tl_len": {"hard_min": 20, "default": 206, "min": 150, "max": 262, "step": 8, "type": "int",
               "label": "Trendline Length (bars)",
               "tooltip": "Bars of highs (before the signal bar) the descending trendline is fit to."},
    "limit_atr": {"default": 0.55, "min": 0.35, "max": 0.75, "step": 0.05, "type": "float",
                  "label": "Shallow Limit Depth (x ATR)",
                  "tooltip": "Resting buy limit this many ATR under the signal close, live 10 bars."},
    "vol_mult": {"default": 1.1, "min": 0.7, "max": 1.5, "step": 0.1, "type": "float",
                 "label": "Volume Spike (x avg)",
                 "tooltip": "Signal-bar volume must reach its 20-bar average x this. 0 = off."},
    "stop_mult": {"default": 1.0, "min": 0.8, "max": 1.3, "step": 0.1, "type": "float",
                  "label": "Stop (x risk-to-swing-low)",
                  "tooltip": "Initial stop distance as a fraction of fill-to-swing-low."},
    "act_R": {"default": 1.5, "min": 1.0, "max": 2.5, "step": 0.5, "type": "float",
              "label": "Trail Activation (R)",
              "tooltip": "Start trailing once the high is this many R above the fill."},
    "trail_frac": {"default": 2.5, "min": 1.5, "max": 3.5, "step": 0.5, "type": "float",
                   "label": "Trail Width (x risk)",
                   "tooltip": "Trailing stop rides this many risk units under the running high."},
    "buf_atr": {"default": 0.3, "min": 0.1, "max": 0.5, "step": 0.1, "type": "float",
                "label": "Breakout Buffer (x ATR)",
                "tooltip": "Close must clear the trendline by this x ATR."},
    "min_brk": {"default": 1.6, "min": 1.2, "max": 2.0, "step": 0.1, "type": "float",
                "label": "Breakout Decisiveness (x ATR)",
                "tooltip": "(close - trendline) / ATR must reach this."},
    "ema_len": {"hard_min": 2, "default": 220, "min": 140, "max": 300, "step": 20, "type": "int",
                "label": "Trend EMA Length (bars)",
                "tooltip": "Only longs with close above this EMA."},
    "atr_len": {"hard_min": 2, "default": 52, "min": 36, "max": 68, "step": 4, "type": "int",
                "label": "ATR Length (bars)",
                "tooltip": "Simple average true range window (buffer, decisiveness, limit depth)."},
    "regime_len": {"default": 10, "min": 0, "max": 20, "step": 5, "type": "int",
                   "label": "Regime SMA (x 390 bars, 0=off)",
                   "tooltip": "Close must sit above its trailing regime_len x 390-bar average (the parent's unit)."},
    "breakeven_R": {"default": 2.0, "min": 1.5, "max": 2.5, "step": 0.5, "type": "float",
                    "label": "Breakeven (R)",
                    "tooltip": "Once the high is this many R above the fill, the stop rises to the fill."},
    "er_len": {"hard_min": 2, "default": 100, "min": 100, "max": 100, "step": 10, "type": "int",
               "label": "Efficiency Lookback (bars) - pinned",
               "tooltip": "Pinned: unused while the efficiency floor is 0 (the 73d cell)."},
    "er_th": {"default": 0.0, "min": 0.0, "max": 0.0, "step": 0.05, "type": "float",
              "label": "Efficiency Floor (0=off) - pinned",
              "tooltip": "Pinned at 0 = off, as in the 73d cell."},
    "nq_gate": {"default": 0, "min": 0, "max": 2, "step": 1, "type": "int",
                "label": "NQ gate (0 off / 1 shadow / 2 relay)",
                "tooltip": "0 = every ES trade (cell 73d). 1 = keep a trade only if NQ ENGU-Q was flat at the bar "
                           "before the fill (73a). 2 = skip signals while NQ ENGU-Q holds a trade (73b)."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 73d)": {"nq_gate": [0]},
    "Gate cells (73d / 73a / 73b)": {"nq_gate": [0, 1, 2]},
    "Medium (risk knobs)": {"stop_mult": [0.8, 0.9, 1.0, 1.1, 1.2], "act_R": [1.0, 1.5, 2.0, 2.5],
                            "trail_frac": [1.5, 2.0, 2.5, 3.0, 3.5], "breakeven_R": [1.5, 2.0, 2.5]},
}

PNL_UNITS = "points"

_N_SCAN = 10
_RISK_FLOOR = 0.5
_ROWS = 20000               # candidate rows per trendline batch (rows x tl_len floats)

# ---------------------------------------------------------------------------------- pinned NQ panel
# One token pair per NQ ENGU-Q R2 trade, base 36: (start - previous end, end - start), in UTC epoch MINUTES.
# start = the NQ fill bar's start; end = the start of the NQ bar after the exit bar (flag holds on [start, end)).
# _NQ_HEAD = (first NQ bar start minute, panel end minute = 2026-06-30 17:00 ET, trade count), base 10.
# BEGIN NQ PANEL
_NQ_HEAD = (21264720, 29714220, 2053)
_NQ_PANEL = (
    "cnvq4 chf h2g 8k 3n 1c3 2l 1n 17 6fq m 6e 1e vv ko i 74 ay 501 14 t y 2b 5g ed 2g vd bz 6b ml e f 1x 2p "
    "y 5my 28l cw5 6jy kq fj 3t 2p i7 dm dt 1t p 43q p 1m aa 355 32 10 48 149 2hlj 2k1 a 12 a4 40 7d 4o 3x "
    "3v 2p 1u 20 2xn 2q bk 4m 29 x2 1cz 18 5b 1i 5y 1r 2k 1r 5l 5f 1a o8 4b w 6j 2on 1w kf 2rf n6 15 5xz tm "
    "7wk 153 oj 3f 3j 2zz c7 2d 7os fg el 2c 7n 13s 8 jm eq 3u 2g iw dt 3qa j bf mk 5d mi 81 2fg 1c daj 5to "
    "f4 6q w 23 8a 1j 340 4u2 mk 1p 11m 1r 1m 2h kqx 6fk nk 47 uk 20j 1cf 2d t 50 34l 7ol 1p 3sg o6s 5d3 1x "
    "4m pe e5 w2 2si 8g 28e dmg 1l 34 1v rc 3gc a3 2dz 328 1p9 d4 673 4a 2j 1d 11 b0 2b 10k 40 5y 5rq ej 41 "
    "11 1v 6pq ece 13z 2q 2i 5ss rr l 24u vy g 1m 35 3q 1o 3r2 hq 2g 17j 38 9x4 6a 33u 2ce 7x qu 5n 1by 2s2 "
    "1bi 2 8u 5b da 15 1c 1x ha 52 4u 4do dj cb h 27s 549 5l 46 4u 10 7 96k dfg 1p1 1y 3a 17q 1l 9s 4q l3 1s "
    "1y 1s 29 n i 4v mk 3v 7ya 577 179 23 gr 12 hd 26 1s 26 1h 3wd 3n x 16 ga 696 3b 6d 29 1bf hw 1i z 1d 18 "
    "47 1q 3k 26 3x 5f9 3fa 5nr 1h58 711 ij1 5fy 19 2f 4 yt 12d 16z j 1d 6og 69 2u 1l2 30 3p 5m 14 ao 3zi "
    "37om 1ix ed z 1n 58 d5 f7 5x 8b 40 63e 3i 23 ci 4d 1r4 11 as 1j 3ac 3a 4c 1o no ep 1h 1kj 2b 7om 8k 2o "
    "4v z4 1s 26 2m1 1o6 4e 2i 7r 6zy 8h 6f 85 1k 3s b8 20 2h 18 1b 3h 5w s 14 z 70 8pd 5om 2cz dh 66 34 2tc "
    "66 4g w 3k 1z 2c 6h 3 65 u 1ju 8d 1v g 8f 7c 141 7m5 62e pt 24 ks 5f 3g yh 2wd 49 6u h 8b 6f 386 16 12f "
    "4er 26 66o 5b 1o 9i 1c 13c 2x 616 40m 4dd 2l 3s 1h 24m xm 1p46 1hb 95 15 9j 5x 5 41 2hp oa 1i 143 7 1h "
    "1t 1a3 uo s 1by av3 c 38 3fl 7hj 3i 1b7 3rk 1a8 6r 1g0 ue 3nl 1ge 22 eq 6y4 29 60f 35 sx 8e 13 d 1i 15 "
    "t eh 1y 8om 1c 7rr 19v z1 3h3 z i 149 2x 11q og 4l 4qf 2ba 5e 6q 2u ao 8m an e46 162 97 ny 37 2q4 1m3 g "
    "lk 15 1m 6o 4z 8q 1m 2b 32 ta j5 1u c 1w 33 p j 11 14 13 10 7d 38 31n 6j i 2e4 8c 2i 3q 6g 1bz 3y c 3 "
    "2g 32 40u 2d 8f nk e 2c 1o 2c aa 47 5q 1wo 4gn 21 6oc 1ga ht 6r 6f 3e je 1i ac hh 72e l3 3y f5 es 44c "
    "60 3i 11m 5mf 1k 2u8 1s 31 5i 9 am bc cl 35v 6a 23 4k8 1m 39x 10 12l 7y uv 4e 4p1 12m tf 15 j xw 44 3p "
    "5d ju y 54 2r 1f9 338 5j ay0 57q 3a 3y 3n 3z 3a2 20 38v 1d4 da 5ay 1lk 1i wll 63b 8o 16 5q 8o 83 4w 3s "
    "1yc bp 8bo 3pw 2y 3i jw 15 2mt 90 20 5r 3f 1c 1i 3co 3k 264 6aw 3c 18k 20u 3z 4mq 1o iw 2da 1f 2f q 50 "
    "k67 wu 33 df a0 79 ekj rx i 2d 8b 2f 149 1j 2x2 gp yf 3u 1yl 4s3 v 15t e g5 31 gn 1a 10 46 ns w 18 6z o "
    "4jk i6 2h 2pa 29 7n ml 4at 2a 1m 4a 68 33j 1c zlc 2do 5a 2a dzz xd 3f 3u 4qc 3m 20x 2s to 2b 13z 3es s4 "
    "a4 26t 466 8q q 1v 16 ri 3i 35 29 127 2n 5sl 39r d8j 11k 5a nb 9b 5a 4h 18 6i1 5n1 a6 3e 6x 4y 7e 4q zu "
    "74 189j 1uy q i 1k 1m9 1k 3o i8 2th c4 2f 2t 3w 53 307 19 1a 5g 1e 14a 2u3 7g 39 3j 26 4e zr 1i 3 c 1p "
    "1rv 4d 29 2g y 1o 1u 26 6sj 1n 38 1ag t7 2j6 3y f8 ej 6x cp 1g 38 3s 2h 2c 198 1er tx 20 2bh 1mr 2m4 33 "
    "ue 6c7 x 1f 8h 5e6 r ku 3i 4e 1y e7 z 2a 3b 18s sd b09 3i 8c 1s 8o oz 2x 13z 24 wh 6j9 3o nq 84 3g 4p "
    "5eu 5q hy n3 1d 8sx 2u 11m 4f9 2 6 18 l 6l6 81 v6 1i 8 28s 13b 57 6js 3ws 41 xg bn 3a 5q 2d 3p 3p e77 "
    "29 13yd 2go 5bl 4i 2b6 3jl c1 30 72 t 6 f 8 2e 3mw 9s 1v 4p4 8k 13 6l lh 89 61 nt 5j3 6c 41 e 1c 52 1yr "
    "58 13z 7t7 1c luo e1 2b 3o4 p f 68 2g v 42 5x 7v 114 1fd 3a 1j 97 2e 47 24 1p 1a 3g 29 13u 4nw 9 5q 5q "
    "1b 89 k 6o 2s 5dq 8wf 12c 4u3 r6 6p l8 1we 9z 1d 6x 2o 22 24 w 91s 5l0 48 5z 2k c2 x d0 eh 3t3 12 35l "
    "fh 5d7 35 tuy 2oq la 1q 32 p 4gl 1h4 2o ff 1b 1d 1p 6 8 1dg h 45o q 2ow 6v 1t fh h6 6a 6g 21 3p 17 2e "
    "et3 73i 8f 21 142 4a 37v 7bu 33 2z 2f 14 a i ai bf nx 53 7ka 2u8 2n 1m 52 5d 31 2h 1o 2f 5j 32c 3 3h "
    "162f vj 3g 5d 12 38v 6y 29 217 18 4g 1j 7lc 57q 6f 3d 7 1i wq 5q 23 5h 3j 71i 7b 4c 2t 2k 9s dj ik jh "
    "3p 44 l 3p 77 4c 5fs 17c ws 35 y8 3y9 g5 45 y5 52 6sj 2r 159 4ve m 56 20 w m i d9 4n 3a gu m 2z 18 4m "
    "1b 1s 5 2z9 9d 1f 48m 13a bn 44 21 mm dny 1iy 97 1t l 2b 1m 1k 62 2j qv 4l 7a 2c 38f yb 2jg 6ic 244 3a "
    "7 m w 4tk lf 1n 4u 4b 8wp 6ek 18 5 1k 5j d 1t yp 43 w4 2i z 3j2 tx gz 5 j r 1rt 18 t4 2sx eh 2s1 25 6fg "
    "1i 7x 88m c6 1o 12e 2n 7q8 4qu 9t 4f 73 23 28 2c 2g 1ju 19 cu 6l 2v uv cg 35c 2p 278 7xd 17h s 4ns 2bk "
    "hc 9y 1h 9x ek 35a 4k yr ep 2p 1d 17 y5 3p 27 1ax fn 382 1o 1y aq 6x px 26 2ml 9z cg 3lq 2b 3u2 hv 5s "
    "20 5ih xs 7a uz 46 19s5 4pa 7j 44 a4 1w 6s 3l 6ka 1h kj 14f 242 51 83 2h 3cu uo 75 6q 13i fj dx 3zz 6v "
    "1r ak 4 6 78 m6 3p 2p j4 f0 4w 44 1x 2f 6ht 4f 3d 4u 66 po 5d b 3 17c 53l 6vq hy f7 1h 17a 9i e ey bm "
    "dju q 14 1c v yb 8iy 5jf lb 3s ud 42 10k 6k3 7rh 9a b0 8f w4 3y 2a cr 2j 7kk 5w 4sq 1di 2v 2o b7 1l 3o9 "
    "23 2v 1x 2t 1ja 15 l 6nv 2pl lo 11s i 13 p 7 s v dic 4wu 6r 66 c qr 49 18 12 y9 86 4i 2s 4a da 4h 30 38 "
    "ge 2i ai kf 44x 1wg ba 1y y 5o 1t yr 5r 329 l1 va b0y 4dn 2e 76d d t 1a 1v 4t w x 6jf 4m 2h 2oy 5ut bp "
    "37 1r 3t 7 3u 39 2ud 39 4f 9d 1o x 34 2p3 1l 101 2v 1ee f 8vu jb u 3l 5b 2z 5s 3a0 3t 7a 1g8 nr qn 6vr "
    "1n h 7 8 16 5l 37 1j8 21 2n 64 19 1p 3ct 40 a5 1zw 1e 36 3l 18z 5kr 127 2w 54 4f 5j1 5k 1q 1oo s6 21 "
    "82l 1s 6k 2u bs 5b 56 2ba 1np4 3oq 1z 65 25 77 6b 65 e9k 1j2 4d 5m 7m 2f 70 2a 10p 33 12 3lm n1 43 1s "
    "3q zc 1ad c fo 5u 5v 35 3z 13m 2tw 5l p v7 7v 1g 1u 5v 3ir z 2l i 3c4 319 r t 2e 6k0 cnn 2dn sz wa 1do "
    "31n 124 gy0 5bh 5 n qpu 5ij 2k pp 4z p 50 f0 12 62 5d 2o 6r 1o 45 3c 6li 4e x4 ot 2h v 2 2x 8q bc 2ae "
    "h2 11z 6z 3o 1l 5xz uq 7m1 2ci js 4a ay 72 19 1e 14 nm 8p 34 345 1u 287 u gp4 3th c4 3f 1u 4o 16y hq vm "
    "21 1o 74 37 3m b t 74 8h 15 ul 17 3o 38c ma 5j c9 8v zk y9 9d d3l 287 75 fb 3y 2e 2y 1t 82 5x 2co 1ad "
    "85 n 5p 47 d g 6ra 1jl o 71 1q 28 bt 17d 2a vd j 2ov gn 1y 77 27 yp 7aa 7o 69 7p 2f 13g 9d f5p 2x 109 "
    "39 ed7 4v2 hu r 1a4 2u 2a 30 7gt 1i 15s i3 md 3j 8vy 5j3 4d 50g df 8j tq 1a 1w 37 3n 1h5 5y 5q 5a 24 "
    "121 17 3cf 3o n9 1zp 5j 1t 20 65 23 75k 3d 3z 6x a4 i 2t neg 46d 4n pb 2y 4 u s 4o 3t v 2d 12w kq im "
    "13u b 29 4r6 10f mm 45u 1bv 1x 75 3h 21f 5a9 h c 2b 28 e 1e 14x 71 9l 6v lw 146 1f 3h2 70 1d4 7m 4r u "
    "13 16 1h 28r 3b 2hx 6i 1qf 26r 12s 2yj 1o x 7a 1p 36 3h 3kv xn 32d 1z 7s zh 12z 7kz 59 4r vt 2v 6 n 4jc "
    "4c ie9 10q 2h 42 8h 22 5z 2bq qr 3ly 6v3 15g bq 1i 7e 2n 6jb 47e 3y 9h 131 2mo 4h 1l jj 26 7 24 3p 2h2 "
    "1d rc 8x6 19 vp 50r 87 3v 6v 2n3 ou 9 ddc 5a xf evp uz dn je 21 6fv t6 1jo 1s 4j9 130 7sn 3w 5zl 1zf ok "
    "6z7 s p3 4i 4c4 2i 10 1i 1o ace wx y f4 gp 1a 4hk 2j 3b 60 5c ox 4a 57k 13 31 1gx 3s 7bu 368 4p bob fo "
    "4k 16 6cc 2p 2o 1u 36c 5p 2h 3j 2j 6p c9 e3 24 w b 1m 42a 55 1o 4 1k 39 20 axp 78s in 69 39z 1ma fy 7f "
    "4k 1by jf 369 6b z o 5 9m 5r k2 2m 2f 2f 2q 1j 1d a4 kl r 7 3i 5r4 3f cv 1vk cg m3 tl 2nd 2gc 13c il 3t "
    "gah 3ls 2fv u hn nq k1 6b 1n 4o 2p8 rg 8z 194 1en 39 57 2z 5s 7yl il 28 df 2el 8y l7 118 26n 5t7 y4 5om "
    "1f5 2q d 1g 1s w d 18 20 2o 3j 15 2h vo 8a 2q 1h 2o 5d 5c 4rj as 73 15d 13v xa 4nj 1ot qg 1e 2n 6d 40 "
    "4j 3y 7k8 45v ga 1q ys 1aa 5d 3nz js 13v 4 1 8t v0 11 a 15x 28 d6u 7h0 14 aa 6oh 1b8 2c 54 1y 4u et 1p "
    "1c km 34 5c as gz hx 3g 2y 36 3c 3qx gk 3v 1ba f3 1c 2f r 1e hz 1c 5 38 f6 2g 2r 5j 3ke aj i 1sr 4o cgn "
    "9c 6c 71 2r 3ce 4ex jp yi 17 j 19 36 3i 5hd 4b 2w 9h w 16 1l3 nd 3b 23q 4lh 37p 732 f3 66 s p 4v 1d 37f "
    "4fk cc7 361 2x 4n7 2h4 67e 6o 83h 60 ag 5o 23 1o 3u 5xt 2ob 37r 1w ck 1c uy 2x 6jv y7 1e 4d 1jx 4x 64 "
    "3j ih 79 4og 2nr 2d 11 4bl 2zf 42 2n 5t 12 93 13 86 2p 3s 1p ai z 7y 2t0 9 1o p 1i ji 59 15 4m j7 66 xs "
    "1a p9 27 34 4l1 2c 4q 22 3f 20v 37 3y 8d jv 2l 7r8 13p 8b 1h 3gc ad rr 9q 4p dc k i8 6o oi b 5g po 3z "
    "39u el r 2c jn 7f 67 o7 24 6bs 1u u 1i 47 2a1 2m 7u 48 oe 1a 7tj 5aw p 3o 4j 1ni ks 13 6pa 35 n5j 23 ar "
    "3g3 wr 1cb uk 5h0 b4 2c d4 93t 5dd 2lt 7u epy d 3h ae 2y 7t9 yh 3m 2r 46 18 6t 1q 9f 305 1v4 3m 33 4f "
    "p2 35 47 1 6is 2a6 4gb 54 44q 5c8 2x 2g 5f 2s 7yb 1iv 2y z 4j 3y 33 4l 26 3sx 1f 1l ci 28 1u 1j q4 3d "
    "gx 4m mj s9 1i 3w 54 29 3c1 pr r 9b1 7vp 23v 4qj 5n 1i5 2y 6s 53 v4 4b m 4mg ro 2k u o 2ah 4u 2e5 r8 2h "
    "214 2r 3f q8 25 4td 2ci hu 3c 4g 16 y 1 54 37 yj 2v 6n 4qx 9 13 1o 44 1q 4 7n 1p 1k 7b 2 5 7 29 246 5ut "
    "19 u 59 5d ad 16j u 3r7 mh 2v7 36 3f 1g 4n 1a 2q5 1nd 23t 4hg 3p 2c6 p 14v 3u na 4ac 4i 5s 8u 1bt v0l "
    "1rm 96 2yf bf 22 kc 4m 1n 2i 2f 3i 1aw u fz 1j 1bf 13 ik 2hm n2 3dl 2 mm fo 3 3oi ey 3d 97 ts9 10z q 16 "
    "9o z 4 s ao fx 2tz 2co 1jj 1m 9e 3d 3q a9 t8 10 1h 4i 9qd 4ta mr 2h h9 55 1y g6 10s 3ka 27 5c 1s2 8g vg "
    "m 3qb 3n bsn c3y 1c9 24 4p 1m 1kq 7g 5x 6gb 34 8tt 1cp 3rw lq 1b r7 3c 1u 2a go 31 6b 3d 5a al sa 1t 1s "
    "2e 7t 2un 1ph 4f 5a 5jt 139 29 fg 34 4r 1m 4 68 1j 1b 89 2b 1l 1x 154 17 l 1q 3s9 sq 1wr 41 22 3y g9 1a "
    "lj 6m wf 9p 3d6 2eh d 11 32 36 k9 3j 25 ib 4s0 cz 25p 4sj 7s 22 ox 3b s9 6n 1qj 1g 37h 36 1dz 2kf ck 69 "
    "db5 1pa jq 24 2j1 2f ea 4q 1a8 38 2bx t9 5 n 6e5 3x 2v 5e3 bw 2y 8uh 1kx 7l 5d 6q 3mn fhd 202 29 23h 2c "
    "41 4fj 36 2e 5q gv 1t 8z 1q 13o 4ic 315 wl br 8q 7qg 5dh new 1g z4 72l 5h 1w 81 3k 8u yn 13 3ln 26u 18 "
    "1j 5xr 3p 3t 9w 34 144 4wg jx 2r 1p w ph 3i 5k 15 m 1t jo c4 1z3 35 43 3r8 ya 1o 46 19r qm 32 4x4 1v 56 "
    "2c 96 36 47 24 ya 5g0 u 3xw 5f 28 a6 3bw 26 1c2 3v 6bo 1q y4 3y 8e 2e 3i 8q 3v 5 2l 5r6 1n c0 282 96 4q "
    "l1 25 1n bm ka 2y 34d 3f 1uq hw 66 1a2 nk 1v 7l 2fj of iq jt sf 32 3y 2f g 1az gr lp 2ic a9 4s bb 46 "
    "a2c 50l ac 25 ad 5f 3y g3 61 2w 3gb 1k 2u1 1c5 1q 4h ebo 2uy 2l 36 1j4 1t 33v 16 8g 2d5 6r 3x 7p 2h 9p "
    "52v 8h 39 2 8 7 3m 6m6 3e 22x 5jg h dq 1tv 42 6p 3k 7l 4c 734 104 2s 6i 5ur 2wy 29 5zl 93 4w o 3m 2g "
    "3zl a7 35 8 u lt 5a 2m 1p e 1a 8k 4r 4y 6k ll 6es 3e3 dj 5ad 4k zf 4j7 at 6p 1b a9 bg 7s r ec 6i 12 8d "
    "3g 36 2d2 173e 2g8 45k 44k 317 29 32 1x 5c 1l 2z 6x 21 4h 141 1pq 1r 4y fj3 3ua 3d 5f 47 1z 7 30 g 2c "
    "yf 2m 2t ay 20g ku 90 45 7p 6r 35a l 1ba 2n xy 1jl g2 5u w 1z 2hd qy inn 4as 2q cj 10d 1s 28p 5wu mh 2z "
    "6ow 24y dk 13d 31l 17 94 50 p6 37 gux 12h kq g9 l1n 86z 1p 5g s 12 x t 3t 2m u 3a b 52 10e 5j1 5gy 9gd "
    "11 ri 12yi 22o 3el 1j 7pe 355 2p t eq 4nm 1t 82 9d h3 qt 5se zp y 249 3si 1e 21 v 2v 97 2rq hj 5e3 z 1x "
    "68 2f adv 3zr 5 i2 b3 2z 7f 7t0 2bq ee7 4y 29a 5ly 6mm 1wo 2i 77 5c4 d 17 3q 1s x6 73 x4 65s dd s 3u "
    "1le z 2u 37 2t 1h 3a 81 1v 2jz 3v 4fc 645 wk 10 31 49 1q 1c d 39 z8 4n2 12p 15 hoe 374 14s 9cl g9 e s w "
    "1e 2k d 5sy 1o 8c e 1h j4 62 2s 1j wv 7kt 1f 2e a 4l 16t 3um 1c 3a 40 3n 1o 2l 12c 3p zv 6en 71 2b 5c "
    "1s5 a1 94 33a 38 12c 1g 10s 547 6o 48 4m 26 qe 14b 17 h5 i 9 6ga 1h 15z 13b 5d8 b2 20b 15 6d 6pi lk 40t "
    "2mb hc 9i 2m ly v 5k9 6fn 100 cq 74s 3dm 82 1d 8g 9 3l1 iy 3i 1u 1i7 27 232 5wn h7 z 69 2b d9z 1kc fa "
    "1a 91 3s 18 e9 e2 1w 32 2p3 1g u 99 2i 1j z 6t ew 1f 3e 88 1l 9g 2v x9 85w ud h 13v 7fw 6a 31 9 3 70 "
    "3yv 8o y 1z 14b 6m6 7bb 8n c2 4b 2m 12a 1c 1j 688 5y 1kz 3g 2o 3e 5p 5q 4xg tq 1o o7 3n 3y 11 7 3d 1bo "
    "7jr 22zt 1kp 28 by mo 5en 1j 314 54 7c 4f 4q 3rx 2w k8 nm 9e 11 2m j 2b 3b 10p 45p h2 hz ba 33 2l 3i "
    "23f j rj7 1tb cg 12 7j 7a 3h sv 1z 4gl 134 p 2xr 6rm 1f 4f 69 e1 25 31 6c 3tw 4n un a3 2dl 2e 2e fq 1k "
    "2g 2np cz z 1i 21 1a 1w 83 bb mh 11 m 3w 2g 6ni 2e pq 1w c3 ot 35 5aj 3p 2px pt 9t 4d wc 1e 4bw 117 49 "
    "hc lc 8c 45x n 36 5z vo z 1w 40 2c 3a rn 1la l2 4 312 37 5y oj 2v 33 8h 41 f 2n8 ha 5b w 1a 1d 6f 37k "
    "3k yn 5o 1m 1i hj 93v 2t ks s 8 9b 3l 57 2se c7 22 4j 2t j 1j k 1a 10w 5yk 1c 31 ip 45 1bh yz 17 1k efw "
    "1hu 8d c5 5il 7j jd 2b 7a 35 v 1hn pt 1d 5k5 1b3 yt 2f 5l3 12 6gy 2xl 36 64 1u 53f 9z 2s 5e 7 33 4j xc "
    "24 7np 13j u 4a8 6v 1r 9nv 5qq 34 a 1o q9 4a 46 15 x 1m 17b 2y 15t 44x 2q 1h s c6 2y4 q b4w 2a9 5g9 2k "
    "2m 37i 4kv 9v2 5en 4n 32 10p a 1b 4x 2e 16z 1we ben h3 2tj y7 5e 47w 1bw vl ej 2h 2 4 g 90 t 8w 5t elz "
    "54g am 33 7r 2f 9t 52 8c 5k3 1i 2w ba7 3rt dz 31 10i 1 1jmw 603 89 1j f 9u 11 1n 14v f 111 1p x 52 6id "
    "1bh 81o ov 4z 3ov 6c 3j 7q 2f n 84 1y 2km 2r 3o 8f 23 c5x 1pn b5 38 4j 5o 100 2j 88 6d0 157 2v 2hu 64 "
    "uj ul 48 2g nx 1ae 5cy 2xv q8 55 2c3 216 xe 50 yp 4nc 2t le 3t vy 45 1h 6y 1c 5e g 5ch 144 1j 1i 2p 2h "
    "1d 5oi sr 2cc 29 kb bn 2h 3v 16c 2tf 4d 4d 6e z1 2v xu 1l1 ex 6x 1f 39z 3h 9m0 3k 6m 5k 4s 4e 1bj 7k 24 "
    "11 5s 3c 2a 4ku 2tg r 37 7i 2ti 5q 25 h2 fk a1 1k 52 y 30 9p pi 4h a7l 1j 6gq 19 39 195 2di 37 yh 4v ex "
    "53 5 2a 62 1p l6 6av a0 24 1g 52 3dt 1y ek9 5n0 38s 4tb kp 1e 26c 1o 6p6 4ex c o 3n 3o 23 ad 7w 3w 8b "
    "1t 1x 43 j9 61t 1cx 63h 5u 44 g2 1vi xz 6dp er 1in 4z 2w 9s 1p eji 3r5 lv 1as 7f 2sz 5t 4g 4a5 7xl zj "
    "2p m57 2xb 2q s at 3g 3gm v1 66 1r 20s h 5ks 29l 56 re 8n z 2v6 3u p 6u 2r 1b 26s 4rb 1dy 3f cj 16 134 "
    "2z 7d 6ey oi 1p 9ex 61l 84 4w 43 ac vj x u6k 4mt p9 1x 4d5 ae5 v1 4o uv 7pi 3w to 6f 7o 18u 6s 4fo 3w "
    "6k4 26o 9w 7p 46 ax 28o 4d9 fv 7j e 49 1hv 1l uu 3hp 8c 2e 2e 36 6b 1j 7f 22 128 sk b 6b 5y8 32 1xu byq "
    "99 4e 12 2hu cv 71r 10j 1by 2ez 2y n5 2x i3 4h 76 1h7 qz fc ln j4 5a6 6wx ol 5z bf 67r 7h 118 185 2x "
    "c1k 1c5 zw 13 4d 1c d4 1m 18 6b 15c 4v 2s7 1f j8 6r 1yn p6 5w 13 a0 1d 96 7c 3as 6o 8r 6x 2l 1gd so 7i "
    "hfb 2p7 5a3 3x0 3t 2j fi 30 1xo 11w 482 26 1j0 57m a5 18 2d 32 33 43 ar 2s 2m x ai uk 2u 7g 1k 59s 19 "
    "6u 170m 3r4 us 5i 4l oe 1ah 7u 7gb 1n 14e 7ru 3u9 3a 1xj gq 78 21 2m i2 1c 3c 3o 1a 1g b n 8a 1v 5jd h "
    "10 62 3b 1yy 2te 1w 1r bh 18 60 32 1p k uh 38 17z 2r 7kw 3x a 1j 8ms 4dn 26 7y 1o 66 ed 23 80 20 qk qq "
    "on 5r 14t 2fn 1x7 10k 161 65 y8 5po 13u 3n0 2un 1yo 63 2nu 98t 6st c6 2w 23c a4 3o 3h ld 452 55 36t 12 "
    "1b g 37 8f 4ux 4t q 1x 19 9 2c 1v 33 6c 26 ivi 6ww dim 2u5 8 h 2 g o 3l9 ji 44 1k4 7c 2t 7x c3 54e do "
    "5s 5z m me 2e3 18 5ry cdu 121 ru 646 1o 32 x 3c 2s 4c 3q e6 1h 78 en 1o 15 v 8b 5x h4 3l 53 3r 11f 5kj "
    "dnb 2vi 1bi 44 mu 3rx 2ez 596 cc b f 65 2b 2h dq 2h vy 5i2 3qh 5w8 7v 3c 4z 1e je 9p 6x 3v 3q2 3d 1rh "
    "4g 12vv wb e 3u 1tc 2e 21 5si 3 a q 78 5x 4b ax 1i 4l 4i 1a 2j 6kg 52 i0 ez 4zt 65 fz k 1hr 8o2 efm sr "
    "1l 14 2b au 8g 3wt q 23 1dk "
)
# END NQ PANEL

_CACHE = {}


def _nq_intervals():
    if "iv" not in _CACHE:
        tok = _NQ_PANEL.split()
        v = np.array([int(t, 36) for t in tok], dtype=np.int64)
        if len(v) != 2 * int(_NQ_HEAD[2]):
            _CACHE["iv"] = None
        else:
            d0 = v[0::2]; d1 = v[1::2]
            st = np.empty(len(d0), np.int64); en = np.empty(len(d0), np.int64)
            prev = 0
            for q in range(len(d0)):
                st[q] = prev + int(d0[q]); en[q] = st[q] + int(d1[q]); prev = int(en[q])
            _CACHE["iv"] = (st, en)
    return _CACHE["iv"]


def _es_flag(index, n):
    """NQ flag on each ES bar (int8), as-of on bar start; bars at/after the panel end read 1. None = no panel / index."""
    iv = _nq_intervals()
    if iv is None or index is None or len(index) != n:
        return None
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        idx = idx.tz_localize("US/Eastern", ambiguous="NaT", nonexistent="NaT")
    t = idx.tz_convert("UTC").tz_localize(None).asi8
    bad = t == np.iinfo(np.int64).min
    tm = np.floor_divide(t, 60_000_000_000)
    st, en = iv
    k = np.searchsorted(st, tm, side="right") - 1
    inside = (k >= 0) & (tm < en[np.clip(k, 0, None)])
    out = inside.astype(np.int8)
    out[(tm >= int(_NQ_HEAD[1])) | bad] = 1
    return out


# ---------------------------------------------------------------------------------- indicators (the parent's arithmetic)
def _ema(c, n):
    k = 2.0 / (n + 1.0)
    return pd.Series(c).ewm(alpha=k, adjust=False).mean().to_numpy()


def _signals(o, h, l, c, vv, have_vol, tl_len, vol_mult, buf_atr, min_brk, ema_len, atr_len, regime_len,
             er_len, er_th):
    n = len(c)
    ema = _ema(c, int(ema_len))
    ok = (c > o) & (c > ema)
    if int(regime_len) > 0:
        rb = int(regime_len) * 390
        if rb < n:
            reg = np.full(n, np.nan)
            rc = np.cumsum(c)
            reg[rb - 1:] = (rc[rb - 1:] - np.concatenate([[0], rc[:-rb]])) / rb
            ok &= ~np.isnan(reg) & (c > np.nan_to_num(reg, nan=np.inf))
    tr = np.empty(n); tr[0] = h[0] - l[0]
    if n > 1:
        pc = c[:-1]
        tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    al = int(atr_len)
    atr = np.full(n, np.nan)
    csum = np.cumsum(tr)
    atr[al - 1:] = (csum[al - 1:] - np.concatenate([[0], csum[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)
    if float(vol_mult) > 0 and have_vol:
        w = 20
        vavg = np.full(n, np.nan)
        vc = np.cumsum(vv)
        vavg[w - 1:] = (vc[w - 1:] - np.concatenate([[0], vc[:-w]])) / w
        ok &= ~np.isnan(vavg) & (vv >= float(vol_mult) * np.nan_to_num(vavg, nan=np.inf))
    if float(er_th) > 0:
        L = int(er_len)
        chg = np.abs(c - np.concatenate([np.full(L, np.nan), c[:-L]]))
        ad = np.abs(np.diff(c, prepend=c[0]))
        cs2 = np.cumsum(ad)
        vsum = cs2 - np.concatenate([np.zeros(L), cs2[:-L]])
        er = np.where(vsum > 0, chg / np.maximum(vsum, 1e-9), 0.0)
        ok &= np.nan_to_num(er) >= float(er_th)
    ok[: tl_len + 1] = False
    prevh = np.concatenate([[np.inf], h[:-1]])
    ok &= c > prevh
    cand = np.flatnonzero(ok)
    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()
    keep = np.zeros(len(cand), bool)
    off = np.arange(tl_len)
    for s in range(0, len(cand), _ROWS):
        ci = cand[s:s + _ROWS]
        hw = h[ci[:, None] - tl_len + off[None, :]]
        mu = hw.mean(axis=1)
        slope = (xd[None, :] * (hw - mu[:, None])).sum(axis=1) / xss
        tl_now = mu + slope * (tl_len - xm)
        a = atr[ci]
        cc = c[ci]
        good = (slope < 0) & (cc > tl_now + buf_atr * a) & ((cc - tl_now) / np.maximum(a, 0.25) >= min_brk)
        keep[s:s + _ROWS] = good
    return cand[keep], atr


def _manage(o, h, l, s, ep, risk, stop_mult, act_R, trail_frac, breakeven_R):
    """First exit bar >= s and its fill, or (None, None) when the data ends with the trade open."""
    n = len(h)
    sl0 = ep - stop_mult * risk
    mprev = -np.inf
    step = 512
    while s < n:
        e = min(n, s + step)
        M = np.maximum.accumulate(h[s:e])
        if mprev > M[0]:
            M = np.maximum(M, mprev)
        sl = np.full(e - s, sl0)
        sl = np.where(M - ep >= act_R * risk, np.maximum(sl, M - trail_frac * risk), sl)
        if breakeven_R > 0:
            sl = np.where(M - ep >= breakeven_R * risk, np.maximum(sl, ep), sl)
        hit = np.flatnonzero(l[s:e] <= sl)
        if len(hit):
            j = int(hit[0]); x = s + j; sx = float(sl[j])
            return x, (float(o[x]) if o[x] < sx else sx)
        mprev = float(M[-1])
        s = e
        step = min(step * 4, 262144)
    return None, None


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 tl_len=206, limit_atr=0.55, vol_mult=1.1, stop_mult=1.0, act_R=1.5, trail_frac=2.5,
                 buf_atr=0.3, min_brk=1.6, ema_len=220, atr_len=52, regime_len=10, breakeven_R=2.0,
                 er_len=100, er_th=0.0, nq_gate=0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    tl_len = int(tl_len)
    if n < tl_len + 5:
        return None
    gate = int(nq_gate)
    flag = None
    if gate in (1, 2):
        flag = _es_flag(index, n)
        if flag is None:
            return None
    have_vol = volumes is not None and len(volumes) == n and np.nansum(np.asarray(volumes, float)) > 0
    vv = np.asarray(volumes, float) if have_vol else None
    sig, atr = _signals(o, h, l, c, vv, have_vol, tl_len, float(vol_mult), float(buf_atr), float(min_brk),
                        int(ema_len), int(atr_len), int(regime_len), int(er_len), float(er_th))
    limit_atr = float(limit_atr); stop_mult = float(stop_mult); act_R = float(act_R)
    trail_frac = float(trail_frac); breakeven_R = float(breakeven_R)
    trades = []
    k = 0
    ns = len(sig)
    while k < ns:
        if _stop_event is not None and _stop_event.is_set():
            return None
        i = int(sig[k])
        if gate == 2 and flag[i] == 1:
            k += 1
            continue
        swing_low = float(l[i - tl_len:i + 1].min())
        if limit_atr <= 0:
            fj = i; fp = float(c[i])
        else:
            limit = c[i] - limit_atr * atr[i]
            jmax = min(i + _N_SCAN, n - 1)
            seg = np.flatnonzero(l[i + 1:jmax + 1] <= limit)
            if len(seg) == 0:
                k += 1
                continue
            fj = i + 1 + int(seg[0]); fp = float(min(limit, o[fj]))
        risk = fp - swing_low
        if risk < _RISK_FLOOR:
            k = int(np.searchsorted(sig, fj + 1)) if fj > i else k + 1
            continue
        x, xp = _manage(o, h, l, fj + 1, fp, risk, stop_mult, act_R, trail_frac, breakeven_R)
        if x is None:
            x = n - 1; xp = float(c[-1])
        keep = not (gate == 1 and flag[fj - 1] == 1)
        if keep:
            trades.append((int(fj), int(x), float(xp - fp), 1, fp, xp))
        if x >= n - 1:
            break
        k = int(np.searchsorted(sig, x + 1))
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    p = np.array([t[2] for t in trades], float)
    w = p[p > 0]; ls = p[p < 0]
    cum = np.cumsum(p)
    out = {"total_pnl": round(float(p.sum()), 2), "num_trades": int(len(p)),
           "win_rate": round(len(w) / len(p) * 100, 1),
           "profit_factor": round(float(w.sum()) / max(abs(float(ls.sum())), 1e-9), 2),
           "max_drawdown": round(float((cum - np.maximum.accumulate(cum)).min()), 2),
           "avg_pnl": round(float(p.mean()), 2), "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = trades
    return out
