"""Decompose the screen: does any single step predict, and do the divergences?

The composite averages six sub-signals equally, which can bury a live signal in
a dead one. This tests each step alone, and tests the DIVERGENCE selections --
which are a different selection rule from "highest composite", not a subset of it.

Same point-in-time discipline: scoring at E, return measured E -> E+1.
"""
import statistics as st, sys
from screen import load, score_expiry, forward_return, MIN_HIST
from sectors import sector_map

N = 10
ROLL = ["roll_vs_prev", "roll_vs_own", "roll_vs_sec"]
COST = ["cost_vs_prev", "cost_vs_own", "cost_vs_sec"]


def _z(vals):
    m, s = st.mean(vals), (st.pstdev(vals) or 1.0)
    return lambda x: (x - m) / s


def sub(rec, keys):
    """Mean z across `keys`, over names that have them."""
    zf = {k: _z([v[k] for v in rec.values() if k in v]) for k in keys
          if any(k in v for v in rec.values())}
    out = {}
    for s, v in rec.items():
        have = [zf[k](v[k]) for k in keys if k in v and k in zf]
        if have:
            out[s] = sum(have) / len(have)
    return out


def basket(fwd, names):
    return st.mean(fwd[s] for s in names) if names else float("nan")


def run(tests=7, n=N):
    by, exps = load(); sm = sector_map()
    idxs = list(range(MIN_HIST, len(exps) - 1))[-tests:]
    acc = {}
    for i in idxs:
        rec = score_expiry(by, exps, i, sm)
        fwd = {s: forward_return(by, exps, i, s) for s in rec}
        rec = {s: v for s, v in rec.items() if fwd.get(s) is not None}
        if len(rec) < 3 * n:
            continue
        u = st.mean(fwd.values() for _ in [0]) if False else st.mean(fwd[s] for s in rec)
        rs, cs = sub(rec, ROLL), sub(rec, COST)
        variants = {
            "step1 MOM":        sorted(rec, key=lambda s: -rec[s]["mom"]),
            "step2 ROLLOVER":   sorted(rs,  key=lambda s: -rs[s]),
            "step3 COST":       sorted(cs,  key=lambda s: -cs[s]),
            "composite":        sorted(rec, key=lambda s: -rec[s]["score"]),
        }
        for name, rank in variants.items():
            top, bot = rank[:n], rank[-n:]
            a = acc.setdefault(name, {"t": [], "b": [], "u": []})
            a["t"].append(basket(fwd, top) - u)      # excess vs universe
            a["b"].append(basket(fwd, bot) - u)
            a["u"].append(u)
        # divergences: opposite-sign selections, not rank extremes
        up   = [s for s in rec if rec[s]["mom"] > 0 and s in rs]
        down = [s for s in rec if rec[s]["mom"] < 0 and s in rs]
        d1 = sorted(up,   key=lambda s: rs[s])[:n]     # rose, rollover weakest
        d2 = sorted(down, key=lambda s: -rs[s])[:n]    # fell, rollover strongest
        for name, names in (("DIV rose+roll↓", d1), ("DIV fell+roll↑", d2)):
            if len(names) >= n // 2:
                acc.setdefault(name, {"t": [], "b": [], "u": []})["t"].append(
                    basket(fwd, names) - u)
    print(f"{len(idxs)} windows · baskets of {n} · figures are EXCESS vs universe (pp)\n")
    print(f"{'variant':<18}{'top':>8}{'bottom':>9}{'spread':>9}{'top>0':>8}{'bot<0':>8}")
    for name, a in acc.items():
        t = st.mean(a["t"]) if a["t"] else float("nan")
        if not a["b"]:
            hit = sum(1 for x in a["t"] if x > 0)
            print(f"{name:<18}{t:>+8.2f}{'—':>9}{'—':>9}{hit:>7}/{len(a['t'])}{'—':>8}")
            continue
        b = st.mean(a["b"])
        ht = sum(1 for x in a["t"] if x > 0); hb = sum(1 for x in a["b"] if x < 0)
        print(f"{name:<18}{t:>+8.2f}{b:>+9.2f}{t-b:>+9.2f}{ht:>7}/{len(a['t'])}"
              f"{hb:>7}/{len(a['b'])}")
    print("\n  top    = excess return of the highest-ranked basket")
    print("  bottom = excess return of the lowest-ranked basket")
    print("  a working LONG signal needs top > 0; a working SHORT signal needs bottom < 0")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
