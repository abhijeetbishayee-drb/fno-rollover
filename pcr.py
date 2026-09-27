"""Per-stock Put-Call Ratio from the SAME NSE bhavcopy the rollover sheet uses.

No second data source: the files cached in data/bhav/ already carry every stock
option row (FinInstrmTp=="STO", ~30k rows/day across 210 underlyings), so this
adds no new point of failure. Contrast the Nifty PCR tracker, which scrapes
Sensibull live -- that is an intraday need, this is an end-of-day one.

DEFINITION, and why this one:

    PCR(sym, d) = sum(PE open interest) / sum(CE open interest)
                  over ALL live option contracts of that symbol on date d.

Deliberately contract-agnostic. The obvious alternative -- "PCR of the front
contract" -- breaks the moment you compare two dates, because the front
contract is a different contract on each of them, and on expiry day itself the
front contract is dying and its OI is collapsing for reasons that have nothing
to do with positioning. Summing all contracts makes WOW and MOM honest time
comparisons of the same quantity. OI is overwhelmingly concentrated in the
near and next months anyway, so this is not a material dilution.

WOW/MOM DO NOT MEAN WHAT THEY MEAN IN THE NIFTY PCR TRACKER, and the difference
is not cosmetic. There, weekly-PCR and monthly-PCR are two different EXPIRIES
priced on the same day. Stock options have no weeklies -- RELIANCE on 2026-09-25
has exactly three expiries, all monthly, against NIFTY's eight -- so carrying
that definition over would have every one of the 210 names silently reporting
its monthly PCR twice under two labels. That is the BANKNIFTY bug of 2026-09-26,
which was one symbol; here it would have been all of them. So for stocks WOW and
MOM are TIME comparisons: the same measure, one week and one month apart.
"""
import collections
from datetime import date, timedelta

from backfill import fetch


def _d(iso):
    y, m, dd = map(int, iso.split("-"))
    return date(y, m, dd)


def pcr_on(rows):
    """symbol -> (pcr, ce_oi, pe_oi) for one bhavcopy's worth of rows."""
    ce = collections.Counter()
    pe = collections.Counter()
    for r in rows:
        if r["FinInstrmTp"] != "STO":
            continue
        oi = float(r["OpnIntrst"] or 0)
        (ce if r["OptnTp"] == "CE" else pe)[r["TckrSymb"]] += oi
    out = {}
    for sym in set(ce) | set(pe):
        c, p = ce[sym], pe[sym]
        out[sym] = (round(p / c, 4) if c else None, c, p)
    return out


def peak_strikes(rows, after_iso):
    """symbol -> (max-CE-OI strike, max-PE-OI strike) on the first contract
    expiring strictly after `after_iso` -- i.e. the month that carries forward,
    not the one expiring today."""
    live = sorted({r["XpryDt"] for r in rows
                   if r["FinInstrmTp"] == "STO" and r["XpryDt"] > after_iso})
    if not live:
        return {}
    front = live[0]
    agg = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        if r["FinInstrmTp"] != "STO" or r["XpryDt"] != front:
            continue
        key = (r["TckrSymb"], r["OptnTp"])
        agg[key][float(r["StrkPric"])] += float(r["OpnIntrst"] or 0)
    out = {}
    for (sym, tp), strikes in agg.items():
        if not strikes:
            continue
        best = max(strikes.items(), key=lambda kv: kv[1])[0]
        cur = out.setdefault(sym, {"expiry": front})
        cur["maxCE" if tp == "CE" else "maxPE"] = best
    return out


def pcr_near(target_iso, back=10):
    """PCR map for the newest trading day on or before target_iso.

    Walks backwards because the exact date may be a holiday. Returns
    (map, actual_iso) or (None, None) -- never a silent empty dict, so a
    caller cannot mistake 'no file' for 'no open interest'.
    """
    d = _d(target_iso)
    for _ in range(back):
        rows = fetch(d)
        if rows:
            return pcr_on(rows), d.isoformat()
        d -= timedelta(days=1)
    return None, None
