"""Weekly snapshot of F&O positioning, for week-on-week comparison.

Rollover proper is MONTHLY by construction -- there is exactly one roll per
series. Its weekly analogue is the OI picture: rollover asks "did positions move
to the next series", the weekly snapshot asks "are positions building or
unwinding". Same question, weekly cadence.

Idempotent: re-running for a date already captured is a no-op, so a duplicated
or retried CI run cannot corrupt the series.
"""
import csv, sys
from datetime import date, timedelta
from pathlib import Path
from backfill import fetch, stf_expiries

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "weekly_snapshots.csv"
FIELDS = ["asof", "symbol", "spot", "near_expiry", "near_px", "next_px", "basis",
          "cost_pct", "rollover_so_far_pct", "oi_near", "oi_next", "oi_far", "oi_total"]


def latest_trading_day(back=10):
    d = date.today()
    for _ in range(back):
        if d.weekday() < 5:
            rows = fetch(d)
            if rows:
                return d, rows
        d -= timedelta(days=1)
    return None, None


def snapshot(rows, asof):
    per = {}
    for r in rows:
        if r["FinInstrmTp"] == "STF":
            per.setdefault(r["TckrSymb"], {})[r["XpryDt"]] = r
    exps = stf_expiries(rows)
    if len(exps) < 2:
        return []
    near, nxt = exps[0], exps[1]
    far = exps[2] if len(exps) > 2 else None
    out = []
    for sym, d in per.items():
        if near not in d or nxt not in d:
            continue
        g = lambda e, k: float(d[e][k] or 0) if e in d else 0.0
        n_oi, x_oi = g(near, "OpnIntrst"), g(nxt, "OpnIntrst")
        f_oi = g(far, "OpnIntrst") if far else 0.0
        npx, xpx, spot = g(near, "ClsPric"), g(nxt, "ClsPric"), g(near, "UndrlygPric")
        tot = n_oi + x_oi + f_oi
        if npx <= 0 or tot <= 0:
            continue
        out.append({
            "asof": asof.isoformat(), "symbol": sym, "spot": spot,
            "near_expiry": near, "near_px": npx, "next_px": xpx,
            "basis": round(npx - spot, 4),
            "cost_pct": round(100 * (xpx - npx) / npx, 4),
            # same formula the expiry-day rollover uses, so a mid-cycle reading
            # is directly comparable to the final number
            "rollover_so_far_pct": round(100 * (x_oi + f_oi) / tot, 4),
            "oi_near": n_oi, "oi_next": x_oi, "oi_far": f_oi, "oi_total": tot,
        })
    return out


def main():
    asof, rows = latest_trading_day()
    if not rows:
        print("no bhavcopy in the last 10 days -- nothing to do")
        return 0
    seen = set()
    if OUT.exists():
        seen = {r["asof"] for r in csv.DictReader(OUT.open())}
    if asof.isoformat() in seen:
        print(f"{asof} already captured -- no-op")
        return 0
    snap = snapshot(rows, asof)
    if not snap:
        print(f"{asof}: no usable rows")
        return 1
    new = not OUT.exists()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(snap)
    print(f"{asof}: captured {len(snap)} symbols (near expiry {snap[0]['near_expiry']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
