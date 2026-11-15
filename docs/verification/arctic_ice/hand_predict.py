"""Hand prediction (independent of the pipelines) of the Earth-gap figures after the Arctic integration.
Inputs: the new pool index (accepted = excluded is null), NASADEM pool measures (data/derived/measure, from the
backup so nothing new is read), Arctic measures (arctic_probe/measures.json), Mars cells and targets (query tables of
the backup), sigma (config/measure.json), thresholds (query 'threshold' column). D = ||dz|| / sqrt(3)."""
import json
from pathlib import Path

import numpy as np

R = Path(r"C:\SpaceApps2026_Hackathon")
B = R / "_backup_pre_arctic"
F = ["slope_p95_deg", "hi", "hurst"]
sig = json.loads((R / "config/measure.json").read_text(encoding="utf-8"))["features"]
s = np.array([sig[f]["sigma"] for f in F])

idx = json.loads((R / "data/raw/earth/pool/index.json").read_text(encoding="utf-8"))
rows = idx if isinstance(idx, list) else idx.get("windows") or next(v for v in idx.values() if isinstance(v, list))
acc = [r for r in rows if not r.get("excluded")]
print("index rows", len(rows), "accepted", len(acc),
      {b: sum(1 for r in acc if r.get("sensor", "nasadem") == b) for b in ("nasadem", "copdem")})

arc = json.loads((R / "data/derived/arctic_probe/measures.json").read_text(encoding="utf-8"))
arc = arc if isinstance(arc, list) else next(v for v in arc.values() if isinstance(v, list))
arcF = {r["id"]: r["features"] for r in arc if r.get("status") == "ok" and r.get("features")}

X, sens, ids = [], [], []
for r in acc:
    if r.get("sensor", "nasadem") == "nasadem":
        rec = json.loads((B / "data/derived/measure" / f"pool__{r['id']}.json").read_text(encoding="utf-8"))
        if rec.get("status") != "ok":
            continue
        f = rec["features"]
    else:
        f = arcF.get(r["probe_id"])
        if f is None:
            continue
    if any(f.get(k) is None for k in F):
        continue
    X.append([f[k] for k in F]); sens.append(r.get("sensor", "nasadem")); ids.append(r["id"])
X = np.array(X) / s
nas = np.array([x == "nasadem" for x in sens])
print("usable pool", len(ids), "nasadem", int(nas.sum()), "arctic", int((~nas).sum()))


def table(name):
    q = B / "site/data/query" / name
    col = lambda n: np.fromfile(q / f"{n}.f32", dtype="<f4").astype(float)
    codes = np.fromfile(q / "id.codes.u16", dtype="<u2")
    d = json.loads((q / "id.dict.json").read_text(encoding="utf-8"))
    d = d if isinstance(d, list) else d.get("values") or list(d)
    out = {"id": [d[c] for c in codes], "thr": col("threshold"), "gap_old": col("gap"),
           "Y": np.stack([col(k) for k in F], 1) / s}
    if (q / "body.codes.u16").exists():
        bc = np.fromfile(q / "body.codes.u16", dtype="<u2")
        bd = json.loads((q / "body.dict.json").read_text(encoding="utf-8"))
        bd = bd if isinstance(bd, list) else bd.get("values") or list(bd)
        out["body"] = [bd[c] for c in bc]
    return out


res = {}
for name in ("mars_cells", "targets"):
    t = table(name)
    ok = np.isfinite(t["thr"]) & np.isfinite(t["Y"]).all(1)
    Y = t["Y"][ok]
    D = np.sqrt(((Y[:, None, :] - X[None, :, :]) ** 2).sum(-1)) / np.sqrt(3)
    gap_all = D.min(1) > t["thr"][ok]
    gap_nas = D[:, nas].min(1) > t["thr"][ok]
    ids_ok = [i for i, k in zip(t["id"], ok) if k]
    res[name] = {"n": int(ok.sum()), "gap_old": int((t["gap_old"][ok] == 1).sum()),
                 "gap_nasadem": int(gap_nas.sum()), "gap_all": int(gap_all.sum())}
    if name == "targets":
        body = [b for b, k in zip(t["body"], ok) if k]
        moon = [i for i, b in enumerate(body) if b == "moon"]
        res[name]["moon_gap_nasadem"] = sorted(ids_ok[i] for i in moon if gap_nas[i])
        res[name]["moon_gap_all"] = sorted(ids_ok[i] for i in moon if gap_all[i])
        res[name]["moon_gap_old"] = sorted(ids_ok[i] for i in moon if t["gap_old"][ok][i] == 1)
    print(name, res[name])
(R / "docs/verification/arctic_ice").mkdir(parents=True, exist_ok=True)
Path(r"C:\Users\mario\AppData\Local\Temp\claude\e114aefffa4d8325\f506418e-46fc-4e4e-962d-8b02f1b6670c\scratchpad\hand_predict.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
