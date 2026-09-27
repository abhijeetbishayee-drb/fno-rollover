"""Split-sample test: does a finding live in BOTH halves, or only one?

Six variants were tested at three sample sizes, so roughly a one-in-four chance
that something clears p<0.05 on luck alone. A real effect appears in both halves
with the same sign. An artefact lives in one.

Also measures basket OVERLAP, because "cost fell most" and "price fell +
rollover built" may be one finding counted twice.
"""
import statistics as st, sys
from screen import load, score_expiry, forward_return, MIN_HIST
from sectors import sector_map
from decompose import sub, ROLL, COST, PCR, N


def collect(tests=27, n=N):
    by, exps = load(); sm = sector_map()
    idxs = list(range(MIN_HIST, len(exps) - 1))[-tests:]
    per = {}; picks = []
    for i in idxs:
        rec = score_expiry(by, exps, i, sm)
        fwd = {s: forward_return(by, exps, i, s) for s in rec}
        rec = {s: v for s, v in rec.items() if fwd.get(s) is not None}
        if len(rec) < 3 * n:
            continue
        u = st.mean(fwd[s] for s in rec)
        rs, cs, ps = sub(rec, ROLL), sub(rec, COST), sub(rec, PCR)
        cost_bot = sorted(cs, key=lambda s: cs[s])[:n]
        pcr_bot = sorted(ps, key=lambda s: ps[s])[:n]
        # COST-bottom and PCR-bottom overlap by ~0.5 names of 10, so they are
        # near-independent selections. Test the combination rather than assume
        # two weak shorts add up.
        cp = sub(rec, COST + PCR)
        both_bot = sorted(cp, key=lambda s: cp[s])[:n]
        down = [s for s in rec if rec[s]["mom"] < 0 and s in rs]
        div_up = sorted(down, key=lambda s: -rs[s])[:n]
        roll_bot = sorted(rs, key=lambda s: rs[s])[:n]
        for name, names in (("COST bottom (short)", cost_bot),
                            ("PCR bottom (short)", pcr_bot),
                            ("COST+PCR bottom (short)", both_bot),
                            ("DIV fell+roll↑ (long)", div_up),
                            ("ROLLOVER bottom", roll_bot)):
            if names:
                per.setdefault(name, []).append(
                    (exps[i], st.mean(fwd[s] for s in names) - u))
        picks.append((exps[i], set(cost_bot), set(div_up), set(pcr_bot)))
    return per, picks


def main(tests=27):
    per, picks = collect(tests)
    print(f"{len(picks)} windows, split into halves\n")
    print(f"{'variant':<24}{'1st half':>20}{'2nd half':>20}{'verdict':>12}")
    print(f"{'':<24}{'excess   hit':>20}{'excess   hit':>20}")
    for name, rows in per.items():
        h = len(rows) // 2
        a, b = rows[:h], rows[h:]
        ea, eb = st.mean(x for _, x in a), st.mean(x for _, x in b)
        # direction we are testing: short variants want negative, long positive
        want_neg = "short" in name or "bottom" in name and "DIV" not in name
        ha = sum(1 for _, x in a if (x < 0) == want_neg)
        hb = sum(1 for _, x in b if (x < 0) == want_neg)
        same = (ea < 0) == (eb < 0)
        v = "BOTH halves" if same and abs(ea) > 0.2 and abs(eb) > 0.2 else \
            "one half only" if not same else "weak/flat"
        print(f"{name:<24}{ea:>+9.2f} {ha:>3}/{len(a):<6}{eb:>+9.2f} {hb:>3}/{len(b):<6}{v:>12}")
    print(f"\n  1st half: {picks[0][0]} .. {picks[len(picks)//2 - 1][0]}")
    print(f"  2nd half: {picks[len(picks)//2][0]} .. {picks[-1][0]}")
    ov = [len(c & d) for _, c, d, _ in picks]
    print(f"\n  basket overlap, COST-bottom vs DIV-fell+roll↑: mean {st.mean(ov):.1f} of {N} names"
          f"  (max {max(ov)}, min {min(ov)})")
    op = [len(c & q) for _, c, _, q in picks]
    print(f"  basket overlap, COST-bottom vs PCR-bottom      : mean {st.mean(op):.1f} of {N} names"
          f"  (max {max(op)}, min {min(op)})")
    print("  -> high overlap would mean these are ONE finding counted twice")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 27)
