# -*- coding: utf-8 -*-
"""Verificacion independiente de estados del mapa (solo lectura).

Lee site/, config/ y data/ (no importa pipelines/ ni src/). Escribe solo en docs/verification/.
Definiciones: STANDARDS.md 10.13 (niebla), 10.14 (Earth gap), section 4 (features, D).
"""
import json
import math
import glob
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path("C:/SpaceApps2026_Hackathon")
OUT = ROOT / "docs/verification"
SEED = 20261114
Z = 1.96
K = 3
FEATS = ["slope_p95_deg", "hi", "hurst"]  # in-distance features (config/measure.json)
QDIR = ROOT / "site/data/query"
TILE_DIR = ROOT / "data/raw/earth/pool/_worldcover_coarse"


def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def wilson(k, n):
    if n == 0:
        return None
    p = k / n
    z2 = Z * Z
    centro = (p + z2 / (2 * n)) / (1 + z2 / n)
    margen = Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return [round(centro - margen, 4), round(centro + margen, 4)]


# ------------------------------------------------------------------ config
cfg = jload(ROOT / "config/measure.json")
SIG = np.array([cfg["features"][f]["sigma"] for f in FEATS], float)
FLAT_SLOPE = cfg["validation"]["v13"]["flat_slope_p95_deg"]  # 3.0
RUN = jload(ROOT / "data/derived/neighbors/run.json")
RUN_THR = RUN["thresholds"]


def relief(slope):
    return "rugged" if slope >= FLAT_SLOPE else "flat"


# ------------------------------------------------------------------ Earth pool (data/derived/neighbors)
pool_rows = pq.read_table(ROOT / "data/derived/neighbors/earth_windows.parquet").to_pylist()
POOL_BY_ID = {r["id"]: r for r in pool_rows}
POOL_ALL_IDS = [r["id"] for r in pool_rows]
pool_F = np.array([[np.nan if r[f] is None else r[f] for f in FEATS] for r in pool_rows], float)
pv = np.isfinite(pool_F).all(1)
P_IDS = [i for i, ok in zip(POOL_ALL_IDS, pv) if ok]
P_Z = pool_F[pv] / SIG


def nearest(F):
    """Fuerza bruta: D = sqrt(sum((z_a-z_b)^2)/K), z = x/sigma, contra el pool valido."""
    Zq = np.asarray(F, float) / SIG
    n = len(Zq)
    d = np.empty(n)
    idx = np.empty(n, int)
    for s in range(0, n, 128):
        diff = Zq[s:s + 128, None, :] - P_Z[None, :, :]
        D = np.sqrt((diff ** 2).sum(-1) / K)
        j = D.argmin(1)
        idx[s:s + 128] = j
        d[s:s + 128] = D[np.arange(len(j)), j]
    return d, idx


# ------------------------------------------------------------------ umbral: dev NASADEM vs Copernicus
dev_pairs = []
for fn in sorted(glob.glob(str(ROOT / "data/derived/measure/*__nasadem.json"))):
    nj = jload(fn)
    if nj.get("role") != "dev" or nj.get("status") != "ok":
        continue
    cp = fn.replace("__nasadem.json", "__copdem.json")
    if not os.path.exists(cp):
        continue
    cj = jload(cp)
    if cj.get("status") != "ok":
        continue
    a = np.array([nj["features"][f] for f in FEATS], float)
    b = np.array([cj["features"][f] for f in FEATS], float)
    D = math.sqrt(float((((a - b) / SIG) ** 2).sum()) / K)
    dev_pairs.append({"region": nj["region_id"], "relief": relief(nj["features"]["slope_p95_deg"]),
                      "slope_p95_nasadem": nj["features"]["slope_p95_deg"], "D": D})
THR = {}
for c in ["rugged", "flat"]:
    v = [x["D"] for x in dev_pairs if x["relief"] == c]
    THR[c] = float(np.percentile(v, 95)) if v else None
