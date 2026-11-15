"""Provenance block written into every JSON under data/derived (STANDARDS.md section 7).

Formula: config_sha256 = SHA-256 of the config file bytes; each input sha256 = SHA-256 of the file bytes;
code_version = output of `git rev-parse --short HEAD` run in the project root, or "uncommitted" when git is
unavailable, the project is not its own repository, or the command fails.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GENERATED_WITH = (
    "Code written with AI assistance (Claude, Anthropic) under the team's direction; "
    "data computed by this code from the listed sources."
)


def sha256_file(path: str | Path) -> str:
    """SHA-256 hex digest of a file's bytes.

    Formula: sha256(bytes(file)). Raises FileNotFoundError when the file does not exist.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_version(project_root: str | Path = PROJECT_ROOT) -> str:
    """Short git hash of HEAD for the project root, or 'uncommitted'.

    Formula: `git rev-parse --short HEAD`, accepted only when `git rev-parse --show-toplevel` is the
    project root itself (so a parent repository never stamps this project).
    """
    root = Path(project_root).resolve()
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True, timeout=20
        )
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
            return "uncommitted"
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return "uncommitted"
    if head.returncode != 0 or not head.stdout.strip():
        return "uncommitted"
    return head.stdout.strip()


def build_provenance(
    stage: str,
    config_path: str | Path,
    inputs: list[dict[str, str]],
) -> dict[str, object]:
    """Build the provenance block for one derived JSON.

    Formula: schema = "analog.<stage>/1"; created = current UTC time (ISO 8601, Z suffix);
    config_version and config_sha256 read from config_path; inputs = [{source_id, path, sha256}].
    ``inputs`` items need the keys ``source_id`` and ``path``. Raises FileNotFoundError when the config or an
    input file is missing (provenance must be exact; no null sha256).
    """
    if not stage or not stage.replace("_", "").isalnum() or stage != stage.lower():
        raise ValueError(f"stage {stage!r} must be a lowercase snake_case id")
    config_file = Path(config_path)
    config_bytes = config_file.read_bytes()
    config = json.loads(config_bytes)

    input_records: list[dict[str, str]] = []
    for item in inputs:
        path = Path(item["path"])
        input_records.append(
            {"source_id": str(item["source_id"]), "path": str(item["path"]), "sha256": sha256_file(path)}
        )

    return {
        "schema": f"analog.{stage}/1",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_version": str(config["version"]),
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "code_version": code_version(),
        "inputs": input_records,
        "generated_with": GENERATED_WITH,
    }
