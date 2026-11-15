"""Tests for pipelines/export_sources.py: one synthetic case per rule (missing terrain entry, missing URL, clean)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))

import export_sources as ES  # noqa: E402


def make_root(root: Path, terrain_source_id: str = "A", mission_urls: tuple[str, ...] = ("https://example.org/a",)) -> Path:
    sources = [
        {
            "id": "A", "body": "moon", "product": "Product A", "provider": "NASA / Team, served by Host",
            "access": "http", "url_or_collection": "https://example.org/a", "page": "https://example.org/a-page",
            "doi": "10.1/a", "license": "Licence A", "used": True, "use": "u",
            "short_label": "NASA A", "is_nasa": True, "mission_instrument": "Mission A",
        },
        {
            "id": "B", "body": "mars", "product": "Product B", "provider": "Other org",
            "access": "http", "url_or_collection": "https://example.org/b", "page": "https://example.org/b-page",
            "alt_urls": ["https://example.org/b-alt"], "license": "Licence B", "used": False, "use": "u",
            "short_label": "Other B", "is_nasa": False, "mission_instrument": "Mission B",
        },
    ]
    cfg = root / "config" / "sources.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"version": "test", "sources": sources}), encoding="utf-8")

    terrain = root / "site" / "data" / "terrain" / "t1"
    terrain.mkdir(parents=True)
    (terrain / "meta.json").write_text(json.dumps({"source_id": terrain_source_id}), encoding="utf-8")

    data = root / "site" / "data"
    entries = [{"source_url": u} for u in mission_urls]
    (data / "missions.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
    (data / "bodies.json").write_text(json.dumps({"bodies": {}}), encoding="utf-8")
    (data / "targets.json").write_text(json.dumps({"targets": []}), encoding="utf-8")
    (root / "site" / "assets" / "globes").mkdir(parents=True)
    return root


def test_terrain_source_without_entry_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_root(tmp_path / "r", terrain_source_id="Z")
    with pytest.raises(ES.ExportError, match="'Z'"):
        ES.build(root)
    assert ES.main(["--root", str(root)]) == 1
    assert "'Z'" in capsys.readouterr().err
    assert not (root / "site" / "data" / "sources.json").exists()


def test_mission_url_missing_from_by_url_fails(tmp_path: Path) -> None:
    root = make_root(tmp_path / "r", mission_urls=("https://example.org/a", "https://example.org/nowhere"))
    with pytest.raises(ES.ExportError, match="nowhere"):
        ES.build(root)


def test_clean_case_passes(tmp_path: Path) -> None:
    root = make_root(tmp_path / "r", mission_urls=("https://example.org/a", "https://example.org/b-alt"))
    assert ES.main(["--root", str(root)]) == 0
    out = json.loads((root / "site" / "data" / "sources.json").read_text(encoding="utf-8"))
    assert out["generated_by"] == "pipelines/export_sources.py"
    assert out["by_url"]["https://example.org/a"] == "A"
    assert out["by_url"]["https://example.org/b-alt"] == "B"
    assert out["by_url"]["https://example.org/b-page"] == "B"
    assert out["sources"]["A"]["used"] is True  # via terrain meta
    assert out["sources"]["B"]["used"] is True  # via a missions URL (alt_urls)
    assert out["sources"]["A"]["agency"] == "NASA / Team"
    assert out["sources"]["A"]["citation"] == "NASA / Team. Product A. doi:10.1/a. https://example.org/a"
    assert out["sources"]["B"]["licence_note"] == "Licence B"
