"""Weekly sheet: the three steps at weekly cadence.

Step 2 CANNOT be weekly rollover -- there is one roll per series, so a weekly
rollover number would be fiction. Its weekly analogue is OI change: rollover
asks "did positions move to the next series", weekly OI asks "are positions
building or unwinding". Same question, weekly cadence.
"""
import collections, csv, json, statistics as st
from datetime import datetime, timezone
from pathlib import Path
from sectors import sector_map

ROOT = Path(__file__).resolve().parent
SNAP = ROOT / "data" / "weekly_snapshots.csv"


def build():
    rows = list(csv.DictReader(SNAP.open()))
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["symbol"]][r["asof"]] = r
    weeks = sorted({r["asof"] for r in rows})
    cur, prev = weeks[-1], weeks[-2]
    sm = sector_map()
    out = []
    for s, d in by.items():
        if cur not in d or prev not in d:
            continue
        a, b = d[cur], d[prev]
        sp, spb = float(a["spot"]), float(b["spot"])
        oi, oib = float(a["oi_total"]), float(b["oi_total"])
        if sp <= 0 or spb <= 0 or oib <= 0:
            continue
        out.append({
            "sector": sm.get(s, "(unclassified)"), "symbol": s, "spot": sp,
            "W_O_W": 100 * (sp - spb) / spb,
            "future_price": float(a["near_px"]), "basis": float(a["basis"]),
            "oi_total": oi, "oi_chg_pct": 100 * (oi - oib) / oib,
            "roll_so_far": float(a["rollover_so_far_pct"]),
            "cost": float(a["cost_pct"]),
            "cost_chg": float(a["cost_pct"]) - float(b["cost_pct"]),
            "near_expiry": a["near_expiry"],
        })
    # composite: price + OI build + cost change, cross-sectional z, equal weight
    def z(k):
        v = [r[k] for r in out]; m, sd = st.mean(v), (st.pstdev(v) or 1.0)
        return {r["symbol"]: (r[k] - m) / sd for r in out}
    zs = {k: z(k) for k in ("W_O_W", "oi_chg_pct", "cost_chg")}
    for r in out:
        r["score"] = sum(zs[k][r["symbol"]] for k in zs) / len(zs)
    out.sort(key=lambda r: (r["sector"], r["symbol"]))
    return out, cur, prev, weeks


def emit():
    rows, cur, prev, weeks = build()
    g = collections.defaultdict(list)
    for r in rows:
        g[r["sector"]].append(r)
    sectors = [{
        "sector": k, "count": len(v),
        "avgWow": round(st.mean(x["W_O_W"] for x in v), 2),
        "avgOiChg": round(st.mean(x["oi_chg_pct"] for x in v), 2),
        "avgCost": round(st.mean(x["cost"] for x in v), 3),
        "rows": [{kk: (round(vv, 4) if isinstance(vv, float) else vv)
                  for kk, vv in x.items() if kk != "sector"} for x in v],
    } for k, v in sorted(g.items())]
    # adopt the monthly sheet's canonical order so the two views scroll
    # together; fall back to own ranking only if it has not been built yet
    ref = ROOT / "sheet_data.json"
    if ref.exists():
        order = {x["sector"]: x.get("order", 999)
                 for x in json.loads(ref.read_text())["sectors"]}
        sectors.sort(key=lambda s: order.get(s["sector"], 999))
    else:
        sectors.sort(key=lambda s: -s["avgOiChg"])
    doc = {"asof": cur, "prevWeek": prev, "weeksAvailable": len(weeks),
           "count": len(rows), "sectors": sectors,
           "generatedAt": datetime.now(timezone.utc).replace(microsecond=0)
           .isoformat().replace("+00:00", "Z")}
    p = ROOT / "weekly_data.json"
    p.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"wrote {p.name}: {len(rows)} names, {len(sectors)} sectors, "
          f"week {cur} vs {prev} ({len(weeks)} weeks available)")


if __name__ == "__main__":
    emit()
