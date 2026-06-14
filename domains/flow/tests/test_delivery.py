# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-Proprietary-Commercial
# SPDX-FileCopyrightText: 2026 James Ray Hawkins <jhawk314@gmail.com>

"""Tests: the delivery layer (daily job, delta vs prior, digest)."""

import json
import os

import domains  # noqa: F401  (path bootstrap)

from domains.flow.delivery import (
    DataPaths, assemble, diff_ledgers, digest, run_daily,
)
from domains.flow.ledger import Ledger, Finding


def test_assemble_synthetic_has_all_detectors():
    led = assemble(DataPaths(), allow_synthetic=True)
    dets = {f.detector for f in led.findings}
    assert {"ma_overpayment", "drug_conflict", "hospital_price"} <= dets
    assert led.findings


def test_assemble_real_only_skips_missing():
    # No real paths + real_only -> empty (no synthetic fallback).
    led = assemble(DataPaths(), allow_synthetic=False)
    assert led.findings == []


def test_diff_new_and_increased():
    cur = Ledger()
    cur.add(Finding("ma_overpayment", "state:CA", "c", 100.0, 0.7))   # grew
    cur.add(Finding("hospital_price", "ccn:1|drg:2", "c", 50.0, 0.45))  # new
    prior = [
        {"detector": "ma_overpayment", "entity": "state:CA", "dollars": 80.0},
        {"detector": "drug_conflict", "entity": "drug:X", "dollars": 10.0},  # resolved
    ]
    d = diff_ledgers(cur, prior, prior_date="2026-06-13")
    new_keys = {(f.detector, f.entity) for f in d.new}
    assert ("hospital_price", "ccn:1|drg:2") in new_keys
    assert any(f.entity == "state:CA" and abs(dl - 20.0) < 1e-9
               for f, pd, dl in d.increased)
    assert any(p["entity"] == "drug:X" for p in d.resolved)
    assert abs(d.total_change - (150.0 - 90.0)) < 1e-9


def test_diff_no_prior_all_new():
    cur = Ledger()
    cur.add(Finding("d", "e", "c", 5.0, 0.5))
    d = diff_ledgers(cur, None)
    assert len(d.new) == 1
    assert d.prior_date is None


def test_digest_contains_sections():
    led = assemble(DataPaths(), allow_synthetic=True)
    d = diff_ledgers(led, None)
    md = digest(led, d, "2026-06-14")
    assert "# The Leak Ledger" in md
    assert "By detector" in md
    assert "Top 10 by priority" in md


def test_run_daily_writes_artifacts_and_delta(tmp_path):
    out = str(tmp_path / "ledger")
    # Day 1: baseline.
    r1 = run_daily(DataPaths(), out_dir=out, date="2026-06-13")
    assert r1["prior_date"] is None
    for fn in ("leak_ledger_2026-06-13.csv", "leak_ledger_2026-06-13.json",
               "digest_2026-06-13.md", "latest.json", "latest.csv", "latest.md",
               "history.jsonl"):
        assert os.path.exists(os.path.join(out, fn)), fn
    # Day 2: same inputs -> diff computed against day 1 (no new findings).
    r2 = run_daily(DataPaths(), out_dir=out, date="2026-06-14")
    assert r2["prior_date"] == "2026-06-13"
    assert r2["new"] == 0 and r2["increased"] == 0
    # history.jsonl has two run records.
    hist = open(os.path.join(out, "history.jsonl"), encoding="utf-8").read().splitlines()
    assert len(hist) == 2
    assert json.loads(hist[1])["date"] == "2026-06-14"
