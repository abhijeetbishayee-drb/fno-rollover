"""Outperformer / underperformer screen over rollover history.

Three STEPS (the user's note): 1 MOM gain, 2 Rollover, 3 cost gain/decline.
Three COMPARISONS per step: vs previous month, vs own trailing average,
vs sector average. Research only -- reads a CSV, places nothing.
"""
import csv, collections, statistics as st, sys
from pathlib import Path
from sectors import sector_map, viable_sectors, MIN_PEERS
SECTOR_MAP = sector_map()

ROOT = Path(__file__).resolve().parent
rows = list(csv.DictReader((ROOT / "data" / "rollover_history.csv").open()))
by = collections.defaultdict(dict)
for r in rows:
    by[r["symbol"]][r["expiry"]] = r
exps = sorted({r["expiry"] for r in rows})
cur, prev = exps[-1], exps[-2]

def z(vals):
    m, s = st.mean(vals), (st.pstdev(vals) or 1.0)
    return lambda x: (x - m) / s

rec = {}
for s, d in by.items():
    if cur not in d or prev not in d:
        continue
    hist = [d[e] for e in exps[:-1] if e in d]
    if len(hist) < 4:
        continue
    roll, cost = float(d[cur]["rollover_pct"]), float(d[cur]["rollover_cost_pct"])
    rec[s] = {
        "mom":  100 * (float(d[cur]["spot"]) - float(d[prev]["spot"])) / float(d[prev]["spot"]),
        "roll": roll, "cost": cost,
        "roll_vs_prev": roll - float(d[prev]["rollover_pct"]),
        "cost_vs_prev": cost - float(d[prev]["rollover_cost_pct"]),
        "roll_vs_own":  roll - st.mean(float(h["rollover_pct"]) for h in hist),
        "cost_vs_own":  cost - st.mean(float(h["rollover_cost_pct"]) for h in hist),
        "sector": SECTOR_MAP.get(s),
    }

# comparison 3: vs sector average (only where a sector is known)
sec = collections.defaultdict(list)
for s, v in rec.items():
    if v["sector"]:
        sec[v["sector"]].append(s)
VIABLE = viable_sectors(rec.keys())     # >= MIN_PEERS; smaller groups get NO baseline
for k, members in sec.items():
    if k not in VIABLE:
        continue                        # never average a group of 1-4
    ravg = st.mean(rec[m]["roll"] for m in members)
    cavg = st.mean(rec[m]["cost"] for m in members)
    for m in members:
        rec[m]["roll_vs_sec"] = rec[m]["roll"] - ravg
        rec[m]["cost_vs_sec"] = rec[m]["cost"] - cavg

KEYS = ["roll_vs_prev", "roll_vs_own", "roll_vs_sec", "cost_vs_prev", "cost_vs_own", "cost_vs_sec"]
zf = {k: z([v[k] for v in rec.values() if k in v]) for k in KEYS}
for v in rec.values():
    have = [zf[k](v[k]) for k in KEYS if k in v]
    v["score"] = sum(have) / len(have)          # mean of AVAILABLE comparisons
    v["n_cmp"] = len(have)

def show(title, items, note=""):
    print(f"\n{title}{note}")
    print(f"  {'symbol':<12}{'MOM%':>8}{'roll%':>8}{'vs prev':>9}{'vs own':>8}{'vs sec':>8}{'cost Δown':>11}{'score':>7}")
    for s, v in items:
        vs = f"{v['roll_vs_sec']:+8.2f}" if "roll_vs_sec" in v else f"{'--':>8}"
        print(f"  {s:<12}{v['mom']:>+8.2f}{v['roll']:>8.2f}{v['roll_vs_prev']:>+9.2f}"
              f"{v['roll_vs_own']:>+8.2f}{vs}{v['cost_vs_own']:>+11.2f}{v['score']:>+7.2f}")

ranked = sorted(rec.items(), key=lambda kv: -kv[1]["score"])
print(f"ROLLOVER SCREEN — expiry {cur} (prev {prev}) · {len(rec)} symbols · "
      f"{sum(1 for v in rec.values() if v['n_cmp']==6)} with all 3 comparisons")
show("OUTPERFORMERS — price up, positions carried forward above every baseline",
     [(s, v) for s, v in ranked if v["mom"] > 0][:10])
show("UNDERPERFORMERS — price down, positions leaving below every baseline",
     [(s, v) for s, v in reversed(ranked) if v["mom"] < 0][:10])
show("DIVERGENCE — price ROSE but rollover/cost collapsed (longs leaving into strength)",
     [(s, v) for s, v in reversed(ranked) if v["mom"] > 3][:8])
show("DIVERGENCE — price FELL but rollover/cost built (positions added into weakness)",
     [(s, v) for s, v in ranked if v["mom"] < -3][:8])