THR_CHECK = {c: {"recomputed": THR[c], "run_json": RUN_THR[c],
                 "abs_diff": abs(THR[c] - RUN_THR[c]) if THR[c] is not None else None,
                 "n_dev_pairs": sum(1 for x in dev_pairs if x["relief"] == c)} for c in ["rugged", "flat"]}

# ------------------------------------------------------------------ query export helpers
def q_ids(table):
    codes = np.fromfile(QDIR / table / "id.codes.u16", dtype="<u2")
    dic = jload(QDIR / table / "id.dict.json")
    return [None if c == 65535 else dic[c] for c in codes]


def q_f32(table, col):
    return np.fromfile(QDIR / table / f"{col}.f32", dtype="<f4")


# ------------------------------------------------------------------ Mars atlas cells
atlas = jload(ROOT / "site/data/atlas/mars_cells.json")
A_ids = [c["id"] for c in atlas]
A_by_id = {c["id"]: c for c in atlas}
A_F = np.array([[c["features"][f] for f in FEATS] for c in atlas], float)
A_D, A_I = nearest(A_F)
A_relief = [relief(c["features"]["slope_p95_deg"]) for c in atlas]
A_gap = np.array([A_D[i] > THR[A_relief[i]] for i in range(len(atlas))])
A_gap_stored_thr = np.array([A_D[i] > RUN_THR[A_relief[i]] for i in range(len(atlas))])

mpq = {r["id"]: r for r in pq.read_table(ROOT / "data/derived/neighbors/mars_cells.parquet").to_pylist()}
qm_ids = q_ids("mars_cells")
qm_gap = q_f32("mars_cells", "gap")
QM_GAP = {i: (None if np.isnan(v) else int(v)) for i, v in zip(qm_ids, qm_gap)}
# consistencia de features atlas vs parquet
feat_diff = max(abs(A_by_id[i]["features"][f] - mpq[i][f]) for i in A_ids for f in FEATS)

# ------------------------------------------------------------------ targets (16)
tj = jload(ROOT / "site/data/targets.json")["targets"]
tq_ids = q_ids("targets")
tq_gap = q_f32("targets", "gap")
TQ_GAP = {i: (None if np.isnan(v) else int(v)) for i, v in zip(tq_ids, tq_gap)}
tpq = {r["id"]: r for r in pq.read_table(ROOT / "data/derived/neighbors/targets.parquet").to_pylist()}
T_REC = {}
for t in tj:
    m = jload(ROOT / f"data/derived/measure/{t['id']}.json")
    F = np.array([[m["features"][f] for f in FEATS]], float)
    d, i = nearest(F)
    rel = relief(m["features"]["slope_p95_deg"])
    T_REC[t["id"]] = {"body": t["body"], "mission": t["mission"], "unlocked": t["unlocked"],
                      "relief": rel, "D": float(d[0]), "twin_id": P_IDS[int(i[0])],
                      "gap": bool(d[0] > THR[rel]), "features": m["features"]}

# ------------------------------------------------------------------ Mars coverage (fog) + CTX bboxes
covM = jload(ROOT / "site/data/coverage/mars.json")
GM = np.array(covM["grid"], int).reshape(covM["height"], covM["width"])
covE = jload(ROOT / "site/data/coverage/earth.json")
GE = np.array(covE["grid"], int).reshape(covE["height"], covE["width"])
covM_classes = covM["classes"]
covE_classes = covE["classes"]


def cell_rc(lat, lon):
    r = min(179, max(0, math.floor(90 - lat)))
    c = min(359, max(0, math.floor(lon + 180)))
    return r, c


C2M = defaultdict(list)
for cid in A_ids:
    C2M[cell_rc(A_by_id[cid]["lat"], A_by_id[cid]["lon"])].append(cid)
for t in tj:
    if t["body"] == "mars":
        C2M[cell_rc(t["lat"], t["lon"])].append(t["id"])
grid_m2 = set(map(tuple, np.argwhere(GM == 2).tolist()))
C2M_MATCH = set(C2M.keys()) == grid_m2

