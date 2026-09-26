# F&O rollover screen

Screens the NSE stock-futures universe (210 names) for positioning that agrees
or disagrees with price.

## The three steps

1. **MOM gain** — price momentum
2. **Rollover** — were positions carried into the next series
3. **Cost gain/decline** — did carrying them get more or less expensive

A name that rose, rolled above its norm, *and* at rising cost has longs paying
up to stay. One that rose while rollover collapsed has longs leaving into
strength. The disagreements are the signal; agreement is just trend confirmation.

## The three baselines

Each step is measured against: the **previous month**, the stock's **own
trailing average**, and its **sector average**.

## Data

NSE F&O bhavcopy (`OpnIntrst`, `UndrlygPric`, `ClsPric` per contract per
series). Public, historical, no auth, no broker dependency.

**Rollover formula**, validated to two decimals on 9/9 symbols against an
independently published rollover sheet for 2026-08-25:

    rollover % = (next + far OI) / (near + next + far OI)

`next / (near + next)` is *close* and wrong — it misses by up to 1.0pp
(POWERINDIA 91.35 vs 92.32). It fails quietly, which is worse.

## Sectors

Reuses `FNO_SECTORS` from
[`nifty-heatmap-core`](https://github.com/abhijeetbishayee-drb/nifty-heatmap-core),
**fetched at runtime, never vendored** — a second copy would drift. Sectors with
fewer than 5 F&O members get no sector baseline: an average over one member is
that member, and the resulting 0.00 deviation looks like data.

## Files

| | |
|---|---|
| `backfill.py` | historical expiries. Expiry dates are **derived** from each bhavcopy's own ladder, never assumed — the Thursday→Tuesday convention change would break a hardcoded rule |
| `update.py` | weekly snapshot, idempotent |
| `sectors.py` | taxonomy adapter |
| `analyse.py` | the screen |
