"""Sector taxonomy for the rollover screen.

REUSES the curated 23-sector taxonomy from `nifty-heatmap-core` (FNO_SECTORS)
rather than inventing a second one that would drift from it.

It is FETCHED at runtime, not vendored. A vendored snapshot is a second copy,
and this project's own history is a catalogue of two-copies-drifting bugs --
including the one that created nifty-heatmap-core in the first place. The cache
is a fallback for no-network, never the primary.

Two adaptations, both deliberate:
  * tickers normalised (board uses Yahoo `ABB.NS`, bhavcopy uses `ABB`)
  * CASH_ONLY names dropped -- no futures, so no rollover

MIN_PEERS exists because a "sector average" over one member IS that member:
the deviation is exactly 0.00, which LOOKS like data. Groups under the floor
get NO sector baseline and are reported as such, never silently averaged.
"""
import importlib.util, ssl, urllib.request
from pathlib import Path

MIN_PEERS = 5
SRC = ("https://raw.githubusercontent.com/abhijeetbishayee-drb/"
       "nifty-heatmap-core/main/nifty_heatmap_core/__init__.py")
_CACHE = Path(__file__).resolve().parent / "data" / "heatmap_core_cache.py"


def _load():
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(SRC, headers={"User-Agent": "rollover-screen"})
        txt = urllib.request.urlopen(req, timeout=25, context=ctx).read().decode("utf-8")
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(txt)
    except Exception as e:
        if not _CACHE.exists():
            raise RuntimeError(f"taxonomy unavailable and no cache: {e}") from e
        print(f"  [sectors] live fetch failed ({type(e).__name__}); using cache")
    spec = importlib.util.spec_from_file_location("_nhc", _CACHE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _norm(t):
    return t[:-3] if t.endswith(".NS") else t


def sector_map():
    """{symbol: sector} for F&O-tradable names only."""
    m = _load()
    cash = {_norm(s) for s in (getattr(m, "CASH_ONLY", []) or [])}
    return {_norm(t): sec for sec, members in m.FNO_SECTORS.items()
            for t in members if _norm(t) not in cash}


def viable_sectors(symbols):
    """Sectors with >= MIN_PEERS members among `symbols`."""
    sm, n = sector_map(), {}
    for s in symbols:
        if s in sm:
            n[sm[s]] = n.get(sm[s], 0) + 1
    return {k for k, v in n.items() if v >= MIN_PEERS}