prods = jload(ROOT / "config/mars_coverage.json")["products"]
PB = np.array([p["bbox"] for p in prods], float)  # [minlon, minlat, maxlon, maxlat]
PID = [p["id"] for p in prods]
PFULL = (PB[:, 2] - PB[:, 0]) >= 359  # bboxes de ancho 360: dos tiras de 2 grados junto a +/-180


def ctx_hits_centre(clat, clon):
    lat_ok = (PB[:, 1] <= clat) & (clat <= PB[:, 3])
    lon_ok = np.where(PFULL, (clon <= -178) | (clon >= 178), (PB[:, 0] <= clon) & (clon <= PB[:, 2]))
    return np.nonzero(lat_ok & lon_ok)[0]


def ctx_overlaps_cell(r, c):
    la, la2 = 90 - r - 1, 90 - r
    lo, lo2 = -180 + c, -180 + c + 1
    lat_ok = (PB[:, 1] < la2) & (PB[:, 3] > la)
    lon_ok = np.where(PFULL, (lo < -178) | (lo2 > 178), (PB[:, 0] < lo2) & (PB[:, 2] > lo))
    return np.nonzero(lat_ok & lon_ok)[0]


def mars_cov_record(r, c):
    clat, clon = 90 - r - 0.5, -180 + c + 0.5
    stored = int(GM[r, c])
    measured = (r, c) in C2M
    hits = ctx_hits_centre(clat, clon)
    if measured:
        rec = 2
    elif len(hits):
        rec = 1
    else:
        rec = 0
    ov = ctx_overlaps_cell(r, c)
    alt = 2 if measured else (1 if len(ov) else 0)
    return {"cell": f"r{r:03d}c{c:03d}", "lat_centre": clat, "lon_centre": clon,
            "stored_class": stored, "recomputed_class": rec, "match": rec == stored,
            "measured_window_in_cell": measured, "measured_ids": C2M.get((r, c), []),
            "ctx_bbox_covers_centre": len(hits) > 0, "ctx_product_example": PID[hits[0]] if len(hits) else None,
            "n_ctx_centre": int(len(hits)), "alt_rule_overlap_class": alt,
            "alt_rule_match": alt == stored}


# ------------------------------------------------------------------ Earth coverage (fog) + WorldCover cache
C2E = set(cell_rc(r["lat"], r["lon"]) for r in pool_rows)
grid_e2 = set(map(tuple, np.argwhere(GE == 2).tolist()))
C2E_MATCH = C2E == grid_e2
TILE_FILES = set(os.listdir(TILE_DIR)) if TILE_DIR.exists() else set()


def tile_name(lat0, lon0):
    ns = "N" if lat0 >= 0 else "S"
    ew = "E" if lon0 >= 0 else "W"
    return f"ESA_WorldCover_10m_2021_v200_{ns}{abs(lat0):02d}{ew}{abs(lon0):03d}.npy"


_tile_cache = {}


def tile_arr(lat0, lon0):
    name = tile_name(lat0, lon0)
    if name not in TILE_FILES:
        return None
    if name not in _tile_cache:
        _tile_cache[name] = np.load(TILE_DIR / name)
    return _tile_cache[name]


def cell_share(la, lo, orient="N"):
    """Share de la celda 1x1 (SW corner la, lo) en el tile 3x3 cacheado (bool 300x300)."""
    lat0 = math.floor(la / 3.0) * 3
    lon0 = math.floor(lo / 3.0) * 3
    a = tile_arr(lat0, lon0)
    if a is None:
        return None
    c0 = int(round((lo - lon0) * 100))
    if orient == "N":  # fila 0 = borde norte
        r0 = int(round((lat0 + 2 - la) * 100))
    else:  # fila 0 = borde sur
        r0 = int(round((la - lat0) * 100))
    blk = a[r0:r0 + 100, c0:c0 + 100]
    return float(blk.mean()) if blk.size else None


