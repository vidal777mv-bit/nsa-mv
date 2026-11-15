import json, glob, os, re

ROOT = r"C:\SpaceApps2026_Hackathon"
OUT_DIR = os.path.join(ROOT, "docs", "verification", "arctic_top10")

shares = json.load(open(os.path.join(ROOT, "data", "derived", "pool_rules", "shares.json"), encoding="utf-8"))["windows"]

rows = []
for path in sorted(glob.glob(os.path.join(ROOT, "site", "data", "rankings", "*.json"))):
    site = os.path.splitext(os.path.basename(path))[0]
    data = json.load(open(path, encoding="utf-8"))
    for r in data.get("ranking", []):
        if r.get("rank", 999) > 10:
            continue
        aid = r.get("analog_id", "")
        core = aid[len(site) + 2:] if aid.startswith(site + "__") else aid
        m = re.fullmatch(r"pool__pool_(\d{5})", core)
        if not m:
            continue
        n = int(m.group(1))
        if n <= 2000:
            continue
        key = "pool_" + m.group(1)
        sh = shares.get(key, {})
        place = (r.get("analog_place") or {}).get("name")
        rows.append({
            "site": site,
            "rank": r["rank"],
            "analog_id": aid,
            "pool_key": key,
            "D": r.get("D"),
            "analog_place": place,
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "ice_share": sh.get("ice_share"),
            "bare_share_full": sh.get("bare_share_full"),
            "greenland_name": bool(place and "greenland" in place.lower()),
        })

rows.sort(key=lambda x: (x["site"], x["rank"]))
json.dump(rows, open(os.path.join(OUT_DIR, "_list_stage.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("n_rows", len(rows))
for r in rows:
    print(r["site"], r["rank"], r["analog_id"], round(r["D"], 4) if r["D"] is not None else None, r["analog_place"], r["lat"], r["lon"], r["ice_share"], r["bare_share_full"])
