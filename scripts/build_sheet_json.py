"""Emit sheet_data.json for the hosted page. Read-only, no broker."""
import json, sys, statistics as st, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sheet import build

rows, cur, prev = build(out_csv=False)
by = collections.defaultdict(list)
for r in rows:
    by[r["sector"]].append(r)
sectors = []
for sec, grp in sorted(by.items()):
    sectors.append({
        "sector": sec, "count": len(grp),
        "avgMom":  round(st.mean(g["M_O_M"] for g in grp), 2),
        "avgRoll": round(st.mean(g["rollover"] for g in grp), 2),
        "avgCost": round(st.mean(g["rollover_cost"] for g in grp), 3),
        "rows": [{k: (round(v, 4) if isinstance(v, float) else v)
                  for k, v in g.items() if k != "sector"} for g in grp],
    })
sectors.sort(key=lambda s: -s["avgRoll"])
out = {"expiry": cur, "prevExpiry": prev, "count": len(rows),
       "sectors": sectors, "generatedAt": __import__("datetime").datetime.utcnow()
       .replace(microsecond=0).isoformat() + "Z"}
p = Path(__file__).resolve().parent.parent / "sheet_data.json"
p.write_text(json.dumps(out, separators=(",", ":")))
print(f"wrote {p.name}: {len(rows)} rows / {len(sectors)} sectors, expiry {cur}")