# prueba de orientacion del cache contra worldcover_share del indice del pool
pidx = jload(ROOT / "data/raw/earth/pool/index.json")
pwins = pidx["windows"] if isinstance(pidx, dict) else pidx
xs, sN, sS = [], [], []
for w in pwins:
    if w.get("worldcover_share") is None:
        continue
    la, lo = math.floor(w["lat"]), math.floor(w["lon"])
    a1, a2 = cell_share(la, lo, "N"), cell_share(la, lo, "S")
    if a1 is None or a2 is None:
        continue
    xs.append(w["worldcover_share"]); sN.append(a1); sS.append(a2)
corr_N = float(np.corrcoef(xs, sN)[0, 1]) if len(xs) > 2 else None
corr_S = float(np.corrcoef(xs, sS)[0, 1]) if len(xs) > 2 else None
ORIENT = "N" if (corr_N or -9) >= (corr_S or -9) else "S"
ORIENT_INFO = {"n_pairs": len(xs), "corr_north_up": corr_N, "corr_south_up": corr_S, "chosen": ORIENT}


# ------------------------------------------------------------------ Luna (Moon) Artemis census
ARTEMIS = [t["id"] for t in tj if t["body"] == "moon" and "Artemis" in (t.get("mission") or "")]

# ------------------------------------------------------------------ muestra (semilla fija, orden fijo)
rng = np.random.default_rng(SEED)
records = {"mars_cov": [], "earth_cov": [], "mars_gap": [], "moon_artemis": []}
strata = []  # (name, list of records with 'pass' key, n_expected)

