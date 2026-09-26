"""Backfill weekly snapshots so the weekly sheet has WOW to compare against.

Reuses update.snapshot() -- one implementation of what a snapshot IS.
Walks back week by week, taking the last trading day of each week (Friday,
stepping back through holidays). Idempotent: dates already present are skipped.
"""
import csv, sys
from datetime import date, timedelta
from pathlib import Path
from backfill import fetch
from update import snapshot, OUT, FIELDS


def last_trading_of_week(anchor):
    """Friday of anchor's week, stepping back to the last day with a bhavcopy."""
    fri = anchor - timedelta(days=(anchor.weekday() - 4) % 7)
    for back in range(5):
        d = fri - timedelta(days=back)
        rows = fetch(d)
        if rows:
            return d, rows
    return None, None


def main(weeks=26):
    have = set()
    if OUT.exists():
        have = {r["asof"] for r in csv.DictReader(OUT.open())}
    anchor = date.today()
    got = []
    for _ in range(weeks):
        d, rows = last_trading_of_week(anchor)
        anchor -= timedelta(days=7)
        if not d:
            continue
        if d.isoformat() in have:
            print(f"  {d} already present")
            continue
        snap = snapshot(rows, d)
        if snap:
            got.extend(snap); have.add(d.isoformat())
            print(f"  {d}: {len(snap)} symbols")
    if not got:
        print("nothing new"); return 0
    existing = list(csv.DictReader(OUT.open())) if OUT.exists() else []
    allrows = existing + got
    allrows.sort(key=lambda r: (r["asof"], r["symbol"]))
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS); w.writeheader(); w.writerows(allrows)
    weeks_n = len({r['asof'] for r in allrows})
    print(f"\nDONE {len(allrows)} rows across {weeks_n} weeks -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 26))
