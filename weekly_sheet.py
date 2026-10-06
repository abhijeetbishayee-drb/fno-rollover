"""Weekly sheet: the three steps at weekly cadence.

Step 2 CANNOT be weekly rollover -- there is one roll per series, so a weekly
rollover number would be fiction. Its weekly analogue is OI change: rollover
asks "did positions move to the next series", weekly OI asks "are positions
building or unwinding". Same question, weekly cadence.
"""
import collections, csv, json, statistics as st
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from sectors import sector_map

ROOT = Path(__file__).resolve().parent
SNAP = ROOT / "data" / "weekly_snapshots.csv"
PCRW = ROOT / "data" / "pcr_weekly.csv"
HIST = 26          # sparkline points, one per week of elapsed time
WOW_DAYS = 7       # "a week ago" and "a month ago" are DURATIONS, not row
MOM_DAYS = 28      # offsets -- see below


# ANCHORS ARE DATES, NOT ROW POSITIONS.
#
# This file used to take weeks[-2] as "a week ago" and weeks[-4] as "a month
# ago", which is only true while captures land exactly one week apart. They do
# not. The published sheet on 2026-09-30 read asof 2026-09-29 against prevWeek
# 2026-09-25 and called it week-on-week: a FOUR-day comparison, because an
# off-grid capture on the Tuesday expiry followed the Friday one. The label was
# wrong and nothing could notice, since the code never looked at the dates.
#
# It matters much more now that the snapshot job runs DAILY: on a positional
# rule, week-on-week would quietly become day-on-day, "a month" would become
# four days, and the 26-point sparkline would cover five weeks instead of six
# months -- every one of them still labelled as before. Anchoring to elapsed
# time keeps the weekly view weekly whatever the capture cadence, and the gap
# actually used is published per row so a stretched comparison is visible
# rather than implied.

def _d(iso):
    return date.fromisoformat(iso)


def nearest(days, target, exclude=()):
    """The capture closest in TIME to `target`; ties go to the earlier one."""
    pool = [d for d in days if d not in exclude]
    return min(pool, key=lambda d: (abs((_d(d) - target).days), d)) if pool else None


def anchors(days, cur):
    """(a week back, four weeks back) as dates, each the nearest capture."""
    c = _d(cur)
    wk = nearest(days, c - timedelta(days=WOW_DAYS), exclude={cur})
    mo = nearest(days, c - timedelta(days=MOM_DAYS), exclude={cur})
    return wk, mo


def weekly_grid(days, cur, n=HIST):
    """`n` points one week apart ending at `cur`, nearest capture to each.

    De-duplicated: a daily series has several captures per week and a sparse one
    may have none, so the grid is however many DISTINCT weeks actually exist.
    """
    c, out = _d(cur), []
    for k in range(n - 1, -1, -1):
        d = nearest(days, c - timedelta(days=WOW_DAYS * k))
        if d and d not in out:
            out.append(d)
    return out


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
    prev_w, prev_m = anchors(weeks, cur)
    past = weekly_grid(weeks, cur)
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
            p["wkDays"] = (_d(cur) - _d(prev_w)).days
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
    cur = weeks[-1]
    prev = anchors(weeks, cur)[0] or weeks[-2]
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
    # prevWeekDays is the gap ACTUALLY used. The page shows it whenever it is
    # not 7, so a comparison stretched by a holiday or a missed capture reads
    # as what it is instead of being labelled week-on-week regardless.
    doc = {"asof": cur, "prevWeek": prev,
           "prevWeekDays": (_d(cur) - _d(prev)).days,
           "capturesAvailable": len(weeks), "weeksAvailable": len(past),
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
