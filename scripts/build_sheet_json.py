"""Emit the hosted monthly sheets.

Writes one JSON per expiry (so any past month can be viewed), an expiries.json
index for the picker, and sheet_data.json as the latest -- kept under its
original name so nothing that already points at it breaks.

Sector order is CANONICAL and set here: by average rollover cost, descending.
The weekly sheet adopts this exact order, because if each view sorted by its
own period's value the sequences would diverge and the two would stop scrolling
together.
"""
import collections, json, statistics as st, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sheet import build          # noqa: E402
from screen import load          # noqa: E402

# Every expiry with enough history to score gets its own file. The floor is
# screen.MIN_HIST: below that the trailing-average baseline does not exist, so
# a sheet there would show a DIIF computed from too few points -- worse than
# absent, because it would look like data.


def emit(rows, cur, prev, prev2):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["sector"]].append(r)
    rnd = lambda v: round(v, 4) if isinstance(v, float) else v
    sectors = [{
        "sector": sec, "count": len(grp),
        "avgMom":  round(st.mean(g["M_O_M"] for g in grp), 2),
        "avgRoll": round(st.mean(g["rollover"] for g in grp), 2),
        "avgCost": round(st.mean(g["rollover_cost"] for g in grp), 3),
        "rows": [{k: rnd(v) for k, v in g.items() if k != "sector"} for g in grp],
    } for sec, grp in sorted(by.items())]
    sectors.sort(key=lambda s: -s["avgCost"])
    for i, s in enumerate(sectors):
        s["order"] = i
    return {"expiry": cur, "prevExpiry": prev, "prevExpiry2": prev2,
            "count": len(rows), "sectors": sectors,
            "generatedAt": datetime.now(timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z")}


def main():
    _, exps = load()
    index = []
    from screen import MIN_HIST
    for e in exps[MIN_HIST:]:
        rows, cur, prev, prev2 = build(e, out_csv=False)
        name = f"sheet_{cur}.json"
        (ROOT / name).write_text(json.dumps(emit(rows, cur, prev, prev2),
                                            separators=(",", ":")))
        index.append({"expiry": cur, "file": name, "count": len(rows)})
    index.reverse()                                   # newest first
    (ROOT / "expiries.json").write_text(
        json.dumps({"expiries": index}, separators=(",", ":")))
    # latest also under the original name
    rows, cur, prev, prev2 = build(out_csv=False)
    (ROOT / "sheet_data.json").write_text(
        json.dumps(emit(rows, cur, prev, prev2), separators=(",", ":")))
    print(f"wrote {len(index)} per-expiry files + expiries.json; "
          f"latest {cur} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
