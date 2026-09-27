"""Outperformer / underperformer screen over rollover history.

Three STEPS (the user's note): 1 MOM gain, 2 Rollover, 3 cost gain/decline.
Three COMPARISONS per step: vs previous month, vs own trailing average,
vs sector average. Research only -- reads a CSV, places nothing.

The scoring itself lives in screen.py and is NOT repeated here. It used to be:
this module carried its own KEYS, its own z-scoring, its own trailing average
and its own sector-averaging block, which is exactly what screen.py's docstring
warns against ("a second copy is how this project's own history says things
drift"). The warning came true on 2026-09-27, when PCR was added to screen.py
and this file silently did not get it. This is now a presentation layer over
score_expiry() at the newest expiry; the numbers have one source.
"""
from screen import load, score_expiry

by, exps = load()
cur, prev = exps[-1], exps[-2]
rec = score_expiry(by, exps, len(exps) - 1)


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
