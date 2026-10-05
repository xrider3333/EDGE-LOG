"""Owner decision 2026-10-05 (MANAGER inbox #74, option (a)): the paper ENGU-Q #335 legs run on the
roll-corrected master db_adj_eth at 0.783 points a round trip, the way BOOK #463 charges them. Every other
leg keeps the default no-adjust master and its own cost."""
from api import paper

ENGUQ_335_FAMILY = {"ENGUQ_335", "ENGUQ_335_S1", "ENGUQ_335_S2", "ENGUQ_335_VC"}


def _legs():
    return {leg["key"]: leg for leg in paper.PAPER_LEGS}


def test_enguq_335_family_uses_adj_master_and_book_cost():
    legs = _legs()
    for key in ENGUQ_335_FAMILY:
        assert legs[key]["master_source"] == "db_adj_eth", key
        assert legs[key]["cost_pts"] == 0.783, key


def test_no_other_leg_moved():
    for key, leg in _legs().items():
        if key in ENGUQ_335_FAMILY:
            continue
        assert "master_source" not in leg, key
        assert leg.get("cost_pts") != 0.783 or key.startswith("DIP_"), key


def test_run_shadow_asks_find_master_for_the_named_source(monkeypatch):
    seen = []

    def fake_find_master(instrument, timeframe, session=None, source=None):
        seen.append(source)
        return None                         # run_shadow returns early with a warning

    monkeypatch.setattr(paper, "find_master", fake_find_master)
    out = paper.run_shadow(_legs()["ENGUQ_335"], "2026-10-05")
    assert seen == ["db_adj_eth"] and out["ran_ok"] is False
    seen.clear()
    paper.run_shadow(_legs()["NOISE_422"], "2026-10-05")
    assert seen == [None]
