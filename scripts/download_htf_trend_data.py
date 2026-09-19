"""
One-off HTF (H4 / Daily) downloader for the HTF-trend-filter research question.
================================================================================
Pulls ~2 years of H4 and Daily candles from Oanda for the 5 currently-active
live pairs (XAU_USD, XAG_USD, JP225_USD, NAS100_USD, BCO_USD) and saves them
to their OWN files:

    data/forex_raw/{PAIR}_4_Hour.csv
    data/forex_raw/{PAIR}_Daily.csv

This does NOT touch, read from, or write to the production `_15_Min` /
`_5_Min` files, and it is NOT wired into `download_forex.py` (the 5-minute
cron). CLAUDE.md documents that H4 was deliberately dropped from the cron in
Sep 2026 because nothing live reads it — this script is a separate, standalone,
one-off research pull, same category as `download_forex_max_history.py`, whose
auth/pagination pattern it reuses.

Paging: Oanda returns at most 5000 candles per request. Starting from "now",
this walks BACKWARDS via the `to` param, prepending each page, until either
~2 years of history is covered or Oanda stops returning older bars. Same
column layout as download_forex.py (Date, Open, High, Low, Close, Volume),
alignmentTimezone=America/New_York to match the production downloader.

Usage:
    python scripts/download_htf_trend_data.py                # H4 + Daily, all 5 pairs
    python scripts/download_htf_trend_data.py --gran H4       # one granularity
    python scripts/download_htf_trend_data.py --years 2.5
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from oandapyV20.endpoints import instruments

sys.path.insert(0, str(Path(__file__).parent))
from download_forex import DATA_DIR, get_oanda_api, parse_candles

PAIRS = ["XAU_USD", "XAG_USD", "JP225_USD", "NAS100_USD", "BCO_USD"]
GRAN_SUFFIX = {"H4": "4_Hour", "D": "Daily"}
PAGE = 5000
MAX_PAGES = 20  # generous headroom; H4 2yrs ~= 2,920 candles = 1 page, D ~= 500 candles = 1 page


def fetch_before(api, instrument, granularity, before_ts):
    params = {
        "granularity": granularity,
        "alignmentTimezone": "America/New_York",
        "count": PAGE,
        "to": before_ts.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
    }
    r = instruments.InstrumentsCandles(instrument=instrument, params=params)
    api.request(r)
    return r.response.get("candles", [])


def download_one(api, symbol, granularity, cutoff, dry_run=False):
    path = DATA_DIR / f"{symbol}_{GRAN_SUFFIX[granularity]}.csv"
    print(f"  [{symbol} {granularity}] target: back to {cutoff.date()} -> {path.name}")
    if dry_run:
        return 0

    before = datetime.now(timezone.utc)
    frames = []
    pages = 0
    while pages < MAX_PAGES:
        try:
            candles = fetch_before(api, symbol, granularity, before)
        except Exception as e:
            print(f"    page {pages + 1} failed ({e}) — stopping")
            break
        records = parse_candles(candles)
        if not records:
            print(f"    Oanda returned no further history before {before}")
            break
        df = pd.DataFrame(records)
        df["Date"] = pd.to_datetime(df["Date"], utc=True)
        frames.append(df)
        oldest = df["Date"].min()
        pages += 1
        print(f"    page {pages}: +{len(df):,} bars, oldest so far {oldest}")
        if oldest <= cutoff:
            break
        before = oldest
        time.sleep(0.2)

    if not frames:
        print(f"  [{symbol} {granularity}] nothing fetched")
        return 0

    out = (pd.concat(frames)
             .drop_duplicates(subset=["Date"], keep="last")
             .sort_values("Date"))
    out = out[out["Date"] >= cutoff]
    out["Date"] = out["Date"].dt.tz_convert(None)
    out.to_csv(path, index=False)
    print(f"  [{symbol} {granularity}] saved {len(out):,} rows, "
          f"{out['Date'].min()} -> {out['Date'].max()} -> {path}")
    return len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gran", default="H4,D", help="comma-separated Oanda granularities")
    ap.add_argument("--pairs", default=",".join(PAIRS), help="comma-separated symbols")
    ap.add_argument("--years", type=float, default=2.0, help="years of history to pull")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api = get_oanda_api()
    if not api:
        sys.exit("No Oanda API — check credentials.")

    grans = [g.strip() for g in args.gran.split(",")]
    pairs = [p.strip() for p in args.pairs.split(",")]
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(args.years * 365.25))

    print(f"Downloading {grans} for {pairs}, cutoff {cutoff.date()}"
          f"{' (DRY RUN)' if args.dry_run else ''}\n")
    total = 0
    for symbol in pairs:
        print(f"{symbol}")
        for gran in grans:
            total += download_one(api, symbol, gran, cutoff, args.dry_run)
        print()
    print(f"Done. {total:,} rows written." if not args.dry_run else "Dry run complete.")


if __name__ == "__main__":
    main()
