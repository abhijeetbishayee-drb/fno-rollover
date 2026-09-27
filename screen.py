"""The screen itself, shared by analyse.py and forward_test.py.

One implementation deliberately: a second copy is how this project's own
history says things drift.

Scoring is point-in-time. score_expiry(idx) uses ONLY expiries[:idx+1], so a
forward test cannot leak information from the future it is trying to predict.
"""
import collections, csv, functools, statistics as st
from pathlib import Path
from sectors import sector_map, viable_sectors

KEYS = ["roll_vs_prev", "roll_vs_own", "roll_vs_sec", "cost_vs_prev", "cost_vs_own", "cost_vs_sec"]

# PCR is computed and exposed but is NOT in KEYS, so it does not move the
# composite score. Folding an untested input into a composite is how the one
# surviving result in this project would get diluted without anyone noticing.
# Promote these into KEYS only on split-sample evidence -- see split_test.py.
PCR_KEYS = ["pcr_vs_prev", "pcr_vs_wk", "pcr_vs_own", "pcr_vs_sec"]
MIN_HIST = 4
MIN_PCR_HIST = 2       # a trailing PCR average over one expiry is that expiry


def load(path=None):
    p = Path(path or Path(__file__).resolve().parent / "data" / "rollover_history.csv")
    rows = list(csv.DictReader(p.open()))
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["symbol"]][r["expiry"]] = r
    return by, sorted({r["expiry"] for r in rows})


@functools.lru_cache(maxsize=None)
def pcr_map(path=None):
    """(expiry, kind) -> {symbol: pcr}, from the committed PCR series.

    Memoised: score_expiry runs once per window and split_test walks 27 of
    them, so an unmemoised reader would re-parse an 11.5k-row CSV 27 times.
    viable_sectors had exactly this bug and was re-fetching over the network.

    Missing file is tolerated: the screen predates PCR and must still run
    without it. Missing is NOT the same as zero -- callers get no key at all.
    """
    p = Path(path or Path(__file__).resolve().parent / "data" / "pcr_history.csv")
    out = collections.defaultdict(dict)
    if not p.exists():
        return out
    for r in csv.DictReader(p.open()):
        out[(r["expiry"], r["kind"])][r["symbol"]] = float(r["pcr"])
    return out


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
    pm = pcr_map()
    pc_cur, pc_wk = pm.get((cur, "on"), {}), pm.get((cur, "wk"), {})
    pc_prev = pm.get((prev, "on"), {})
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
        # PCR, same point-in-time rule: `cur` is an expiry-day reading, and the
        # trailing average sees only `past`.
        if s in pc_cur:
            v = pc_cur[s]
            rec[s]["pcr"] = v
            if s in pc_wk:
                rec[s]["pcr_wk"] = pc_wk[s]
                rec[s]["pcr_vs_wk"] = v - pc_wk[s]
            if s in pc_prev:
                rec[s]["pcr_vs_prev"] = v - pc_prev[s]
            back = [pm[(e, "on")][s] for e in past
                    if (e, "on") in pm and s in pm[(e, "on")]]
            if len(back) >= MIN_PCR_HIST:
                rec[s]["pcr_vs_own"] = v - st.mean(back)
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
        withp = [m for m in members if "pcr" in rec[m]]
        if len(withp) >= 2:
            pavg = st.mean(rec[m]["pcr"] for m in withp)
            for m in withp:
                rec[m]["pcr_vs_sec"] = rec[m]["pcr"] - pavg
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
