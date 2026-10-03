"""The web's pre-queue repeat check (index.html DUPE_FIELDS) must fingerprint exactly the fields the
runner's dupe guard does (api/dupe_guard.py MATERIAL_FIELDS). They drifted once: the runner gained
'book_sizing' and 'legs' (2026-10-03) while the web list kept neither, so the queue prompt called two
different books on one window a repeat."""
import os
import re

from api import dupe_guard as DG

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_web_dupe_fields_match_the_runner_material_fields():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    m = re.search(r"const DUPE_FIELDS=\[(.*?)\];", html, re.S)
    assert m, "DUPE_FIELDS not found in index.html"
    web = re.findall(r"'([^']+)'", m.group(1))
    assert len(web) == len(set(web)), "a field is listed twice in DUPE_FIELDS"
    assert set(web) == set(DG.MATERIAL_FIELDS), (sorted(set(web) - set(DG.MATERIAL_FIELDS)), sorted(set(DG.MATERIAL_FIELDS) - set(web)))
