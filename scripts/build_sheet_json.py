"""Emit sheet_data.json for the hosted page. Read-only, no broker."""
import json, sys, statistics as st, collections
from datetime import datetime, timezone
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
# CANONICAL ORDER, consumed by the weekly view too. By avg rollover cost,
# descending: it is the only signal column both views share, and the only one
# that survived the split-sample forward test. Computed ONCE here so both
# sheets present sectors in an identical sequence -- if each sorted by its own
# period's value the orders would diverge and the views would stop scrolling
# together, which is the whole point.
sectors.sort(key=lambda s: -s["avgCost"])
for i, s in enumerate(sectors):
    s["order"] = i
out = {"expiry": cur, "prevExpiry": prev, "count": len(rows),
       "sectors": sectors,
       "generatedAt": datetime.now(timezone.utc).replace(microsecond=0)
       .isoformat().replace("+00:00", "Z")}
p = Path(__file__).resolve().parent.parent / "sheet_data.json"
p.write_text(json.dumps(out, separators=(",", ":")))
print(f"wrote {p.name}: {len(rows)} rows / {len(sectors)} sectors, expiry {cur}")
