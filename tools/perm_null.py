# -*- coding: utf-8 -*-
"""Permutation nulls for a trade TAG (keep the tagged trades, skip the rest).

within_session_share is the null NOISE round 64 pre-registered (docs/PREREG_noise_r64_delta_2026-09-30.md, criterion 2):
the tag is shuffled only among trades of the SAME session, so the null keeps each day's tag count and asks whether the
tag picks the better trades within a day. A session holding one tagged trade cannot be shuffled, so it adds the same
amount to the real sum and to every shuffle. global_share shuffles across all trades (the first r64 read used it by
mistake; kept for comparison, always labelled).
"""
import numpy as np


def within_session_permutation(labels, sessions, rng):
    """labels shuffled independently inside each session group; same length and order as the input."""
    labels = np.asarray(labels, bool)
    sessions = np.asarray(sessions)
    out = labels.copy()
    for s in np.unique(sessions):
        idx = np.flatnonzero(sessions == s)
        if len(idx) > 1:
            out[idx] = labels[idx][rng.permutation(len(idx))]
    return out


def within_session_share(pnl, labels, sessions, n=2000, seed=20260930):
    """Share of within-session shuffles whose kept-trade P&L is >= the real tag's kept-trade P&L."""
    pnl = np.asarray(pnl, float)
    labels = np.asarray(labels, bool)
    real = pnl[labels].sum()
    rng = np.random.default_rng(seed)
    return float(np.mean([pnl[within_session_permutation(labels, sessions, rng)].sum() >= real for _ in range(n)]))


def global_share(pnl, labels, n=2000, seed=20260930):
    """Share of all-trade shuffles whose kept-trade P&L is >= the real tag's kept-trade P&L."""
    pnl = np.asarray(pnl, float)
    labels = np.asarray(labels, bool)
    real = pnl[labels].sum()
    rng = np.random.default_rng(seed)
    return float(np.mean([pnl[rng.permutation(labels)].sum() >= real for _ in range(n)]))
