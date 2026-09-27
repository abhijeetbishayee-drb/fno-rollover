"""Merge per-stock PCR into every sheet_*.json, in place.

Reads data/pcr_history.csv only -- no network, no bhavcopy cache. Run
backfill_pcr.py first if the series needs extending.

Runs AFTER build_sheet_json.py and never rewrites the sheet's own numbers; it
only adds a `pcr` object to each row. Kept as its own pass on purpose: if NSE
changes the option rows, or a bhavcopy is missing, the rollover sheet must
still build. A PCR failure degrades the click-through, it does not take the
page down.

A row with no computable PCR gets NO `pcr` key at all, rather than one full of
nulls. The page then shows "no option data" instead of a panel of dashes, which
would read as "the ratio is zero" -- an absent number must never be able to
pass for a measured one.
"""
import collections, csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HIST = 12          # sparkline points; 12 expiries is a year of monthly PCR
SRC = ROOT / "data" / "pcr_history.csv"


def read_history():
    """(expiry, kind) -> {symbol: record}"""
    out = collections.defaultdict(dict)
    for r in csv.DictReader(SRC.open()):
        rec = {"pcr": round(float(r["pcr"]), 4),
               "ce": int(float(r["ce"])), "pe": int(float(r["pe"])),
               "asof": r["asof"]}
        for src, dst in (("max_ce", "maxCE"), ("max_pe", "maxPE")):
            if r[src]:
                rec[dst] = float(r[src])
        if r["opt_expiry"]:
            rec["expiry"] = r["opt_expiry"]
        out[(r["expiry"], r["kind"])][r["symbol"]] = rec
    return out


def build(sym, e, prev_e, past, hist):
    cur = hist[(e, "on")].get(sym)
    if not cur:
        return None
    p = {k: cur[k] for k in ("pcr", "ce", "pe") }
    for k in ("maxCE", "maxPE", "expiry"):
        if k in cur:
            p[k] = cur[k]
    wk = hist.get((e, "wk"), {}).get(sym)
    if wk:
        p["pcrWk"] = wk["pcr"]
        p["wow"] = round(cur["pcr"] - wk["pcr"], 4)
        p["wkDate"] = wk["asof"]
    prev = hist.get((prev_e, "on"), {}).get(sym) if prev_e else None
    if prev:
        p["pcrPrev"] = prev["pcr"]
        p["mom"] = round(cur["pcr"] - prev["pcr"], 4)
    # Values only, aligned to the doc-level pcrHist date list -- 205 copies of
    # the same 12 date strings tripled the file.
    series = [(hist.get((x, "on"), {}).get(sym) or {}).get("pcr") for x in past]
    if sum(v is not None for v in series) > 1:
        p["hist"] = series
    return p


def main():
    index = json.loads((ROOT / "expiries.json").read_text())["expiries"]
    order = [e["expiry"] for e in reversed(index)]           # oldest first
    hist = read_history()
    touched = 0

    for meta in index:
        e, path = meta["expiry"], ROOT / meta["file"]
        if (e, "on") not in hist:
            print(f"  WARN no PCR history for expiry {e} -- left untouched")
            continue
        i = order.index(e)
        prev_e = order[i - 1] if i else None
        past = order[max(0, i - HIST + 1):i + 1]

        doc = json.loads(path.read_text())
        n = 0
        for sec in doc["sectors"]:
            for r in sec["rows"]:
                p = build(r["symbol"], e, prev_e, past, hist)
                if p:
                    r["pcr"] = p
                    n += 1
                else:
                    r.pop("pcr", None)
        doc["pcrHist"] = past
        path.write_text(json.dumps(doc, separators=(",", ":")))
        touched += 1
        print(f"  {e}: {n}/{doc['count']} rows with PCR")

    (ROOT / "sheet_data.json").write_text((ROOT / index[0]["file"]).read_text())
    print(f"merged PCR into {touched} sheets; sheet_data.json mirrors {index[0]['expiry']}")


if __name__ == "__main__":
    main()
