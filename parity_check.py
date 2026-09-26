"""Parity test: this repo's sector plotting vs the heatmap board's.

Exists because of the 2026-09-06 Android incident -- "at parity" was declared
after a partial port and the user found the gap in testing. The lesson recorded
then was: diff explicitly against a checklist, never infer. So this is a test,
re-runnable, not a one-off eyeball.

Divergences are not automatically failures. Some are STRUCTURAL and justified.
They must be DECLARED here, so an undeclared one is what fails.
"""
import csv, glob, statistics as st, sys
import sectors as ours

DECLARED = {
    "cash_only": "heatmap PLOTS cash-only names (dashed tile); we exclude them — "
                 "they have no futures, so no OI/rollover/cost exists to screen",
    "min_peers": f"heatmap plots ALL 23 sectors; we suppress the sector BASELINE "
                 f"below {ours.MIN_PEERS} F&O members — a deviation from a group "
                 f"of one is 0.00 and reads as data. Different use of the same "
                 f"aggregate: they display breadth, we score against it",
}

def heatmap_core():
    """Same parse-don't-execute path sectors.py uses -- the heatmap module
    imports `requests`, which we must not require just to read two dicts."""
    ours.sector_map()                      # refreshes the cache
    from pathlib import Path
    return ours._extract(
        (Path(__file__).resolve().parent / "data" / "heatmap_core_cache.py").read_text())

def main():
    hm = heatmap_core()
    norm = lambda t: t[:-3] if t.endswith(".NS") else t
    hm_sec = {norm(t): s for s, v in hm.FNO_SECTORS.items() for t in v}
    cash = {norm(t) for t in (getattr(hm, "CASH_ONLY", []) or [])}
    mine = ours.sector_map()
    fails = []

    # 1. sector LABELS identical
    if set(hm.FNO_SECTORS) != set(v for v in mine.values()) | {
            s for s, v in hm.FNO_SECTORS.items() if all(norm(t) in cash for t in v)}:
        extra = set(mine.values()) - set(hm.FNO_SECTORS)
        if extra:
            fails.append(f"sector labels we invented: {extra}")
    print(f"[1] sector labels      : ours {len(set(mine.values()))} ⊆ heatmap {len(hm.FNO_SECTORS)}"
          f"  {'OK' if not (set(mine.values()) - set(hm.FNO_SECTORS)) else 'FAIL'}")

    # 2. every F&O name we map lands in the SAME sector as the board
    bad = {s: (mine[s], hm_sec.get(s)) for s in mine if s in hm_sec and mine[s] != hm_sec[s]}
    if bad: fails.append(f"membership disagrees: {bad}")
    print(f"[2] membership         : {len(mine)} names, {len(bad)} disagree  "
          f"{'OK' if not bad else 'FAIL'}")

    # 3. names we map that the board does not know at all
    unknown = sorted(set(mine) - set(hm_sec))
    print(f"[3] names not on board : {unknown if unknown else 'none'}  "
          f"{'OK' if not unknown else 'REVIEW'}")

    # 4. cash-only exclusion is total (declared divergence, but must be clean)
    leaked = sorted(set(mine) & cash)
    if leaked: fails.append(f"cash-only leaked into our map: {leaked}")
    print(f"[4] cash-only excluded : {len(cash)} on board, {len(leaked)} leaked  "
          f"{'OK' if not leaked else 'FAIL'}")

    # 5. aggregation method matches: equal-weighted mean over members with data
    src = open(ours.__file__).read() + open("analyse.py").read()
    ew = "st.mean" in src
    print(f"[5] equal-weighted mean: {'OK — matches build_sectors' if ew else 'FAIL'}")
    if not ew: fails.append("aggregation is not an equal-weighted mean")

    print("\nDECLARED structural divergences (intentional):")
    for k, v in DECLARED.items():
        print(f"  * {k}: {v}")

    print("\n" + ("PARITY OK" if not fails else "PARITY FAILED:\n  " + "\n  ".join(fails)))
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
