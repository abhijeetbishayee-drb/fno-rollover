"""The screen itself, shared by analyse.py and forward_test.py.

One implementation deliberately: a second copy is how this project's own
history says things drift.

Scoring is point-in-time. score_expiry(idx) uses ONLY expiries[:idx+1], so a
forward test cannot leak information from the future it is trying to predict.
"""
import collections, csv, statistics as st
from pathlib import Path
from sectors import sector_map, viable_sectors

KEYS = ["roll_vs_prev", "roll_vs_own", "roll_vs_sec", "cost_vs_prev", "cost_vs_own", "cost_vs_sec"]
MIN_HIST = 4


def load(path=None):
    p = Path(path or Path(__file__).resolve().parent / "data" / "rollover_history.csv")
    rows = list(csv.DictReader(p.open()))
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["symbol"]][r["expiry"]] = r
    return by, sorted({r["expiry"] for r in rows})


def _z(vals):
    m, s = st.mean(vals), (st.pstdev(vals) or 1.0)
    return lambda x: (x - m) / s


def score_expiry(by, exps, idx, sm=None):
    """Screen as it would have been computed AT exps[idx]. No lookahead."""
    if idx < 1:
        return {}
    cur, prev = exps[idx], exps[idx - 1]
    past = exps[:idx]                      # strictly before cur
    sm = sm if sm is not None else sector_map()
    rec = {}
    for s, d in by.items():
        if cur not in d or prev not in d:
            continue
        hist = [d[e] for e in past if e in d]
        if len(hist) < MIN_HIST:
            continue
        roll, cost = float(d[cur]["rollover_pct"]), float(d[cur]["rollover_cost_pct"])
        rec[s] = {
            "mom": 100 * (float(d[cur]["spot"]) - float(d[prev]["spot"])) / float(d[prev]["spot"]),
            "roll": roll, "cost": cost,
            "roll_vs_prev": roll - float(d[prev]["rollover_pct"]),
            "cost_vs_prev": cost - float(d[prev]["rollover_cost_pct"]),
            "roll_vs_own": roll - st.mean(float(h["rollover_pct"]) for h in hist),
            "cost_vs_own": cost - st.mean(float(h["rollover_cost_pct"]) for h in hist),
            "sector": sm.get(s),
        }
    groups = collections.defaultdict(list)
    for s, v in rec.items():
        if v["sector"]:
            groups[v["sector"]].append(s)
    viable = viable_sectors(rec.keys())
    for k, members in groups.items():
        if k not in viable:
            continue
        ravg = st.mean(rec[m]["roll"] for m in members)
        cavg = st.mean(rec[m]["cost"] for m in members)
        for m in members:
            rec[m]["roll_vs_sec"] = rec[m]["roll"] - ravg
            rec[m]["cost_vs_sec"] = rec[m]["cost"] - cavg
    zf = {k: _z([v[k] for v in rec.values() if k in v]) for k in KEYS
          if any(k in v for v in rec.values())}
    for v in rec.values():
        have = [zf[k](v[k]) for k in KEYS if k in v and k in zf]
        v["score"] = sum(have) / len(have) if have else 0.0
        v["n_cmp"] = len(have)
    return rec


def forward_return(by, exps, idx, sym):
    """Spot return from exps[idx] to exps[idx+1]; None if unmeasurable."""
    if idx + 1 >= len(exps):
        return None
    d = by.get(sym, {})
    a, b = exps[idx], exps[idx + 1]
    if a not in d or b not in d:
        return None
    p0 = float(d[a]["spot"])
    return 100 * (float(d[b]["spot"]) - p0) / p0 if p0 > 0 else None
