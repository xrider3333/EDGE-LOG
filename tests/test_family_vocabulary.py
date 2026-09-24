"""One family vocabulary (owner 2026-09-24): the runner's resolver and the re-stamp tool must agree,
and every strategy file must land on a family in the agreed list."""
import glob, importlib.util, os, re
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOCAB = {"ORB", "NOISE", "ENGU-Q", "ENGU", "TTM", "DIP", "GAPGO", "TTIBS", "VWAP", "REVERT", "SUPERTREND",
         "RSIDIV", "OVERNIGHT", "EMAPB", "REPLAY", "RFML", "BOOK", "MISC"}


def _load(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    return sp, m


def _runner_family():
    import api.runner as R
    return lambda s: R.FirestoreQueue._family_of(None, s)


def _tool_family():
    src = open(os.path.join(ROOT, "tools", "family_rename.py"), encoding="utf-8").read()
    ns = {}
    start = src.index("def resolve(")
    end = src.index("\ndef main(")
    exec("import re\n" + src[start:end], ns)
    return ns["resolve"]


CASES = {"TTMSQZ_3_0_ES30SSOF2.py": "TTM", "NQDIP_1_1.py": "DIP", "ETFDIP_RSI2_1_0.py": "DIP",
         "ORB_3_6_R6.py": "ORB", "ORB_FADE_1_0.py": "ORB", "ENGUQ_1M_ETH_R2_1_0.py": "ENGU-Q",
         "ENGUDQ_1M_1_0.py": "ENGU-Q", "NOISE_1_8_CT304.py": "NOISE", "VWAP_FADE_1_0.py": "VWAP",
         "BOOK: ORB 234 + NOISE": "BOOK", "COMBINED (REAL): ORB234": "BOOK", "GAPGO_TRAVEL_1_0.py": "GAPGO"}


@pytest.mark.parametrize("name,fam", sorted(CASES.items()))
def test_runner_and_tool_agree(name, fam):
    assert _runner_family()(name) == fam
    assert _tool_family()(name) == fam


def test_every_strategy_file_gets_a_short_family_name():
    """Every file resolves to ONE short name: the agreed list, or - for a one-off dead port such as
    GOLDX or HULL - its own single word. Never an instrument-suffixed or multi-part key."""
    fam = _runner_family()
    bad = []
    for p in glob.glob(os.path.join(ROOT, "augur_strategies", "*.py")):
        b = os.path.basename(p)
        if b.startswith("_"):
            continue
        f = fam(b)
        if not re.fullmatch(r"[A-Z][A-Z0-9]*(-[A-Z])?", f) or f.startswith(("NQ", "ES", "ETF")):
            bad.append((b, f))
    assert not bad, bad
