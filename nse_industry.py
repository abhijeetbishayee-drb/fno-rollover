"""NSE's OWN industry classification -- a second, independent source of truth.

Everything else in this repo's sector handling descends from one place: the
heatmap's FNO_SECTORS. parity_check's [1]-[4] therefore pass by construction,
because sector_map() is a filtered VIEW of that same dict. They prove the
derivation is intact; they cannot prove the taxonomy is right.

This module supplies something genuinely independent. NSE publishes an
`Industry` column in its index constituent files, produced by NSE's own
classification process with no causal link to the heatmap. Disagreement here is
real information rather than a self-consistency tautology.

Source is the nsearchives subdomain, which is NOT behind the Akamai wall that
blocks nseindia.com itself -- the same route backfill.py uses for bhavcopy.
"""
import csv, io, ssl, urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parent
# COMMITTED, unlike sectors.py's heatmap cache. If this were gitignored, a
# prolonged NSE outage would turn check [6] into a permanent silent SKIP --
# a gate that stops gating and says so only in logs nobody reads. Committed,
# the check keeps running on the last known-good classification, and the
# weekly job refreshes the file.
CACHE = ROOT / "data" / "nse_industry_cache.csv"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
# Total-market list: widest coverage (~755 names), so every F&O name is in it.
URL = "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"

_MEMO = {}


def industry_map(refresh=True):
    """{symbol: NSE industry}. Returns {} if unavailable -- callers must treat
    empty as "did not run", never as "nothing disagreed"."""
    if "t" in _MEMO:
        return _MEMO["t"]
    text = None
    if refresh:
        try:
            req = urllib.request.Request(URL, headers={
                "User-Agent": UA, "Referer": "https://www.nseindia.com/", "Accept": "*/*"})
            ctx = ssl.create_default_context(cafile=certifi.where())
            text = urllib.request.urlopen(req, timeout=25, context=ctx).read().decode("utf-8")
            if "Industry" not in text.split("\n", 1)[0]:
                raise RuntimeError("no Industry column -- upstream shape changed")
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(text)
        except Exception as e:
            print(f"  [nse] live fetch failed ({type(e).__name__}: {e})")
            text = None
    if text is None:
        if not CACHE.exists():
            return {}
        text = CACHE.read_text()
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        sym, ind = (r.get("Symbol") or "").strip(), (r.get("Industry") or "").strip()
        if sym and ind:
            out[sym] = ind
    _MEMO["t"] = out
    return out
