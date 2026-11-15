"""pipelines/discoveries.py: the source rule (top-3 twins of Moon/Mars targets and Mars cells) (STANDARDS 10.13)."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))
sys.path.insert(0, str(HERE / "src"))

import discoveries as DI  # noqa: E402


def test_top_three_is_the_source_depth():
    assert DI.TOP == 3


def test_module_imports_and_exposes_run():
    assert callable(DI.run) and callable(DI.sources)


def test_place_id_joins_a_refined_window_to_its_pool_window():
    assert DI.place_id("jezero__pool__pool_00226") == "pool__pool_00226"
    assert DI.place_id("pool__pool_00226") == "pool__pool_00226"
    assert DI.place_id("arctic_x") == "arctic_x"


def test_place_counts_count_a_place_once_and_flag_mixed_novelty():
    w = [
        {"place_id": "pool__pool_00001", "novelty": "new"},
        {"place_id": "pool__pool_00001", "novelty": "new"},          # same place, twin of another site
        {"place_id": "pool__pool_00002", "novelty": "known_region"},
        {"place_id": "pool__pool_00003", "novelty": "new"},
        {"place_id": "pool__pool_00003", "novelty": "known_region"},  # re-centred copy crosses a circle edge
        {"place_id": "pool__pool_00004", "novelty": None},
    ]
    counts, mixed = DI.place_counts(w)
    assert counts == {"unique_places": 4, "new": 1, "known_region": 1, "unclassified": 1, "mixed": 1}
    assert mixed == ["pool__pool_00003"]
