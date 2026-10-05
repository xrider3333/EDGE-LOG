from api import shadow_seat_count as S


def _t(leg, n, **kw):
    base = {"leg": leg, "open": False, "backfill": False, "close_day": "2026-10-05"}
    base.update(kw)
    return [dict(base) for _ in range(n)]


def test_counts_only_closed_forward_trades_of_shadows():
    trades = (_t("DIP_ES_452", 3) + _t("DIP_ES_452", 2, open=True, close_day=None)
              + _t("DIP_ES_452", 4, backfill=True) + _t("ORB", 9))
    c = S.count_closed_forward(trades)
    assert c["DIP_ES_452"] == 3
    assert "ORB" not in c


def test_posts_once_per_multiple_and_catches_up(tmp_path):
    sp = str(tmp_path / "state.json")
    posted = []
    lines = S.run(_t("ORB_257", 49), day="2026-10-05", state_path=sp, post=posted.append, log=lambda m: None)
    assert lines == [] and posted == []
    S.run(_t("ORB_257", 50), day="2026-10-06", state_path=sp, post=posted.append, log=lambda m: None)
    assert posted == ["shadow ORB #257 reached 50 closed trades on 2026-10-06"]
    S.run(_t("ORB_257", 70), day="2026-10-07", state_path=sp, post=posted.append, log=lambda m: None)
    assert len(posted) == 1                                   # no repeat until 100
    S.run(_t("ORB_257", 131), day="2026-10-20", state_path=sp, post=posted.append, log=lambda m: None)
    assert posted[-1] == "shadow ORB #257 reached 100 closed trades on 2026-10-20 (now 131)"


def test_dry_run_posts_nothing_and_keeps_state(tmp_path):
    sp = str(tmp_path / "state.json")
    posted = []
    lines = S.run(_t("ENGUQ_335_S1", 50), day="2026-10-05", state_path=sp, post=posted.append,
                  dry_run=True, log=lambda m: None)
    assert lines and posted == []
    assert not (tmp_path / "state.json").exists()
