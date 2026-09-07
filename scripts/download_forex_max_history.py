"""
One-time Oanda backfill — pages BACKWARDS to fill each pair's history.
====================================================================
`download_forex.py` only ever fetches forward from the newest bar it already
has, so it can never recover history that was trimmed away. Run this once after
raising MAX_ROWS to fill the files back out; the regular 5-minute cron keeps
them topped up afterwards.

Why this exists: the old version of this script used yfinance, capped 15m data
at ~60 days, and wrote to `{symbol}.csv` rather than `{symbol}_15_Min.csv`, so
its output was never read by anything. This one talks to Oanda, matches
download_forex.py's file naming and column layout exactly, and is idempotent.

How it pages: Oanda returns at most 5000 candles per request. Starting from the
OLDEST bar currently on disk, it requests the 5000 candles ending just before
that, prepends them, and repeats — walking backwards until Oanda stops
returning new bars or the per-timeframe target is reached. Incomplete candles
are dropped, rows are deduped on Date and sorted, so re-running is safe.

Targets match MAX_ROWS in download_forex.py: 100k rows of 5m (~16 months) and
100k of 15m (~4 years). Runtime is roughly one request per 5000 bars per pair
per timeframe — expect a few minutes and a few hundred requests in total.

Usage:
    python scripts/download_forex_max_history.py              # 5m + 15m, all pairs
    python scripts/download_forex_max_history.py --tf M15     # one timeframe
    python scripts/download_forex_max_history.py --pairs XAU_USD,BCO_USD
    python scripts/download_forex_max_history.py --dry-run    # report only
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from oandapyV20.endpoints import instruments

sys.path.insert(0, str(Path(__file__).parent))
from download_forex import DATA_DIR, MAX_ROWS, get_oanda_api, load_pairs, parse_candles

SUFFIX = {"M5": "5_Min", "M15": "15_Min", "H1": "1_Hour", "H4": "4_Hour", "M3": "3_Min"}
PAGE = 5000
MAX_PAGES = 60          # hard stop; 60 x 5000 = 300k bars per pair/timeframe


def fetch_before(api, instrument, granularity, before_ts):
    """The PAGE candles ending just before `before_ts`. Empty list when exhausted."""
    params = {
        "granularity": granularity,
        "alignmentTimezone": "America/New_York",   # must match download_forex.py
        "count": PAGE,
        "to": before_ts.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
    }
    r = instruments.InstrumentsCandles(instrument=instrument, params=params)
    api.request(r)
    return r.response.get("candles", [])


def backfill(api, symbol, oanda_symbol, granularity, dry_run=False):
    path = DATA_DIR / f"{symbol}_{SUFFIX[granularity]}.csv"
    target = MAX_ROWS.get(granularity, 20000)

    if not path.exists():
        print(f"  [{symbol} {granularity}] no existing file — run download_forex.py first")
        return 0

    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"])
    before = len(df)
    if before >= target:
        print(f"  [{symbol} {granularity}] already {before:,} rows (target {target:,}) — skip")
        return 0

    print(f"  [{symbol} {granularity}] {before:,} rows, oldest {df.Date.min()} "
          f"→ target {target:,}")
    if dry_run:
        return 0

    pages = 0
    while len(df) < target and pages < MAX_PAGES:
        oldest = df["Date"].min()
        try:
            candles = fetch_before(api, oanda_symbol, granularity, oldest)
        except Exception as e:
            print(f"    page {pages + 1} failed ({e}) — stopping this timeframe")
            break

        records = parse_candles(candles)
        if not records:
            print(f"    Oanda returned no further history before {oldest}")
            break

        new = pd.DataFrame(records)
        new["Date"] = pd.to_datetime(new["Date"], utc=True).dt.tz_convert(None)
        new = new[new["Date"] < oldest]
        if new.empty:
            print(f"    no bars older than {oldest} — history exhausted")
            break

        df = (pd.concat([new, df])
                .drop_duplicates(subset=["Date"], keep="last")
                .sort_values("Date"))
        pages += 1
        print(f"    page {pages}: +{len(new):,} bars, now {len(df):,}, "
              f"oldest {df.Date.min()}")
        time.sleep(0.2)      # rate-limit kindness

    if len(df) > target:
        df = df.tail(target)

    gained = len(df) - before
    if gained > 0:
        df.to_csv(path, index=False)
        print(f"  [{symbol} {granularity}] +{gained:,} rows → {len(df):,} "
              f"(from {df.Date.min()})")
    else:
        print(f"  [{symbol} {granularity}] nothing gained")
    return gained


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="M5,M15", help="comma-separated Oanda granularities")
    ap.add_argument("--pairs", default="", help="comma-separated symbols (default: all)")
    ap.add_argument("--dry-run", action="store_true", help="report gaps, fetch nothing")
    args = ap.parse_args()

    api = get_oanda_api()
    if not api:
        sys.exit("No Oanda API — check credentials.")

    pairs = load_pairs()
    if args.pairs:
        wanted = {p.strip() for p in args.pairs.split(",")}
        pairs = [p for p in pairs if p["symbol"] in wanted]
    tfs = [t.strip() for t in args.tf.split(",")]

    print(f"Backfilling {len(pairs)} pairs x {tfs}"
          f"{' (DRY RUN)' if args.dry_run else ''}\n")
    total = 0
    for pair in pairs:
        symbol, oanda_symbol = pair["symbol"], pair.get("oanda_symbol")
        if not oanda_symbol:
            continue
        print(f"{pair['name']} ({oanda_symbol})")
        for tf in tfs:
            total += backfill(api, symbol, oanda_symbol, tf, args.dry_run)
        print()

    print(f"Done. {total:,} bars added." if not args.dry_run else "Dry run complete.")
    if total:
        print("The 5-minute cron keeps these topped up from here — do not re-run.")


if __name__ == "__main__":
    main()