for s in [2, 1, 0]:
    idxs = np.flatnonzero(GM.ravel() == s)
    pick = sorted(rng.choice(idxs, size=8, replace=False).tolist())
    recs = []
    for i in pick:
        rec = mars_cov_record(i // 360, i % 360)
        rec["stratum"] = f"mars_cov_{s}_{covM_classes[str(s)]}"
        rec["pass"] = rec["match"]
        recs.append(rec)
    records["mars_cov"].extend(recs)

for s in [2, 1, 0]:
    idxs = np.flatnonzero(GE.ravel() == s)
    pick = sorted(rng.choice(idxs, size=8, replace=False).tolist())
    for i in pick:
        r, c = i // 360, i % 360
        la, lo = 90 - r - 1, -180 + c
        measured = (r, c) in C2E
        sh = cell_share(la, lo, ORIENT)
        if measured:
            rec_cls = 2
        elif sh is not None and sh >= 0.8:
            rec_cls = 1
        else:
            rec_cls = 0
        n_win = sum(1 for x in pool_rows if cell_rc(x["lat"], x["lon"]) == (r, c))
        records["earth_cov"].append({
            "cell": f"r{r:03d}c{c:03d}", "lat_sw": la, "lon_sw": lo, "stored_class": int(GE[r, c]),
            "recomputed_class": rec_cls, "match": rec_cls == int(GE[r, c]), "stratum": f"earth_cov_{s}_{covE_classes[str(s)]}",
            "pool_windows_in_cell": n_win, "worldcover_share_cell": sh, "tile_cached": sh is not None,
            "pass": rec_cls == int(GE[r, c])})

# Earth gap: 8 con gap almacenado + 8 sin gap (estratificado por el gap guardado en el parquet)
gap_idx = [k for k, cid in enumerate(A_ids) if mpq[cid]["gap"] is True or mpq[cid]["gap"] == 1]
nogap_idx = [k for k, cid in enumerate(A_ids) if not (mpq[cid]["gap"] is True or mpq[cid]["gap"] == 1)]
for label, pool_idx in [("gap1", gap_idx), ("gap0", nogap_idx)]:
    pick = sorted(rng.choice(pool_idx, size=8, replace=False).tolist())
    for k in pick:
        cid = A_ids[k]
        dstored = float(mpq[cid]["d_nearest"])
        gap_rec = bool(A_gap[k])
        gap_stored = bool(mpq[cid]["gap"])
        gap_export = QM_GAP.get(cid)
        d_match = abs(float(A_D[k]) - dstored) < 1e-9
        twin_match = P_IDS[int(A_I[k])] == A_by_id[cid]["twins"][0]["analog_id"]
        ok = (gap_rec == gap_stored) and (gap_export == int(gap_stored)) and d_match
        records["mars_gap"].append({
            "stratum": f"earth_gap_mars_{label}", "id": cid, "relief": A_relief[k],
            "D_recomputed": float(A_D[k]), "threshold_recomputed": THR[A_relief[k]],
            "gap_recomputed": gap_rec, "gap_stored_parquet": gap_stored, "gap_stored_export": gap_export,
            "D_stored_parquet": dstored, "D_match": d_match,
            "nearest_recomputed": P_IDS[int(A_I[k])], "nearest_atlas_twin1": A_by_id[cid]["twins"][0]["analog_id"],
            "twin1_match": twin_match, "pass": ok})

for cid in ARTEMIS:
    tr = T_REC[cid]
    stored = tpq[cid]
    gap_stored = bool(stored["gap"])
    ex = TQ_GAP.get(cid)
    ok = (tr["gap"] == gap_stored) and (ex == int(gap_stored)) and abs(tr["D"] - float(stored["d_nearest"])) < 1e-9
    records["moon_artemis"].append({
        "stratum": "moon_artemis_census", "id": cid, "relief": tr["relief"],
        "D_recomputed": tr["D"], "gap_recomputed": tr["gap"], "gap_stored_parquet": gap_stored,
        "gap_stored_export": ex, "D_stored_parquet": float(stored["d_nearest"]),
        "sin_gemelo_recomputed": tr["gap"], "pass": ok})

# ------------------------------------------------------------------ estratos
def stratum_stats(recs, name):
    n = len(recs)
    k = sum(1 for r in recs if r["pass"])
    p = k / n if n else None
    return {"estrato": name, "n": n, "aciertos": k, "tasa": round(p, 4) if p is not None else None,
            "wilson95": wilson(k, n)}


names = {}
for r in records["mars_cov"]:
    names.setdefault(r["stratum"], []).append(r)
for r in records["earth_cov"]:
    names.setdefault(r["stratum"], []).append(r)
for r in records["mars_gap"]:
    names.setdefault(r["stratum"], []).append(r)
names["moon_artemis_census"] = records["moon_artemis"]
STRATA = [stratum_stats(v, k) for k, v in names.items()]
STRATA_ALL_SAMPLE = {"n": sum(s["n"] for s in STRATA if s["estrato"] != "moon_artemis_census"),
                     "aciertos": sum(s["aciertos"] for s in STRATA if s["estrato"] != "moon_artemis_census")}

# ------------------------------------------------------------------ discrepancias (muestra)
DISC = []
for group in ["mars_cov", "earth_cov", "mars_gap", "moon_artemis"]:
    for r in records[group]:
        if not r["pass"]:
            DISC.append({"group": group, **{k: v for k, v in r.items() if k not in ("lat_centre", "lon_centre")}})

# ------------------------------------------------------------------ portada: recuentos
# A1 16 sitios medidos
n_targets = len(tj)
n_unlocked = sum(1 for t in tj if t["unlocked"])
# A2 2,000 lugares
val = jload(ROOT / "site/data/validation.json")
val_npool = val["v1.2"]["V0"]["n_pool"]
n_pool_rows = len(pool_rows)
n_pool_index = len(pwins)
# A3 1,838 celdas Marte
disc = jload(ROOT / "site/data/discoveries.json")
n_atlas = len(atlas)
n_mars_pq = len(mpq)
# A4/A5 nuevos / conocidos: recomputo desde ventanas (top-3 de atlas y de los 16 objetivos)
kr = jload(ROOT / "config/known_analog_regions.json")["regions"]
def pool_key_of(aid):
    return aid if aid.startswith("pool__") else "pool__" + aid.split("__pool__", 1)[1]


# Regla de discoveries.json: clave = analog_id tal como aparece (ventanas de objetivos llevan prefijo y
# coordenadas refinadas del ranking; ventanas de celdas Marte usan la coordenada del pool).
WIN = {}
for c in atlas:
    for tw in c["twins"][:3]:
        pid_ = tw["analog_id"]
        WIN[pid_] = (POOL_BY_ID[pid_]["lat"], POOL_BY_ID[pid_]["lon"], pid_)
for t in tj:
    rk = jload(ROOT / f"site/data/rankings/{t['id']}.json")["ranking"]
    for row in rk[:3]:
        WIN.setdefault(row["analog_id"], (row["lat"], row["lon"], pool_key_of(row["analog_id"])))
top3_ok = list(WIN.keys())
PHYS_IDS = set(v[2] for v in WIN.values())
# variante: una vez por ventana fisica del pool (sin contar desplazamientos refinados por separado)
PHYS_COUNT = sum(1 for pid_ in PHYS_IDS)
REFINED_MOVED = sum(1 for k, v in WIN.items() if k != v[2] and abs(v[0] - POOL_BY_ID[v[2]]["lat"]) + abs(v[1] - POOL_BY_ID[v[2]]["lon"]) > 1e-6)


def hav(lat1, lon1, lat2, lon2):
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def known_of(lat, lon):
    for reg in kr:
        if hav(lat, lon, reg["lat"], reg["lon"]) <= reg["radius_km"]:
            return reg["id"]
    return None


new_c = known_c = 0
nov_mismatch = []
disc_ids = {w["analog_id"]: w for w in disc["windows"]}
for aid, (la_, lo_, _pid) in WIN.items():
    kid = known_of(la_, lo_)
    nov = "known_region" if kid else "new"
    if nov == "new":
        new_c += 1
    else:
        known_c += 1
    if aid in disc_ids and disc_ids[aid]["novelty"] != nov:
        nov_mismatch.append({"id": aid, "file": disc_ids[aid]["novelty"], "recomputed": nov})
set_match = set(top3_ok) == set(disc_ids.keys())
phys_new = sum(1 for pid_ in PHYS_IDS if known_of(POOL_BY_ID[pid_]["lat"], POOL_BY_ID[pid_]["lon"]) is None)
phys_known = len(PHYS_IDS) - phys_new
# A6 88.5 / 11.5 (gap de Marte)
n_gap_full = int(A_gap.sum())
n_gap_thr_stored = int(A_gap_stored_thr.sum())
gap_full_parquet = sum(1 for cid in A_ids if mpq[cid]["gap"] in (True, 1))
gap_full_export = sum(1 for cid in A_ids if QM_GAP.get(cid) == 1)
# A7 Luna
n_artemis_gap = sum(1 for cid in ARTEMIS if T_REC[cid]["gap"])
n_targets_gap = sum(1 for cid in T_REC if T_REC[cid]["gap"])
# A8/A9 contorno y sin tocar (sombreado por cos(lat), como coverageShares en app.js)
rows = np.arange(covE["height"])
w = np.cos(np.radians(90 - rows - 0.5))
tot = float((w[:, None] * np.ones((1, covE["width"]))).sum())
share = {k: 100 * float((w[:, None] * (GE == k)).sum()) / tot for k in [0, 1, 2]}
rowsM = np.arange(covM["height"])
wM = np.cos(np.radians(90 - rowsM - 0.5))
totM = float((wM[:, None] * np.ones((1, covM["width"]))).sum())
shareM = {k: 100 * float((wM[:, None] * (GM == k)).sum()) / totM for k in [0, 1, 2]}
cells_mars_2 = int((GM == 2).sum())
cells_mars_centres = len(C2M)

PORTADA = [
    {"cifra": "16 sitios medidos", "mostrado": 16, "fuente_mostrado": "site/data/targets.json (unlocked)",
     "recontado": n_unlocked, "detalle": f"targets.json tiene {n_targets} entradas", "ok": n_unlocked == 16 and n_targets == 16},
    {"cifra": "2,000 lugares de la Tierra", "mostrado": val_npool,
     "fuente_mostrado": "site/data/validation.json v1.2.V0.n_pool",
     "recontado": n_pool_rows, "detalle": f"filas data/derived/neighbors/earth_windows.parquet; indice pool index.json = {n_pool_index}",
     "ok": n_pool_rows == 2000 and val_npool == 2000},
    {"cifra": "1,838 celdas de Marte desbloqueadas", "mostrado": disc["from"]["mars_cells"],
     "fuente_mostrado": "site/data/discoveries.json from.mars_cells",
     "recontado": n_atlas, "detalle": f"site/data/atlas/mars_cells.json = {n_atlas}; mars_cells.parquet = {n_mars_pq}. "
     f"OJO: son ventanas; coverage/mars.json cuenta {cells_mars_2} celdas de 1 grado en clase 2 "
     f"({sum(len(v) for v in C2M.values())} centros medidos = 1838 + 6 objetivos de Marte, en {cells_mars_centres} celdas)",
     "ok": n_atlas == 1838 and disc["from"]["mars_cells"] == 1838},
    {"cifra": "1,276 gemelos nuevos", "mostrado": disc["counts"]["new"], "fuente_mostrado": "site/data/discoveries.json counts.new",
     "recontado": new_c, "detalle": f"regla del archivo (clave = analog_id): {len(top3_ok)} ventanas (archivo {disc['counts']['unique_windows']}); "
     f"mismatch de conjunto: {not set_match}; mismatch de novedad: {len(nov_mismatch)}. "
     f"Variante por ventana fisica del pool: {len(PHYS_IDS)} unicas, nuevas={phys_new}, conocidas={phys_known}; "
     f"{REFINED_MOVED} entradas de objetivos con coordenada refinada distinta del pool",
     "ok": new_c == disc["counts"]["new"] and set_match and not nov_mismatch},
    {"cifra": "71 conocidos", "mostrado": disc["counts"]["known_region"], "fuente_mostrado": "site/data/discoveries.json counts.known_region",
     "recontado": known_c, "detalle": "dentro de circulo de config/known_analog_regions.json (regla del archivo)",
     "ok": known_c == disc["counts"]["known_region"]},
    {"cifra": "Tierra puede ensayar 88.5% de Marte medido (211/1838)", "mostrado": "88.5% / 11.5% (211/1838)",
     "fuente_mostrado": "data/derived/neighbors/run.json mars_cells.gap=211; query mars_cells gap.f32",
     "recontado": f"gap={n_gap_full}/{n_atlas} = {100 * n_gap_full / n_atlas:.2f}%; ensaya={100 * (n_atlas - n_gap_full) / n_atlas:.2f}%; "
                  f"gap parquet={gap_full_parquet}; gap export={gap_full_export}; con umbral run.json={n_gap_thr_stored}",
     "ok": n_gap_full == 211 and round(100 * (n_atlas - n_gap_full) / n_atlas, 1) == 88.5},
    {"cifra": "Luna: 3 de 7 sitios Artemis sin gemelo", "mostrado": 3,
     "fuente_mostrado": "run.json targets.gap (16 objetivos, 3 con gap)",
     "recontado": f"{n_artemis_gap} de {len(ARTEMIS)} Artemis; {n_targets_gap} de 16 objetivos con gap",
     "ok": n_artemis_gap == 3 and len(ARTEMIS) == 7},
    {"cifra": "Tierra contorno 0.9% de la esfera", "mostrado": 0.9,
     "fuente_mostrado": "site/data/coverage/earth.json clase 1 (area por cos(lat), como app.js)",
     "recontado": round(share[1], 2), "detalle": f"clase 1 = {int((GE == 1).sum())} celdas",
     "ok": round(share[1], 1) == 0.9},
    {"cifra": "Tierra sin tocar 96.0%", "mostrado": 96.0,
     "fuente_mostrado": "site/data/coverage/earth.json clase 0 (area por cos(lat))",
     "recontado": round(share[0], 2), "detalle": f"clase 0 = {int((GE == 0).sum())} celdas; clase 2 share = {share[2]:.2f}%",
     "ok": round(share[0], 1) == 96.0},
]
# Marte: sombreado de coverage (info, no es cifra de portada)
MARS_SHARE = {"unlocked": round(shareM[2], 2), "to_discover": round(shareM[1], 2), "fog": round(shareM[0], 2)}

# ------------------------------------------------------------------ salida
result = {
    "schema": "docs.verification.map_states/1",
    "seed": SEED,
    "design": {
        "mars_cov": "8 celdas por clase de site/data/coverage/mars.json (0,1,2), muestreo sin reemplazo con rng(20261114), orden 2,1,0 no; orden de estratos: mars 0,1,2 / earth 0,1,2 / gap1 / gap0",
        "earth_cov": "8 celdas por clase de site/data/coverage/earth.json",
        "mars_gap": "8 celdas gap=1 + 8 gap=0 (estrato por gap guardado en data/derived/neighbors/mars_cells.parquet), D por fuerza bruta contra 1994 ventanas validas del pool",
        "moon_artemis": "censo: los 7 objetivos con mission 'Artemis III (candidate region)'",
    },
    "definitions": {
        "niebla_STANDARDS_10_13": "2 = centro de ventana medida cae en la celda; 1 = bbox CTX DTM cubre la celda (Marte: centro dentro del bbox, regla de config/mars_coverage.json); 0 = resto. Luna: 1 solo 80S-90S; Tierra: 1 si share WorldCover >=0.8 (cache de tiles); 0 sin tile.",
        "earth_gap_STANDARDS_10_14": "gap = D_nearest > umbral(clase de relieve); D = sqrt(sum_k((x_a-x_b)/sigma_k)^2 / K), K=3, features slope_p95_deg, hi, hurst; relieve rugged si slope_p95 >= 3 deg",
        "celda_1grado": "fila r = floor(90-lat) (0..179), columna c = floor(lon+180) (0..359); centro (90-r-0.5, -180+c+0.5)",
    },
    "orientation_worldcover_cache": ORIENT_INFO,
    "umbral": {"dev_pairs": dev_pairs, "recomputed": THR, "check": THR_CHECK},
    "feature_consistency_atlas_vs_parquet_max_abs_diff": feat_diff,
    "grid_class2_set_equality": {"mars": C2M_MATCH, "earth": C2E_MATCH},
    "portada": PORTADA,
    "mars_coverage_shares_pct": MARS_SHARE,
    "strata": STRATA,
    "strata_sample_total": STRATA_ALL_SAMPLE,
    "records": records,
    "discrepancies_sample": DISC,
    "novelty_mismatch": nov_mismatch,
    "artemis_ids": ARTEMIS,
    "targets_gap_recomputed": {k: v["gap"] for k, v in T_REC.items()},
}


def conv(o):
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(str(type(o)))


OUT.mkdir(parents=True, exist_ok=True)
with open(OUT / "map_states.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1, default=conv)

print("umbral", THR, THR_CHECK)
print("orient", ORIENT_INFO)
print("C2 sets", C2M_MATCH, C2E_MATCH, "feat diff", feat_diff)
for p in PORTADA:
    print(p["cifra"], "|", p["mostrado"], "|", p["recontado"], "|", p["ok"])
for s in STRATA:
    print(s)
print("DISC", len(DISC))
for d in DISC:
    print({k: d[k] for k in d if k in ("group", "id", "cell", "stratum", "stored_class", "recomputed_class", "gap_stored_parquet", "gap_recomputed", "D_match", "gap_stored_export")})
print("novelty mismatch", nov_mismatch[:5])
print("artemis", [(c, T_REC[c]["gap"], round(T_REC[c]["D"], 4), T_REC[c]["relief"]) for c in ARTEMIS])
