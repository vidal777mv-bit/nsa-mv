"""P-G generate (STANDARDS 10.14): render numbers in README and docs from the facts ledger, never by hand.

Placeholders in a template:
- {{fact:<subject_id>:<property>[:<format>]}}  one fact; it must match exactly one row of the ledger;
- {{agg:<name>[:<format>]}}                     one named aggregate (a view of the ledger); one row, one value.
Formats: f<n> (n decimals), int (thousands separator, no decimals), g (default: shortest form).
Text facts render as text. Fenced code blocks are not rendered (commands, ports and versions are not results).

Any unresolved placeholder (no fact, several facts, unknown aggregate, unknown format) fails the render: nothing is
written and the list of errors is printed.

Usage:
  .venv/Scripts/python.exe tools/render_facts.py --template README.template.md --out README.md
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
FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)


class UnresolvedError(RuntimeError):
    """Raised when at least one placeholder does not resolve; carries every error, not only the first."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def fmt(value: Any, spec: str | None) -> str:
    """Format one ledger value. Numbers: f<n>, int or g; text is returned unchanged."""
    if isinstance(value, str):
        if spec not in (None, "text"):
            raise ValueError(f"format {spec!r} is not valid for a text fact")
        return value
    if spec is None or spec == "g":
        return f"{value:g}"
    if spec == "int":
        return f"{round(value):,}"
    m = re.fullmatch(r"f(\d)", spec)
    if m:
        return f"{value:.{int(m.group(1))}f}"
    raise ValueError(f"unknown format {spec!r}")


def value_of(row: tuple[Any, Any]) -> Any:
    """The value of a ledger row: numeric when present, otherwise text."""
    num, text = row
    return num if num is not None else text


def resolve_fact(con: duckdb.DuckDBPyConnection, arg: str) -> str:
    """Render {{fact:subject:property[:format]}}. Exactly one fact must match."""
    parts = arg.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"fact placeholder needs subject:property[:format], got {arg!r}")
    subject, prop = parts[0], parts[1]
    spec = parts[2] if len(parts) == 3 else None
    rows = con.execute("SELECT value_num, value_text FROM facts WHERE subject_id = ? AND property = ?",
                       [subject, prop]).fetchall()
    if len(rows) != 1:
        raise ValueError(f"{len(rows)} facts match {subject}:{prop} (exactly one required)")
    return fmt(value_of(rows[0]), spec)


def resolve_agg(con: duckdb.DuckDBPyConnection, arg: str) -> str:
    """Render {{agg:name[:format]}}. The named aggregate view must return exactly one row and one value."""
    parts = arg.split(":")
    if len(parts) not in (1, 2):
        raise ValueError(f"agg placeholder needs name[:format], got {arg!r}")
    name, spec = parts[0], (parts[1] if len(parts) == 2 else None)
    known = con.execute("SELECT count(*) FROM duckdb_views() WHERE view_name = ?", [name]).fetchone()[0]
    if known != 1:
        raise ValueError(f"no named aggregate {name!r} in the ledger")
    rows = con.execute(f'SELECT * FROM "{name}"').fetchall()
    if len(rows) != 1 or len(rows[0]) != 1:
        raise ValueError(f"aggregate {name!r} must return one row and one value, got {len(rows)} rows")
    value = rows[0][0]
    if value is None:
        raise ValueError(f"aggregate {name!r} is null")
    return fmt(value, spec)


def render(text: str, con: duckdb.DuckDBPyConnection) -> str:
    """Render every placeholder outside fenced code blocks. Raises UnresolvedError listing all failures."""
    errors: list[str] = []
    fences: list[str] = []

    def keep_fence(m: re.Match[str]) -> str:
        fences.append(m.group(0))
        return f"\x00FENCE{len(fences) - 1}\x00"

    protected = FENCE.sub(keep_fence, text)

    def sub(m: re.Match[str]) -> str:
        kind, arg = m.group(1), m.group(2)
        try:
            return resolve_fact(con, arg) if kind == "fact" else resolve_agg(con, arg)
        except (ValueError, duckdb.Error) as exc:
            errors.append(f"{{{{{kind}:{arg}}}}}: {exc}")
            return m.group(0)

    rendered = PLACEHOLDER.sub(sub, protected)
    if errors:
        raise UnresolvedError(errors)
    for i, block in enumerate(fences):
        rendered = rendered.replace(f"\x00FENCE{i}\x00", block)
    return rendered


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render {{fact}}/{{agg}} placeholders from the ledger (STANDARDS 10.14, P-G).")
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--db", default=None, help="facts.duckdb (default: data/derived/facts/facts.duckdb)")
    args = ap.parse_args(argv)
    db = Path(args.db) if args.db else ROOT / "data" / "derived" / "facts" / "facts.duckdb"
    con = duckdb.connect(str(db), read_only=True)
    try:
        text = Path(args.template).read_text(encoding="utf-8")
        out = render(text, con)
    except UnresolvedError as exc:
        print("render FAILED, nothing written:")
        for e in exc.errors:
            print(f"  {e}")
        return 1
    finally:
        con.close()
    Path(args.out).write_bytes(out.encode("utf-8"))  # bytes: keep LF line endings on every platform
    print(f"rendered {args.template} -> {args.out} ({len(PLACEHOLDER.findall(text))} placeholders)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
