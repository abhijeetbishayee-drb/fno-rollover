"""Parity test: this repo's sector plotting vs the heatmap board's.

Exists because of the 2026-09-06 Android incident -- "at parity" was declared
after a partial port and the user found the gap in testing. The lesson recorded
then was: diff explicitly against a checklist, never infer. So this is a test,
re-runnable, not a one-off eyeball.

Divergences are not automatically failures. Some are STRUCTURAL and justified.
They must be DECLARED here, so an undeclared one is what fails.
"""
import csv, glob, json, statistics as st, sys
from pathlib import Path
import sectors as ours

# Module-level so test_parity_negative.py can point check [5] at a mutated copy.
SHEET = Path(__file__).resolve().parent / "sheet_data.json"

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

    # 3. names we map that the board does not know at all. sector_map() derives
    # our map FROM FNO_SECTORS, so this is structurally impossible -- which is
    # exactly why it must fail rather than print REVIEW: if it ever fires, the
    # derivation in sectors.py has broken, and an advisory line would let that
    # through the weekly gate unnoticed.
    unknown = sorted(set(mine) - set(hm_sec))
    if unknown: fails.append(f"names we map that the board does not know: {unknown}")
    print(f"[3] names not on board : {unknown if unknown else 'none'}  "
          f"{'OK' if not unknown else 'FAIL'}")

    # 4. cash-only exclusion is total (declared divergence, but must be clean)
    leaked = sorted(set(mine) & cash)
    if leaked: fails.append(f"cash-only leaked into our map: {leaked}")
    print(f"[4] cash-only excluded : {len(cash)} on board, {len(leaked)} leaked  "
          f"{'OK' if not leaked else 'FAIL'}")

    # 5. aggregation method matches: equal-weighted mean over members with data.
    # This used to grep the source for the string "st.mean", which is not a test
    # of anything -- it passed on a comment and broke the moment the averaging
    # moved file (2026-09-27, when analyse.py stopped duplicating screen.py).
    # Now it checks the PUBLISHED sector aggregate against an independently
    # recomputed equal-weighted mean, which an OI- or cap-weighted change fails.
    worst, checked = 0.0, 0
    try:
        doc = json.loads(SHEET.read_text())
    except FileNotFoundError:
        doc = None
    if doc is None:
        print("[5] equal-weighted mean: SKIP — sheet_data.json not built yet")
    else:
        for sec in doc["sectors"]:
            rolls = [r["rollover"] for r in sec["rows"] if r.get("rollover") is not None]
            costs = [r["rollover_cost"] for r in sec["rows"] if r.get("rollover_cost") is not None]
            if not rolls or not costs:
                continue
            worst = max(worst, abs(st.mean(rolls) - sec["avgRoll"]),
                        abs(st.mean(costs) - sec["avgCost"]))
            checked += 1
        ew = worst <= 0.005                     # published values are rounded to 2-3dp
        print(f"[5] equal-weighted mean: {'OK — matches build_sectors' if ew else 'FAIL'}"
              f"  ({checked} sectors, worst deviation {worst:.4f})")
        if not ew:
            fails.append(f"sector aggregate is not an equal-weighted mean "
                         f"(worst deviation {worst:.4f})")

    print("\nDECLARED structural divergences (intentional):")
    for k, v in DECLARED.items():
        print(f"  * {k}: {v}")

    print("\n" + ("PARITY OK" if not fails else "PARITY FAILED:\n  " + "\n  ".join(fails)))
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
