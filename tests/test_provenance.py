"""Tests for analog.io.provenance (STANDARDS.md section 7)."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

from analog.io import provenance as pv

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
GENERATED = (
    "Code written with AI assistance (Claude, Anthropic) under the team's direction; "
    "data computed by this code from the listed sources."
)


@pytest.fixture
def config_and_input(tmp_path: Path) -> tuple[Path, Path]:
    """A config file with the frozen version field and one input file, in a temp directory."""
    config = tmp_path / "measure.json"
    config.write_bytes(b'{\n  "version": "1.0",\n  "frozen": "2026-11-13"\n}\n')
    data = tmp_path / "dem_clip.bin"
    data.write_bytes(b"synthetic input bytes")
    return config, data


def test_block_has_section7_fields_and_values(config_and_input, monkeypatch):
    """Block carries the section 7 keys, schema analog.<stage>/1, config version and generated_with text."""
    config, data = config_and_input
    monkeypatch.setattr(pv, "code_version", lambda *a, **k: "abc1234")
    block = pv.build_provenance("measure", config, [{"source_id": "dem_test", "path": str(data)}])
    assert set(block) == {
        "schema",
        "created",
        "config_version",
        "config_sha256",
        "code_version",
        "inputs",
        "generated_with",
    }
    assert block["schema"] == "analog.measure/1"
    assert block["config_version"] == "1.0"
    assert ISO_Z.match(block["created"])
    assert block["code_version"] == "abc1234"
    assert block["generated_with"] == GENERATED


def test_config_and_input_sha256_are_exact(config_and_input, monkeypatch):
    """config_sha256 and each input sha256 equal SHA-256 of the file bytes."""
    config, data = config_and_input
    monkeypatch.setattr(pv, "code_version", lambda *a, **k: "uncommitted")
    block = pv.build_provenance("validation", config, [{"source_id": "dem_test", "path": str(data)}])
    assert block["config_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert block["inputs"] == [
        {
            "source_id": "dem_test",
            "path": str(data),
            "sha256": hashlib.sha256(b"synthetic input bytes").hexdigest(),
        }
    ]


def test_code_version_uncommitted_when_git_missing(tmp_path, monkeypatch):
    """git not installed -> 'uncommitted'."""

    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(pv.subprocess, "run", boom)
    assert pv.code_version(tmp_path) == "uncommitted"


def test_code_version_uses_short_hash_at_project_root(tmp_path, monkeypatch):
    """rev-parse --show-toplevel equals the project root -> the --short HEAD hash is returned."""
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if args[:2] == ["git", "rev-parse"] and "--show-toplevel" in args:
            return subprocess.CompletedProcess(args, 0, stdout=f"{tmp_path.resolve()}\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="abc1234\n", stderr="")

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    assert pv.code_version(tmp_path) == "abc1234"
    assert ["git", "rev-parse", "--short", "HEAD"] in calls


def test_code_version_rejects_parent_repository(tmp_path, monkeypatch):
    """A parent repository (toplevel differs from the project root) must not stamp this project."""

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="C:/Users/somebody\n", stderr="")

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    assert pv.code_version(tmp_path) == "uncommitted"


def test_missing_input_raises(config_and_input, tmp_path):
    """A missing input file raises FileNotFoundError (no null sha256)."""
    config, _ = config_and_input
    with pytest.raises(FileNotFoundError):
        pv.build_provenance("measure", config, [{"source_id": "x", "path": str(tmp_path / "nope.bin")}])


def test_invalid_stage_rejected(config_and_input):
    """Stage must be a lowercase snake_case id."""
    config, _ = config_and_input
    with pytest.raises(ValueError):
        pv.build_provenance("Measure Stage", config, [])
