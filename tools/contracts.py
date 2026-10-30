"""C12 TYPED CONTRACTS (Open Board C12, MANAGER #196) - one pydantic model each for the three hand-off files lanes and Qwen
write: an inbox item (C:\\EdgeLog\\chat_inbox\\*.jsonl), a run record (C:\\EdgeLog\\run_records\\*.jsonl) and a Qwen task file
(C:\\EdgeLog\\manager\\qwen_tasks\\Q<n>-*.md). Validate-only: no writer changes here, so nothing that posts today can break.

    python tools/contracts.py check            validate every file; exit 1 and list each bad line if any fail
    python tools/contracts.py check --kind inbox|records|tasks

From code: contracts.validate_inbox_item(d), validate_run_record(d), validate_task_text(text) -> the model or ValueError.
"""
import argparse
import glob
import json
import os
import re
import sys
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_record as RR  # noqa: E402

INBOX_DIR = os.environ.get("CHAT_INBOX_DIR", r"C:\EdgeLog\chat_inbox")
TASKS_DIR = os.environ.get("QWEN_TASKS_DIR", r"C:\EdgeLog\manager\qwen_tasks")
ICONS = ("⭕", "🟡", "🟢", "🔴", "✅", "⚠")


class InboxItem(BaseModel):
    """One line of a chat inbox, as chat_inbox.post / done write it."""
    model_config = ConfigDict(extra="allow")
    id: int = Field(ge=1)
    at: str
    frm: str = Field(alias="from", min_length=1)
    text: str = Field(min_length=1)
    status: Literal["open", "done"]

    @field_validator("at")
    @classmethod
    def _at(cls, v):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", v):
            raise ValueError("at must be 'YYYY-MM-DD HH:MM'")
        return v


Num = Optional[Union[int, float]]


class RunRecord(BaseModel):
    """One run-record line (tools/run_record.py FIELDS). Shape + types; run_record.py stays the writer of truth."""
    model_config = ConfigDict(extra="forbid")
    ts: str
    lane: str = Field(min_length=1)
    host: Optional[str] = None
    where: Optional[str] = None
    strategy: Optional[str] = None
    family: Optional[str] = None
    instrument: Optional[str] = None
    timeframe: Optional[str] = None
    stage: str
    roc30k: Num = None
    dd5: Num = None
    ddpct: Num = None
    sortino: Num = None
    trades: Num = None
    gross_pt: Num = None
    cost_pt: Num = None
    one_episode: Optional[Union[bool, str]] = None
    ledger_row: Optional[str] = None
    run_id: Optional[Union[str, int]] = None
    sha: Optional[str] = None
    note: Optional[str] = None
    start_usd: Num = None
    net_usd: Num = None
    max_dd_usd: Num = None
    years: Num = None
    win_start: Optional[str] = None
    win_end: Optional[str] = None
    schema_v: Optional[int] = None

    @field_validator("stage")
    @classmethod
    def _stage(cls, v):
        if v not in RR.STAGES:
            raise ValueError(f"stage {v!r} not in {RR.STAGES}")
        return v

    def placeable(self):
        """The sync's rule: a scatter point needs roc30k, or net + worst drawdown."""
        return self.roc30k is not None or (self.net_usd is not None and self.max_dd_usd is not None)


class QwenTask(BaseModel):
    status_icon: str
    status_line: str
    title: str

    @field_validator("status_icon")
    @classmethod
    def _icon(cls, v):
        if v not in ICONS:
            raise ValueError(f"status icon {v!r} not one of {ICONS}")
        return v


def validate_inbox_item(d):
    return InboxItem.model_validate(d)


def validate_run_record(d):
    return RunRecord.model_validate(d)


def validate_task_text(text):
    """A status line ('STATUS:' or 'Status:' + icon) in the first 3 lines, and a title heading ('# Task: ...' or '# Q<n> ...').
    Both board formats in use (runner-written and hand-written) pass."""
    lines = text.lstrip("﻿").splitlines()
    st = next((ln for ln in lines[:3] if re.match(r"(?i)status:", ln)), None)
    if not st:
        raise ValueError("no 'STATUS: <icon>' line in the first 3 lines")
    parts = st.split(None, 2)
    if len(parts) < 2:
        raise ValueError("status line has no icon")
    title = next((re.sub(r"^#\s*(Task:)?\s*", "", ln).strip() for ln in lines[:6]
                  if re.match(r"#\s*(Task:|Q\d+)", ln)), None)
    if not title:
        raise ValueError("no '# Task: <title>' or '# Q<n> <title>' heading in the first 6 lines")
    return QwenTask(status_icon=parts[1].strip(), status_line=st, title=title)


def _jsonl(path, fn):
    bad = []
    with open(path, encoding="utf-8") as f:
        for n, ln in enumerate(f, 1):
            if not ln.strip():
                continue
            try:
                fn(json.loads(ln))
            except ValidationError as e:
                er = e.errors()[0]
                bad.append(f"{path}:{n}: {'.'.join(map(str, er['loc']))} - {er['msg']}")
            except ValueError as e:
                bad.append(f"{path}:{n}: {e}")
    return bad


def check(kind="all", inbox_dir=None, records_dir=None, tasks_dir=None):
    bad, n = [], 0
    if kind in ("all", "inbox"):
        for p in glob.glob(os.path.join(inbox_dir or INBOX_DIR, "*.jsonl")):
            n += 1
            bad += _jsonl(p, validate_inbox_item)
    if kind in ("all", "records"):
        for p in glob.glob(os.path.join(records_dir or RR.records_root(), "*.jsonl")):
            n += 1
            bad += _jsonl(p, validate_run_record)
    if kind in ("all", "tasks"):
        for p in glob.glob(os.path.join(tasks_dir or TASKS_DIR, "Q*-*.md")):
            n += 1
            try:
                validate_task_text(open(p, encoding="utf-8").read())
            except (ValueError, ValidationError) as e:
                bad.append(f"{p}: {e}".splitlines()[0])
    return n, bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("--kind", default="all", choices=["all", "inbox", "records", "tasks"])
    a = ap.parse_args(argv)
    n, bad = check(a.kind)
    for b in bad:
        print(b)
    print(f"{n} file(s) checked, {len(bad)} bad line(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
