"""Backfill F&O rollover metrics from NSE bhavcopy. Read-only, no broker, no orders.

Expiry dates are DERIVED, never assumed: a bhavcopy's nearest STF expiry IS that
month's expiry, so probing one mid-month file per month yields the real date and
survives the Thursday->Tuesday convention change inside the backfill window.
"""
import csv, io, ssl, sys, time, zipfile, urllib.request
import certifi
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "bhav"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d}_F_0000.csv.zip"


def fetch(d: date):
    """Return list-of-dicts for a trading date, or None. Cached on disk."""
    tag = d.strftime("%Y%m%d")
    cached = CACHE / f"{tag}.csv"
    if cached.exists():
        return list(csv.DictReader(cached.open()))
    req = urllib.request.Request(URL.format(d=tag), headers={
        "User-Agent": UA, "Referer": "https://www.nseindia.com/", "Accept": "*/*"})
    # SSL context is EXPLICIT: this interpreter has no usable default CA bundle,
    # so a bare urlopen raises CERTIFICATE_VERIFY_FAILED. Found the hard way --
    # the original `except Exception: return None` swallowed it and reported
    # "expiry None" twelve times with exit code 0. Never catch broadly here.
    CTX = ssl.create_default_context(cafile=certifi.where())
    try:
        raw = urllib.request.urlopen(req, timeout=30, context=CTX).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None          # genuinely no file: holiday / non-trading day
        raise                    # anything else is a real fault -- surface it
    if len(raw) < 50_000:
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return None
    text = zf.read(zf.namelist()[0]).decode("utf-8", "replace")
    cached.parent.mkdir(parents=True, exist_ok=True)   # gitignored: absent on a fresh runner
    cached.write_text(text)
    time.sleep(1.2)                      # be polite to NSE
    return list(csv.DictReader(io.StringIO(text)))


def stf_expiries(rows):
    return sorted({r["XpryDt"] for r in rows if r["FinInstrmTp"] == "STF"})


def expiry_of_month(y, m):
    """Probe mid-month; the nearest STF expiry in that file IS this month's expiry."""
    for day in (10, 11, 12, 13, 14, 9, 8, 15, 16, 17):
        try:
            d = date(y, m, day)
        except ValueError:
            continue
        if d.weekday() >= 5:
            continue
        rows = fetch(d)
        if not rows:
            continue
        exps = stf_expiries(rows)
        if not exps:
            continue
        near = exps[0]
        if near.startswith(f"{y:04d}-{m:02d}"):
            return near
        return None
    return None


def metrics_on(expiry_iso):
    """Compute per-symbol rollover metrics from the expiry-day bhavcopy."""
    y, m, dd = map(int, expiry_iso.split("-"))
    rows = fetch(date(y, m, dd))
    if not rows:
        return None
    per = {}
    for r in rows:
        if r["FinInstrmTp"] != "STF":
            continue
        per.setdefault(r["TckrSymb"], {})[r["XpryDt"]] = r
    exps = stf_expiries(rows)
    if len(exps) < 3:
        return None
    near, nxt, far = exps[0], exps[1], exps[2]
    out = []
    for sym, d in per.items():
        if near not in d or nxt not in d:
            continue
        oi = lambda e: float(d[e]["OpnIntrst"] or 0) if e in d else 0.0
        px = lambda e: float(d[e]["ClsPric"] or 0) if e in d else 0.0
        n_oi, x_oi, f_oi = oi(near), oi(nxt), oi(far)
        tot = n_oi + x_oi + f_oi
        if tot <= 0 or px(near) <= 0:
            continue
        out.append({
            "expiry": expiry_iso,
            "symbol": sym,
            "spot": float(d[near]["UndrlygPric"] or 0),
            "near_px": px(near), "next_px": px(nxt),
            "basis": round(px(near) - float(d[near]["UndrlygPric"] or 0), 4),
            # VALIDATED against the 2026-08-25 published sheet on 9/9 symbols:
            "rollover_pct": round(100.0 * (x_oi + f_oi) / tot, 4),
            "rollover_cost_pct": round(100.0 * (px(nxt) - px(near)) / px(near), 4),
            "oi_near": n_oi, "oi_next": x_oi, "oi_far": f_oi,
        })
    return out


