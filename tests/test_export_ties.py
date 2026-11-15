"""Offline tests for pipelines/export_ties.py (STANDARDS 10.11). Synthetic rankings only; no raw data, no site files.

Run alone: .venv/Scripts/python.exe -m pytest tests/test_export_ties.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
PIPES = HERE / "pipelines"
if str(PIPES) not in sys.path:
    sys.path.insert(0, str(PIPES))

import export_ties as et  # noqa: E402


def rows_from(ds: list[float], tie_groups: list[int]) -> list[dict]:
    """Ranking rows (rank 1..n) with the given D values and tie_group values written by hand."""
    return [{"rank": i + 1, "analog_id": f"c{i + 1}", "D": d, "tie_group": g}
            for i, (d, g) in enumerate(zip(ds, tie_groups))]


def test_all_tied_gives_k_10():
    # threshold 0.415: every D is within 0.09 of the first one, so one group of ten
    ds = [0.10 + 0.01 * i for i in range(10)]
    entry = et.target_entry(rows_from(ds, [0] * 10), 0.415, "synthetic")
    assert entry["n_tied_with_first"] == 10
    assert entry["n_candidates"] == 10
    assert len(entry["groups"]) == 1
    assert entry["groups"][0]["ranks"] == list(range(1, 11))
    assert entry["groups"][0]["D_min"] == pytest.approx(0.10)
    assert entry["groups"][0]["D_max"] == pytest.approx(0.19)
    assert entry["sentence"].startswith("All 10 Earth places are statistically tied")


def test_two_or_more_groups_k_and_groups_correct():
    # threshold 0.3, anchor rule: group 0 = 0.10..0.15; 0.50 starts group 1 (0.50..0.70);
    # 0.82 starts group 2 (0.82..0.90)
    ds = [0.10, 0.12, 0.15, 0.50, 0.55, 0.60, 0.70, 0.82, 0.85, 0.90]
    tg = [0, 0, 0, 1, 1, 1, 1, 2, 2, 2]
    entry = et.target_entry(rows_from(ds, tg), 0.3, "synthetic")
    assert entry["n_tied_with_first"] == 3
    assert [g["ranks"] for g in entry["groups"]] == [[1, 2, 3], [4, 5, 6, 7], [8, 9, 10]]
    assert entry["groups"][1]["D_min"] == pytest.approx(0.50)
    assert entry["groups"][1]["D_max"] == pytest.approx(0.70)
    assert entry["groups"][2]["tie_group"] == 2
    assert entry["sentence"] == et.sentence(3, 10)
    assert "The first 3 of 10 Earth places are statistically tied" in entry["sentence"]


def test_k_equals_one_gives_singular_sentence():
    # spacing 0.4 > threshold 0.3: every place is its own group
    ds = [0.1 + 0.4 * i for i in range(10)]
    entry = et.target_entry(rows_from(ds, list(range(10))), 0.3, "synthetic")
    assert entry["n_tied_with_first"] == 1
    assert entry["sentence"] == "Place 1 is closer than the measurement noise allows the others to be."


def test_sentence_template_for_k_greater_than_one():
    expected = ("The first 4 of 10 Earth places are statistically tied: their differences are smaller than the "
                "measurement noise. None of them is 'the' twin; choose among them by climate, access or what you want "
                "to rehearse.")
    assert et.sentence(4, 10) == expected


def test_file_tie_group_not_following_anchor_rule_stops():
    # D 0.10 and 0.45 differ by 0.35 >= 0.3: the anchor rule starts a new group, so tie_group 0 for both is wrong
    rows = rows_from([0.10, 0.45], [0, 0])
    with pytest.raises(ValueError):
        et.build_groups(rows, 0.3)
