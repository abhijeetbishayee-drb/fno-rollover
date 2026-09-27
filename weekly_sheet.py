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
PCRW = ROOT / "data" / "pcr_weekly.csv"
HIST = 26          # sparkline points; the full weekly series
MOM_WEEKS = 4      # weekly grid, so "a month ago" is 4 snapshots back


def pcr_weekly():
    """asof -> {symbol: (pcr, ce, pe)}, from the committed weekly PCR series.

    Read-only and tolerant of absence: the weekly sheet predates PCR and must
    still build without it. Missing is not zero -- a row simply gets no `pcr`.
    """
    out = collections.defaultdict(dict)
    if not PCRW.exists():
        return out
    for r in csv.DictReader(PCRW.open()):
        out[r["asof"]][r["symbol"]] = (float(r["pcr"]), int(float(r["ce"])),
                                       int(float(r["pe"])))
    return out


def attach_pcr(out, weeks, cur):
    """Add a `pcr` object per row. WOW is against the previous snapshot and MOM
    against four back -- both TIME comparisons on the weekly grid, matching the
    monthly sheet's definitions rather than the Nifty tracker's expiry pair,
    because stock options have no weekly expiry to compare against."""
    pw = pcr_weekly()
    if not pw:
        return []
    i = weeks.index(cur)
    prev_w = weeks[i - 1] if i >= 1 else None
    prev_m = weeks[i - MOM_WEEKS] if i >= MOM_WEEKS else None
    past = weeks[max(0, i - HIST + 1):i + 1]
    now = pw.get(cur, {})
    for r in out:
        rec = now.get(r["symbol"])
        if not rec:
            continue
        val, ce, pe = rec
        p = {"pcr": round(val, 4), "ce": ce, "pe": pe}
        for label, wk in (("Wk", prev_w), ("Prev", prev_m)):
            got = pw.get(wk, {}).get(r["symbol"]) if wk else None
            if got:
                p["pcr" + label] = round(got[0], 4)
                p["wow" if label == "Wk" else "mom"] = round(val - got[0], 4)
        if prev_w:
            p["wkDate"] = prev_w
        series = [(pw.get(w, {}).get(r["symbol"]) or (None,))[0] for w in past]
        if sum(v is not None for v in series) > 1:
            p["hist"] = [round(v, 4) if v is not None else None for v in series]
        r["pcr"] = p
    return past


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
    past = attach_pcr(rows, weeks, cur)
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
           "pcrHist": past,
           "count": len(rows), "sectors": sectors,
           "generatedAt": datetime.now(timezone.utc).replace(microsecond=0)
           .isoformat().replace("+00:00", "Z")}
    p = ROOT / "weekly_data.json"
    p.write_text(json.dumps(doc, separators=(",", ":")))
    n = sum(1 for r in rows if "pcr" in r)
    print(f"wrote {p.name}: {len(rows)} names, {len(sectors)} sectors, "
          f"week {cur} vs {prev} ({len(weeks)} weeks available); "
          f"{n}/{len(rows)} rows with PCR")


if __name__ == "__main__":
    emit()
