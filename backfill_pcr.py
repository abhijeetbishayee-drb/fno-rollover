"""Build data/pcr_history.csv -- the committed, incremental PCR series.

Mirrors how data/rollover_history.csv already works, and for the same reason:
data/bhav/ is gitignored, so a fresh CI runner holds no bhavcopies. Computing
PCR straight from the cache would make every weekly run re-download ~56 files
(~400 MB) from NSE. Instead the derived numbers are committed, and a run only
fetches dates the CSV does not already cover -- after a new expiry that is two.

Two rows per expiry per symbol:
  kind="on" -- the expiry day itself, plus peak-OI strikes on the contract that
               carries forward (the one expiring AFTER this expiry, since the
               one expiring today is dying and its OI says nothing).
  kind="wk" -- the nearest trading day on or before expiry minus 7 days.

MOM needs no row of its own: it is this expiry's "on" against the previous
expiry's "on", both already here.
"""
import csv, json, sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "pcr_history.csv"
COLS = ["expiry", "kind", "asof", "symbol", "pcr", "ce", "pe",
        "max_ce", "max_pe", "opt_expiry"]

# The weekly view runs on its own date grid (weekly_snapshots.csv), not on
# expiries, so it needs its own series. Borrowing the monthly expiry-day number
# would put a reading up to five weeks stale next to a week-on-week column.
SNAP = ROOT / "data" / "weekly_snapshots.csv"
WOUT = ROOT / "data" / "pcr_weekly.csv"
WCOLS = ["asof", "symbol", "pcr", "ce", "pe"]

from backfill import fetch                                   # noqa: E402
from pcr import pcr_on, peak_strikes                         # noqa: E402


def _d(iso):
    y, m, dd = map(int, iso.split("-"))
    return date(y, m, dd)


def load():
    if not OUT.exists():
        return []
    return list(csv.DictReader(OUT.open()))


def rows_for(expiry, kind, back=10):
    """Fetch and reduce one (expiry, kind) slice, or None if no file exists."""
    target = _d(expiry) if kind == "on" else _d(expiry) - timedelta(days=7)
    for _ in range(back):
        raw = fetch(target)
        if raw:
            break
        target -= timedelta(days=1)
    else:
        return None
    pm = pcr_on(raw)
    pk = peak_strikes(raw, expiry) if kind == "on" else {}
    out = []
    for sym, (val, ce, pe) in sorted(pm.items()):
        if val is None:
            continue                      # no calls open: a ratio would be a lie
        k = pk.get(sym, {})
        out.append({"expiry": expiry, "kind": kind, "asof": target.isoformat(),
                    "symbol": sym, "pcr": val, "ce": int(ce), "pe": int(pe),
                    "max_ce": k.get("maxCE", ""), "max_pe": k.get("maxPE", ""),
                    "opt_expiry": k.get("expiry", "")})
    return out


def weekly():
    """PCR at every weekly snapshot date. Incremental, like the expiry series."""
    if not SNAP.exists():
        print("  no weekly_snapshots.csv -- skipping weekly PCR")
        return
    dates = sorted({r["asof"] for r in csv.DictReader(SNAP.open())})
    have = list(csv.DictReader(WOUT.open())) if WOUT.exists() else []
    seen = {r["asof"] for r in have}
    added = 0
    for d in dates:
        if d in seen:
            continue
        raw = fetch(_d(d))
        if not raw:
            print(f"  WARN no bhavcopy on weekly date {d}")
            continue
        for sym, (val, ce, pe) in sorted(pcr_on(raw).items()):
            if val is None:
                continue
            have.append({"asof": d, "symbol": sym, "pcr": val,
                         "ce": int(ce), "pe": int(pe)})
            added += 1
        print(f"  + weekly {d}", flush=True)
    have.sort(key=lambda r: (r["asof"], r["symbol"]))
    with WOUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=WCOLS)
        w.writeheader()
        w.writerows(have)
    print(f"pcr_weekly.csv: {len(have)} rows ({added} new) across "
          f"{len({r['asof'] for r in have})} weeks")


def main():
    expiries = [e["expiry"] for e in
                json.loads((ROOT / "expiries.json").read_text())["expiries"]]
    have = load()
    seen = {(r["expiry"], r["kind"]) for r in have}
    added = 0
    for e in sorted(expiries):
        for kind in ("on", "wk"):
            if (e, kind) in seen:
                continue
            got = rows_for(e, kind)
            if got is None:
                print(f"  WARN no bhavcopy for {e}/{kind}")
                continue
            have.extend(got)
            added += len(got)
            print(f"  + {e}/{kind}: {len(got)} symbols", flush=True)
    have.sort(key=lambda r: (r["expiry"], r["kind"], r["symbol"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(have)
    print(f"pcr_history.csv: {len(have)} rows ({added} new) across "
          f"{len({r['expiry'] for r in have})} expiries")
    weekly()


if __name__ == "__main__":
    sys.exit(main())