def extend(look_back=3):
    """Append any COMPLETED expiry missing from rollover_history.csv.

    This exists because nothing in the weekly job extended the monthly series:
    update.py only appends weekly snapshots, and main() below is a full REWRITE
    that nobody runs on a schedule. The monthly sheet was therefore structurally
    frozen at whatever expiry the last manual backfill produced -- it sat on
    2026-08-25 while the September roll completed on 2026-09-29, and the weekly
    view kept updating beside it, which made the whole page look alive.

    Append-only and idempotent by design: never truncates, never reorders, and
    re-running after a completed expiry is already present is a no-op. main()
    must stay the manual, deliberate path -- it opens the file with "w".
    """
    outp = ROOT / "data" / "rollover_history.csv"
    existing, fields = [], None
    if outp.exists():
        rd = csv.DictReader(outp.open())
        existing, fields = list(rd), rd.fieldnames
    have = {r["expiry"] for r in existing}
    today = date.today()

    wanted = []
    y, m = today.year, today.month
    for _ in range(look_back):
        e = expiry_of_month(y, m)
        # <= today, NOT < today. The job now runs on Tuesday evening and the
        # monthly expiry IS a Tuesday, so a "strictly before today" test would
        # skip the very roll the schedule exists to catch and defer it a week.
        # Completeness is decided by the BHAVCOPY, not the calendar: NSE
        # publishes it only after the close, so metrics_on() returning rows is
        # itself proof the session finished. Run too early and it returns None,
        # which warns and appends nothing.
        if e and e <= today.isoformat() and e not in have:
            wanted.append(e)
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    if not wanted:
        print(f"rollover_history.csv: up to date ({len(have)} expiries, "
              f"newest {max(have) if have else 'none'})")
        return 0

    added, stale = [], []
    for e in sorted(wanted):
        got = metrics_on(e)
        if not got:
            # Missing on the expiry day ITSELF is a timing race, not a fault:
            # the bhavcopy simply is not out yet and the next run will get it.
            # Missing for an expiry already in the PAST is a real fault.
            when = "not published yet" if e == today.isoformat() else "MISSING"
            print(f"  WARN expiry {e}: bhavcopy {when} -- not appended")
            if e != today.isoformat():
                stale.append(e)
            continue
        existing.extend(got)
        added.append((e, len(got)))
    if not added:
        # Exit non-zero only for the real fault. Failing on the timing race
        # would abort the job AFTER update.py captured a valid weekly snapshot,
        # discarding it over a race that resolves itself on the next run.
        return 1 if stale else 0
    fields = fields or list(added and existing[0].keys())
    existing.sort(key=lambda r: (r["expiry"], r["symbol"]))
    with outp.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(existing)
    for e, n in added:
        print(f"  + expiry {e}: {n} symbols")
    print(f"rollover_history.csv: {len(existing)} rows, "
          f"{len(have) + len(added)} expiries (+{len(added)})")
    return 0


def main(n=12):
    today = date.today()
    months, y, m = [], today.year, today.month
    for _ in range(n + 2):
        months.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    expiries = []
    for (yy, mm) in months:
        e = expiry_of_month(yy, mm)
        print(f"  probe {yy}-{mm:02d} -> expiry {e}", flush=True)
        if e and e < today.isoformat():
            expiries.append(e)
        if len(expiries) >= n:
            break
    rows = []
    for e in expiries:
        got = metrics_on(e)
        print(f"  expiry {e}: {len(got) if got else 0} symbols", flush=True)
        if got:
            rows.extend(got)
    outp = ROOT / "data" / "rollover_history.csv"
    if rows:
        with outp.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    print(f"\nDONE {len(rows)} rows across {len(expiries)} expiries -> {outp}")


if __name__ == "__main__":
    if "--extend" in sys.argv:
        sys.exit(extend())
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
