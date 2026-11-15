"""P-R rules (STANDARDS 10.14): SQL assertions over the facts ledger. Every rule is a query that must return zero rows.

R1  a threshold comparison (mission %) whose limit baseline is null or differs from the measurement scale is tagged
    comparison 'reference' (never 'compliance').
R2  a point-footprint fact is never attached to a region-scale subject (subject_type 'region').
R3  every fact has a source_id or a produced_by.
R4  no two facts share (subject_id, property, scale_m) with different values.
R5  every placeholder {{fact:...}} / {{agg:...}} of the templates resolves to exactly one fact (or one aggregate row).
R6  every feature fact comes from a record whose measure_key equals the current config's measure_key (the record's true
    config_version is kept in the ledger; a different feature definition under the same version name is a violation).
    The placeholders are read from the templates (README.template.md and docs/*.template.md) here, so R5 sees what
    render_facts.py will render.

Exit 0 when every rule returns zero rows; exit 1 and print the offending rows otherwise.

Usage: .venv/Scripts/python.exe tools/check_ledger.py [--db <facts.duckdb>] [--root <project root>]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"\{\{(fact|agg):([^{}]+)\}\}")

RULES: dict[str, tuple[str, str]] = {
    "R1": ("mission % without a baseline or with a baseline different from the scale must be comparison 'reference'",
           """SELECT fact_id, subject_type, subject_id, property, value_num, scale_m, baseline_m, comparison
              FROM facts
              WHERE property LIKE 'mission_pct%'
                AND (baseline_m IS NULL OR baseline_m <> scale_m)
                AND (comparison IS NULL OR comparison <> 'reference')"""),
    "R2": ("a point footprint never attaches to a region-scale subject",
           """SELECT fact_id, subject_type, subject_id, property, footprint
              FROM facts
              WHERE footprint = 'point' AND subject_type = 'region'"""),
    "R3": ("every fact has a source_id or a produced_by",
           """SELECT fact_id, subject_type, subject_id, property
              FROM facts
              WHERE (source_id IS NULL OR source_id = '') AND (produced_by IS NULL OR produced_by = '')"""),
    "R6": ("every feature fact comes from a record whose measure_key equals the current config's key (features unchanged "
           "across config versions; a record produced with a different feature definition is a violation)",
           """SELECT f.fact_id, f.subject_type, f.subject_id, f.property, f.config_version, k.value_text AS record_key
              FROM facts f
              JOIN facts k ON k.subject_id = f.subject_id AND k.property = 'measure_key'
              WHERE f.property IN ('slope_p95_deg', 'hi', 'coherence', 'hurst', 'ridge_pct', 'valley_pct')
                AND f.subject_type IN ('target', 'region', 'earth_window', 'mars_cell')
                AND k.value_text IS DISTINCT FROM (
                    SELECT value_text FROM facts
                    WHERE subject_type = 'validation' AND subject_id = 'config_v1.3' AND property = 'measure_key')"""),
    "R4": ("no two facts with the same (subject_id, property, scale_m) and different values",
           """SELECT a.fact_id AS fact_a, b.fact_id AS fact_b, a.subject_id, a.property, a.scale_m,
                     a.value_num AS value_a, b.value_num AS value_b, a.value_text AS text_a, b.value_text AS text_b
              FROM facts a JOIN facts b
                ON a.subject_id = b.subject_id AND a.property = b.property
               AND a.scale_m IS NOT DISTINCT FROM b.scale_m AND a.fact_id < b.fact_id
              WHERE a.value_num IS DISTINCT FROM b.value_num
                 OR a.value_text IS DISTINCT FROM b.value_text"""),
}


def placeholders(root: Path) -> list[tuple[str, str, str]]:
    """(template file, kind, argument) for every placeholder in README.template.md and docs/*.template.md."""
    out: list[tuple[str, str, str]] = []
    files = [root / "README.template.md"] + sorted((root / "docs").glob("*.template.md"))
    for f in files:
        if not f.exists():
            continue
        for m in PLACEHOLDER.finditer(f.read_text(encoding="utf-8")):
            out.append((f.relative_to(root).as_posix(), m.group(1), m.group(2)))
    return out


def r5_rows(con: duckdb.DuckDBPyConnection, items: list[tuple[str, str, str]]) -> list[tuple[Any, ...]]:
    """Placeholders that do not resolve to exactly one fact (or one aggregate row). Returns the offending rows."""
    con.execute("CREATE OR REPLACE TEMP TABLE ph (file VARCHAR, kind VARCHAR, arg VARCHAR)")
    if items:
        con.executemany("INSERT INTO ph VALUES (?, ?, ?)", items)
    rows = con.execute("""
        SELECT ph.file, ph.kind, ph.arg,
               (SELECT count(*) FROM facts f
                 WHERE ph.kind = 'fact' AND f.subject_id = split_part(ph.arg, ':', 1)
                   AND f.property = split_part(ph.arg, ':', 2)) AS n_fact,
               (SELECT count(*) FROM duckdb_views() v
                 WHERE ph.kind = 'agg' AND v.view_name = split_part(ph.arg, ':', 1)) AS n_view
        FROM ph
    """).fetchall()
    bad = []
    for file, kind, arg, n_fact, n_view in rows:
        if kind == "fact" and n_fact != 1:
            bad.append((file, kind, arg, f"{n_fact} facts match"))
        if kind == "agg" and n_view != 1:
            bad.append((file, kind, arg, "no such aggregate view"))
    return bad


def run_rules(con: duckdb.DuckDBPyConnection, root: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Rows violating each rule. A rule passes when its list is empty."""
    out: dict[str, list[tuple[Any, ...]]] = {}
    for rid, (_, sql) in RULES.items():
        out[rid] = con.execute(sql).fetchall()
    out["R5"] = r5_rows(con, placeholders(root))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rules over the facts ledger (STANDARDS 10.14, P-R).")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--db", default=None, help="facts.duckdb (default: data/derived/facts/facts.duckdb)")
    args = ap.parse_args(argv)
    root = Path(args.root)
    db = Path(args.db) if args.db else root / "data" / "derived" / "facts" / "facts.duckdb"
    if not db.exists():
        print(f"ledger not found: {db}")
        return 2
    con = duckdb.connect(str(db), read_only=True)
    results = run_rules(con, root)
    con.close()
    bad = False
    for rid in ("R1", "R2", "R3", "R4", "R5", "R6"):
        rows = results[rid]
        desc = RULES[rid][0] if rid in RULES else "every placeholder resolves to exactly one fact or aggregate"
        print(f"{rid} {'OK' if not rows else 'FAIL'}: {desc} ({len(rows)} offending rows)")
        for row in rows[:20]:
            print(f"   {row}")
        bad = bad or bool(rows)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
