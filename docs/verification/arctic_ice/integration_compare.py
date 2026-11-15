"""Arctic integration (2026-11-14): hand prediction vs engine, and before vs after.
Before = _backup_pre_arctic (single backup taken before the run). Hand = hand_predict_before_run.json (computed
before the engine ran, independent brute force). Engine = the ledger views and site/data after the run.
Writes integration_compare.md next to this file. Read-only on the project."""
import json
from pathlib import Path

import duckdb
import numpy as np

R = Path(__file__).resolve().parents[3]
B = R / "_backup_pre_arctic"
OUT = Path(__file__).with_name("integration_compare.md")
F = ["slope_p95_deg", "hi", "hurst"]

hand = json.loads(Path(__file__).with_name("hand_predict_before_run.json").read_text(encoding="utf-8"))
con = duckdb.connect(str(R / "data/derived/facts/facts.duckdb"), read_only=True)
v = lambda name: con.execute(f"SELECT value FROM {name}").fetchone()[0]
old_f = json.loads((B / "site/data/facts.json").read_text(encoding="utf-8"))["figures"]
new_f = json.loads((R / "site/data/facts.json").read_text(encoding="utf-8"))["figures"]
md = ["# Arctic integration: hand vs engine, before vs after (2026-11-14)", ""]

# 1. hand vs engine
md += ["## 1. Hand prediction (before the run) vs engine (after)", "", "| Figure | Hand | Engine | Match |", "| --- | --- | --- | --- |"]
moon_ids_engine = sorted(r[0] for r in con.execute(
    "SELECT subject_id FROM facts WHERE subject_type='target' AND property='earth_gap' AND value_num=1 AND body='moon'").fetchall())
moon_ids_nas = sorted(r[0] for r in con.execute(
    "SELECT subject_id FROM facts WHERE subject_type='target' AND property='earth_gap_nasadem' AND value_num=1 AND body='moon'").fetchall())
pairs = [
    ("Mars places without twin, NASADEM band only", hand["mars_cells"]["gap_nasadem"], v("mars_gap_cells_nasadem")),
    ("Mars places without twin, NASADEM + Arctic rock", hand["mars_cells"]["gap_all"], v("mars_gap_cells")),
    ("Moon sites without twin, NASADEM only", hand["targets"]["moon_gap_nasadem"], moon_ids_nas),
    ("Moon sites without twin, with Arctic rock", hand["targets"]["moon_gap_all"], moon_ids_engine),
]
for name, h, e in pairs:
    md.append(f"| {name} | {h} | {e} | {'yes' if h == e else '**NO**'} |")

# Arctic features: engine measure records vs the probe's own measurement
probe = json.loads((R / "data/derived/arctic_probe/measures.json").read_text(encoding="utf-8"))
probe = probe if isinstance(probe, list) else next(x for x in probe.values() if isinstance(x, list))
pf = {r["id"]: r.get("features") for r in probe}
idx = json.loads((R / "data/raw/earth/pool/index.json").read_text(encoding="utf-8"))
rows = idx if isinstance(idx, list) else idx.get("windows") or next(x for x in idx.values() if isinstance(x, list))
maxdiff, n = 0.0, 0
for r in rows:
    if r.get("sensor") != "copdem" or r.get("excluded"):
        continue
    rec = json.loads((R / "data/derived/measure" / f"pool__{r['id']}.json").read_text(encoding="utf-8"))
    a, b = rec["features"], pf[r["probe_id"]]
    maxdiff = max(maxdiff, max(abs(a[k] - b[k]) for k in F)); n += 1
md.append(f"| Arctic features, engine record vs probe measurement ({n} windows) | - | max abs diff {maxdiff:.2e} | {'yes' if maxdiff < 1e-9 else '**NO**'} |")

# 2. before vs after headline figures
md += ["", "## 2. Headline figures, before vs after", "", "| Figure | Before | After |", "| --- | --- | --- |"]
for k in ["earth_places_searched", "mars_gap_places", "mars_gap_pct", "mars_rehearsable_pct", "moon_gap_sites",
          "twin_places", "new_twin_places", "known_twin_places"]:
    md.append(f"| {k} | {old_f.get(k, {}).get('display', '-')} | {new_f.get(k, {}).get('display', '-')} |")
for k in ["earth_places_nasadem", "earth_places_arctic", "earth_places_excluded", "mars_gap_pct_nasadem", "moon_gap_sites_nasadem"]:
    md.append(f"| {k} (new) | - | {new_f.get(k, {}).get('display', '-')} |")

# 3. per site
md += ["", "## 3. Per site: the 10 Earth candidates, before vs after", "",
       "| Site | Same in top 10 | Arctic in top 10 | Top 1 before (D) | Top 1 after (D) | Tied with #1 before -> after |",
       "| --- | --- | --- | --- | --- | --- |"]
pid = lambda a: a[a.rfind("pool__pool_"):] if "pool__pool_" in a else a
old_t = json.loads((B / "site/data/ties.json").read_text(encoding="utf-8"))["targets"]
new_t = json.loads((R / "site/data/ties.json").read_text(encoding="utf-8"))["targets"]
sensor = {f"pool__{r['id']}": r.get("sensor", "nasadem") for r in rows}
for f in sorted((R / "site/data/rankings").glob("*.json")):
    tid = f.stem
    a = json.loads((B / "site/data/rankings" / f.name).read_text(encoding="utf-8"))["ranking"]
    b = json.loads(f.read_text(encoding="utf-8"))["ranking"]
    same = len({pid(x["analog_id"]) for x in a} & {pid(x["analog_id"]) for x in b})
    arctic = sum(1 for x in b if sensor.get(pid(x["analog_id"])) == "copdem")
    md.append(f"| {tid} | {same}/10 | {arctic} | {a[0]['analog_place']['name'] if a[0].get('analog_place') else pid(a[0]['analog_id'])} ({a[0]['D']:.3f}) | "
              f"{b[0]['analog_place']['name'] if b[0].get('analog_place') else pid(b[0]['analog_id'])} ({b[0]['D']:.3f}) | "
              f"{old_t[tid]['n_tied_with_first']} -> {new_t[tid]['n_tied_with_first']} |")

# 4. rehearsal counts
def counts(root):
    """Only the pairs of the CURRENT rankings of that root (stale files of earlier rankings are not counted)."""
    c = {}
    names = [f"{q.stem}__{x['analog_id']}.json" for q in (root / "site/data/rankings").glob("*.json")
             for x in json.loads(q.read_text(encoding="utf-8"))["ranking"]]
    for p in (root / "site/data/rehearsal" / n for n in names):
        for l in json.loads(p.read_text(encoding="utf-8"))["lines"]:
            key = f"{l['id']}:{l['status']}"
            c[key] = c.get(key, 0) + 1
    return c
cb, ca = counts(B), counts(R)
md += ["", "## 4. What can be rehearsed (160 pairs), before vs after", "", "| Line:status | Before | After |", "| --- | --- | --- |"]
for k in sorted(set(cb) | set(ca)):
    if cb.get(k) != ca.get(k):
        md.append(f"| {k} | {cb.get(k, 0)} | {ca.get(k, 0)} |")
OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
print("\n".join(md))
