"""Render the rollover sheet in the F&O Gurukul layout, grouped by sector.

Two columns from the original are deliberately NOT reproduced:
  TGT.  -- a discretionary price target, not derivable from the data
  RANK  -- its rule could not be recovered (ETERNAL ranked 1 with rollover 8pp
           BELOW its own average, which kills every obvious hypothesis), so a
           guessed RANK would be fiction. Our own SCORE is shown instead.
"""
import collections, statistics as st, sys, csv
from screen import load, score_expiry, MIN_HIST
from sectors import sector_map


def build(expiry=None, out_csv=True):
    by, exps = load()
    idx = exps.index(expiry) if expiry else len(exps) - 1
    cur, prev = exps[idx], exps[idx - 1]
    prev2 = exps[idx - 2] if idx >= 2 else None
    sm = sector_map()
    rec = score_expiry(by, exps, idx, sm)
    rows = []
    for s, v in rec.items():
        d = by[s]
        rows.append({
            "sector": v["sector"] or "(unclassified)", "symbol": s,
            "spot": float(d[cur]["spot"]), "M_O_M": v["mom"],
            "future_price": float(d[cur]["near_px"]), "basis": float(d[cur]["basis"]),
            "rollover": v["roll"], "avg_roll": v["roll"] - v["roll_vs_own"],
            "rollover_cost": v["cost"], "avg_cost": v["cost"] - v["cost_vs_own"],
            "DIIF": v["roll_vs_own"],
            "rollover_prev": float(d[prev]["rollover_pct"]),
            "cost_prev": float(d[prev]["rollover_cost_pct"]),
            "rollover_prev2": (float(d[prev2]["rollover_pct"])
                               if prev2 and prev2 in d else None),
            "cost_prev2": (float(d[prev2]["rollover_cost_pct"])
                           if prev2 and prev2 in d else None),
            "score": v["score"],
        })
    rows.sort(key=lambda r: (r["sector"], r["symbol"]))
    if out_csv:
        p = f"data/sheet_{cur}.csv"
        with open(p, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        print(f"full sheet -> {p}  ({len(rows)} rows, expiry {cur}, prev {prev})\n")
    return rows, cur, prev, prev2


def show(rows, sectors=None, limit=None):
    H = (f"{'symbol':<12}{'spot':>10}{'M_O_M':>8}{'future':>10}{'basis':>8}"
         f"{'rollover':>10}{'AVG ROLL':>10}{'cost':>8}{'AVG COST':>10}{'DIIF':>8}"
         f"{'roll(prev)':>11}{'score':>7}")
    by_sec = collections.defaultdict(list)
    for r in rows:
        by_sec[r["sector"]].append(r)
    for sec in (sectors or sorted(by_sec)):
        grp = by_sec.get(sec) or []
        if not grp:
            continue
        print(f"\n── {sec}  (n={len(grp)}) " + "─" * max(0, 96 - len(sec)))
        print(H)
        for r in (grp[:limit] if limit else grp):
            print(f"{r['symbol']:<12}{r['spot']:>10,.2f}{r['M_O_M']:>+8.2f}"
                  f"{r['future_price']:>10,.2f}{r['basis']:>8.2f}{r['rollover']:>10.2f}"
                  f"{r['avg_roll']:>10.2f}{r['rollover_cost']:>8.2f}{r['avg_cost']:>10.2f}"
                  f"{r['DIIF']:>+8.2f}{r['rollover_prev']:>11.2f}{r['score']:>+7.2f}")
        print(f"{'  SECTOR AVG':<12}{'':>10}{st.mean(g['M_O_M'] for g in grp):>+8.2f}"
              f"{'':>10}{'':>8}{st.mean(g['rollover'] for g in grp):>10.2f}"
              f"{st.mean(g['avg_roll'] for g in grp):>10.2f}"
              f"{st.mean(g['rollover_cost'] for g in grp):>8.2f}")


if __name__ == "__main__":
    rows, cur, prev, _ = build("2026-08-25")
    show(rows, sectors=["Banks", "Capital Goods", "Metals & Mining"])
