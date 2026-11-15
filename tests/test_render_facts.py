"""tools/render_facts.py: placeholders resolve from the ledger; unresolved ones fail with every error (STANDARDS 10.14)."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "tools"))
sys.path.insert(0, str(HERE / "pipelines"))

import build_ledger as BL  # noqa: E402
import render_facts as RF  # noqa: E402


def _ledger(tmp: Path, rows: list[dict]) -> duckdb.DuckDBPyConnection:
    for i, r in enumerate(rows, start=1):
        r["fact_id"] = f"F{i:04d}"
    db = BL.write_ledger(tmp, rows)["db"]
    return duckdb.connect(str(db), read_only=True)


@pytest.fixture()
def con(tmp_path: Path):
    rows = [
        BL.fact("validation", "v1.3", "auc", 0.69481, footprint="regional", kind="derived", level="observation",
                scale_m=100, source_id="s", produced_by="p"),
        BL.fact("target", "t1", "mission_pct_landing", 99.5417, body="mars", footprint="local", kind="derived",
                level="observation", scale_m=100, source_id="s", produced_by="p", comparison="reference"),
        BL.fact("validation", "t1", "tie_label", "statistically_tied", footprint="local", kind="derived",
                level="interpretation", scale_m=100, source_id="s", produced_by="p"),
    ]
    c = _ledger(tmp_path / "facts", rows)
    yield c
    c.close()


def test_numbers_render_with_formats_and_text_renders_as_text(con):
    out = RF.render("AUC {{fact:v1.3:auc:f3}}; landing {{fact:t1:mission_pct_landing:f1}}; {{fact:t1:tie_label}}", con)
    assert out == "AUC 0.695; landing 99.5; statistically_tied"


def test_aggregates_render_and_int_format_groups_thousands():
    mem = duckdb.connect(":memory:")
    mem.execute("CREATE TABLE t (x INTEGER)")
    mem.execute("INSERT INTO t VALUES (2000)")
    mem.execute("CREATE VIEW n_pool AS SELECT x AS value FROM t")
    assert RF.resolve_agg(mem, "n_pool:int") == "2,000"
    assert RF.resolve_agg(mem, "n_pool") == "2000"
    mem.close()


def test_fenced_code_blocks_are_not_rendered(con):
    text = "value {{fact:v1.3:auc:f2}}\n```bash\npython -m http.server 8765 # {{fact:v1.3:auc:f2}}\n```\n"
    out = RF.render(text, con)
    assert out.startswith("value 0.69\n") and "8765 # {{fact:v1.3:auc:f2}}" in out


def test_unresolved_placeholders_fail_and_list_every_error(con):
    with pytest.raises(RF.UnresolvedError) as exc:
        RF.render("{{fact:v1.3:missing:f2}} and {{agg:no_view}} and {{fact:v1.3:auc:f2}}", con)
    assert len(exc.value.errors) == 2
    assert any("missing" in e for e in exc.value.errors) and any("no_view" in e for e in exc.value.errors)


def test_a_fact_matching_two_rows_is_unresolved(tmp_path: Path):
    rows = [
        BL.fact("validation", "dup", "auc", 0.5, footprint="regional", kind="derived", level="observation",
                scale_m=100, source_id="s", produced_by="p"),
        BL.fact("validation", "dup", "auc", 0.6, footprint="regional", kind="derived", level="observation",
                scale_m=8000, source_id="s", produced_by="p"),
    ]
    c = _ledger(tmp_path / "dup", rows)
    with pytest.raises(RF.UnresolvedError) as exc:
        RF.render("{{fact:dup:auc:f2}}", c)
    assert "2 facts match" in exc.value.errors[0]
    c.close()
