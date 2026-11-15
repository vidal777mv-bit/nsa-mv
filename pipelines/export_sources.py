"""Export the source labels the site shows next to each datum: site/data/sources.json.

config/sources.json is the only source of truth for labels (short_label, is_nasa, mission_instrument, ...).
This script only reads it and the site data that cites sources; it writes one file:

  site/data/sources.json
    generated_by   "pipelines/export_sources.py"
    sources        {source_id: {short_label, is_nasa, agency, mission_instrument, body, url, citation,
                                licence_note, used}}
    by_url         {url: source_id}   every URL the site cites that maps to a source

Rules:
- url:      url_or_collection when it is an http(s) address, else page (STAC collections name no URL).
- by_url:   primary URLs first (url_or_collection and any alt_urls), then page; a secondary URL never
            overrides a primary one. A primary URL claimed by two sources is a config error.
- agency:   provider without the ", served by ..." hosting note.
- citation: agency, product, doi (if any) and url, joined by ". ".
- used:     true if the id is the source_id of a site/data/terrain/*/meta.json, or a URL of
            site/data/missions.json, bodies.json or targets.json maps to it, or the id is named by
            "globe_texture" and that file exists in site/assets/globes/.

Fails (exit 1, message on stderr, nothing written) if:
- a source_id used by site/data/terrain/*/meta.json has no entry in config/sources.json;
- a URL in site/data/missions.json (bodies.json, targets.json) is not in by_url;
- an entry lacks a required label field, or a primary URL is claimed twice.

Usage:
  .venv/Scripts/python.exe pipelines/export_sources.py     (writes site/data/sources.json, prints the counts)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("short_label", "is_nasa", "mission_instrument", "body", "provider", "license")
URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
SITE_JSON_WITH_URLS = ("missions.json", "bodies.json", "targets.json")


class ExportError(Exception):
    """A config or site-data problem that stops the export."""


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise ExportError(f"falta {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def iter_strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_strings(v)


def urls_in(obj: Any) -> list[str]:
    found: list[str] = []
    for text in iter_strings(obj):
        for m in URL_RE.findall(text):
            found.append(m.rstrip(".,;:"))
    return found


def is_http(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def primary_url(entry: dict[str, Any]) -> str | None:
    if is_http(entry.get("url_or_collection")):
        return entry["url_or_collection"]
    return entry.get("page") if is_http(entry.get("page")) else None


def build_by_url(sources: list[dict[str, Any]]) -> dict[str, str]:
    by_url: dict[str, str] = {}
    owner_of_primary: dict[str, str] = {}
    for e in sources:
        primaries = [primary_url(e)] + list(e.get("alt_urls", []))
        for url in filter(None, primaries):
            if url in owner_of_primary and owner_of_primary[url] != e["id"]:
                raise ExportError(f"URL primaria {url} en {owner_of_primary[url]} y en {e['id']}")
            owner_of_primary[url] = e["id"]
            by_url[url] = e["id"]
    for e in sources:
        if is_http(e.get("page")):
            by_url.setdefault(e["page"], e["id"])
    return by_url


def agency_of(entry: dict[str, Any]) -> str:
    return entry["provider"].split(", served by")[0].strip()


def citation_of(entry: dict[str, Any], url: str | None) -> str:
    doi = entry.get("doi")
    parts = [agency_of(entry), entry.get("product"), f"doi:{doi}" if doi else None, url]
    return ". ".join(p for p in parts if p)


def used_ids(root: Path, sources: list[dict[str, Any]], by_url: dict[str, str]) -> set[str]:
    ids = {e["id"] for e in sources}
    used: set[str] = set()

    for meta_path in sorted((root / "site" / "data" / "terrain").glob("*/meta.json")):
        sid = load_json(meta_path).get("source_id")
        if sid is None:
            continue
        if sid not in ids:
            raise ExportError(f"{meta_path.relative_to(root)} usa source_id '{sid}' sin entrada en config/sources.json")
        used.add(sid)

    for name in SITE_JSON_WITH_URLS:
        path = root / "site" / "data" / name
        for url in urls_in(load_json(path)):
            if url not in by_url:
                raise ExportError(f"URL de site/data/{name} sin entrada en by_url (config/sources.json): {url}")
            used.add(by_url[url])

    globes = root / "site" / "assets" / "globes"
    for e in sources:
        tex = e.get("globe_texture")
        if tex:
            if not (globes / tex).is_file():
                raise ExportError(f"textura de globo {tex} de {e['id']} no existe en site/assets/globes/")
            used.add(e["id"])
    return used


def build(root: Path = ROOT) -> dict[str, Any]:
    cfg = load_json(root / "config" / "sources.json")
    sources = cfg["sources"]
    for e in sources:
        missing = [k for k in REQUIRED if k not in e]
        if missing:
            raise ExportError(f"entrada {e.get('id')} sin campos {', '.join(missing)}")
    by_url = build_by_url(sources)
    used = used_ids(root, sources, by_url)

    out_sources: dict[str, Any] = {}
    for e in sources:
        url = primary_url(e)
        out_sources[e["id"]] = {
            "short_label": e["short_label"],
            "is_nasa": e["is_nasa"],
            "agency": agency_of(e),
            "mission_instrument": e["mission_instrument"],
            "body": e["body"],
            "url": url,
            "citation": citation_of(e, url),
            "licence_note": e["license"],
            # shown_in_site: referenced by a site data file (terrain, missions, bodies, targets, globe texture).
            # used: shown in the site OR used by the analysis (config 'used', e.g. Köppen context, Copernicus noise test).
            "shown_in_site": e["id"] in used,
            "used": e["id"] in used or bool(e.get("used")),
            "use": e.get("use"),
        }
    return {"generated_by": "pipelines/export_sources.py", "sources": out_sources, "by_url": by_url}


def write(out: dict[str, Any], root: Path = ROOT) -> Path:
    path = root / "site" / "data" / "sources.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = ROOT
    if "--root" in args:
        root = Path(args[args.index("--root") + 1])
    try:
        out = build(root)
    except ExportError as exc:
        print(f"export_sources: ERROR: {exc}", file=sys.stderr)
        return 1
    path = write(out, root)
    srcs = out["sources"].values()
    print(f"wrote {path}")
    print(f"sources: {len(out['sources'])}  is_nasa true: {sum(1 for s in srcs if s['is_nasa'] is True)}"
          f"  false: {sum(1 for s in srcs if s['is_nasa'] is False)}  used: {sum(1 for s in srcs if s['used'])}")
    print(f"by_url: {len(out['by_url'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
