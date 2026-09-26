"""Forward test: does the screen at expiry E predict returns from E to E+1?

Strictly out-of-sample by construction -- score_expiry(idx) sees only
expiries[:idx+1], and the return measured is idx -> idx+1.

Reports whatever the data says. A screen that does not predict is a finding.
"""
import statistics as st, sys
from screen import load, score_expiry, forward_return, MIN_HIST
from sectors import sector_map

N = 10   # basket size


def run(tests=10, n=N):
    by, exps = load()
    sm = sector_map()
    first = MIN_HIST
    last = len(exps) - 2                      # need idx+1 for the return
    idxs = list(range(first, last + 1))[-tests:]
    print(f"{len(exps)} expiries loaded ({exps[0]} .. {exps[-1]})")
    print(f"running {len(idxs)} forward tests, baskets of {n}\n")
    print(f"{'screened at':<13}{'→ measured to':<15}{'OUT':>8}{'UNDER':>8}{'univ':>8}"
          f"{'spread':>9}{'out>univ':>10}{'und<univ':>10}")
    rows = []
    for i in idxs:
        rec = score_expiry(by, exps, i, sm)
        fwd = {s: forward_return(by, exps, i, s) for s in rec}
        rec = {s: v for s, v in rec.items() if fwd.get(s) is not None}
        if len(rec) < 3 * n:
            continue
        rank = sorted(rec, key=lambda s: -rec[s]["score"])
        top, bot = rank[:n], rank[-n:]
        t = st.mean(fwd[s] for s in top)
        b = st.mean(fwd[s] for s in bot)
        u = st.mean(fwd[s] for s in rec)
        ho = sum(1 for s in top if fwd[s] > u) / n * 100
        hu = sum(1 for s in bot if fwd[s] < u) / n * 100
        rows.append((exps[i], exps[i + 1], t, b, u, t - b, ho, hu))
        print(f"{exps[i]:<13}{exps[i+1]:<15}{t:>+8.2f}{b:>+8.2f}{u:>+8.2f}"
              f"{t-b:>+9.2f}{ho:>9.0f}%{hu:>9.0f}%")
    if not rows:
        print("no testable windows"); return
    T = [r[2] for r in rows]; B = [r[3] for r in rows]
    U = [r[4] for r in rows]; S = [r[5] for r in rows]
    print("\n" + "="*80)
    print(f"{'MEAN':<28}{st.mean(T):>+8.2f}{st.mean(B):>+8.2f}{st.mean(U):>+8.2f}{st.mean(S):>+9.2f}")
    print(f"{'MEDIAN':<28}{st.median(T):>+8.2f}{st.median(B):>+8.2f}{st.median(U):>+8.2f}{st.median(S):>+9.2f}")
    print(f"\n  spread positive in {sum(1 for s in S if s>0)}/{len(S)} months")
    print(f"  outperformer basket beat the universe in {sum(1 for r in rows if r[2]>r[4])}/{len(rows)}")
    print(f"  underperformer basket lagged the universe in {sum(1 for r in rows if r[3]<r[4])}/{len(rows)}")
    sd = st.pstdev(S) or 1e-9
    print(f"\n  mean spread {st.mean(S):+.2f}pp, sd {sd:.2f}, t≈{st.mean(S)/(sd/len(S)**0.5):.2f} "
          f"on {len(S)} obs — NOT significance, just scale")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
