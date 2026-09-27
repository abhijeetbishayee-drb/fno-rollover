"""Negative tests for parity_check.py: prove each check can actually go RED.

Written after check [5] was found to be `"st.mean" in source` -- a substring
grep wearing the label "equal-weighted mean", which would have passed on a
comment and failed only because the averaging moved file. A check that cannot
fail is not a check, and the only way to know is to break it on purpose.

Each case asserts three things: clean run is OK, the injected violation is
caught, and the restored state is OK again. The third matters -- a test that
leaves the tree dirty would make the next check's result meaningless.
"""
import contextlib, io, json, sys, tempfile
from pathlib import Path

import sectors as ours
import parity_check as pc

ROOT = Path(__file__).resolve().parent


def run():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pc.main()
    return rc, buf.getvalue()


@contextlib.contextmanager
def patched_map(mutate):
    """Swap what parity_check sees as OUR map. heatmap_core() also calls
    sector_map(), but only to refresh the on-disk cache it then parses, so the
    board side stays honest while our side is corrupted."""
    real = ours.sector_map
    m = dict(real())
    mutate(m)
    ours.sector_map = lambda: m
    try:
        yield
    finally:
        ours.sector_map = real


@contextlib.contextmanager
def patched_sheet(mutate):
    real = pc.SHEET
    doc = json.loads(real.read_text())
    mutate(doc)
    tmp = Path(tempfile.mkdtemp()) / "sheet_data.json"
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    pc.SHEET = tmp
    try:
        yield
    finally:
        pc.SHEET = real


def invent_label(m):
    m["RELIANCE"] = "Bitcoin Mining"


def move_member(m):
    # a real board sector, but the wrong one for this name
    m["RELIANCE"] = "Information Technology" if m.get("RELIANCE") != "Information Technology" \
        else "Banks"


def unknown_symbol(m):
    m["NOTAREALTICKER"] = "Banks"


def leak_cash_only(m):
    hm = pc.heatmap_core()
    norm = lambda t: t[:-3] if t.endswith(".NS") else t
    cash = sorted(norm(t) for t in (getattr(hm, "CASH_ONLY", []) or []))
    assert cash, "no cash-only names on the board to leak"
    m[cash[0]] = "Banks"


def spot_weight(doc):
    s = doc["sectors"][0]
    w = [r["spot"] for r in s["rows"]]
    v = [r["rollover"] for r in s["rows"]]
    s["avgRoll"] = round(sum(a * b for a, b in zip(w, v)) / sum(w), 2)


CASES = [
    ("[1] invented sector label", patched_map, invent_label,  "sector labels we invented"),
    ("[2] member in wrong sector", patched_map, move_member,  "membership disagrees"),
    ("[3] symbol not on the board", patched_map, unknown_symbol,
     "board does not know"),
    ("[4] cash-only name leaked",  patched_map, leak_cash_only, "cash-only leaked"),
    ("[5] spot-weighted aggregate", patched_sheet, spot_weight,
     "not an equal-weighted mean"),
]


def main():
    rc, _ = run()
    if rc != 0:
        print("ABORT: baseline parity is already failing; fix that first")
        return 2

    bad = []
    print(f"{'case':<30}{'detects':>9}{'restores':>10}   expectation")
    for name, ctx, mutate, expect in CASES:
        with ctx(mutate):
            rc, out = run()
        caught = (rc == 1 and expect in out) if expect else (rc == 0)
        rc2, _ = run()
        restored = rc2 == 0
        note = "must FAIL" if expect else "advisory only — REVIEW, never fails"
        print(f"{name:<30}{'yes' if caught else 'NO':>9}{'yes' if restored else 'NO':>10}   {note}")
        if not (caught and restored):
            bad.append(name)

    print()
    if bad:
        print("NEGATIVE TESTS FAILED: " + ", ".join(bad))
        return 1
    print("all parity checks respond to an injected violation as documented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
