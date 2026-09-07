"""
READ-ONLY probe: how far back will Oanda serve BCO_USD 5-minute candles?
=======================================================================
A safe dry-run of the backwards-paging logic in download_forex_max_history.py,
narrowed to one pair and one timeframe.

⚠️ This script WRITES NOTHING to data/forex_raw/. It pages entirely in memory
and only prints. Safe to run while the bot is live — unlike the real backfill,
which races the 5-minute cron for the same files.

What it tells you: how many bars Oanda actually returns, the oldest timestamp
reachable, the calendar span that covers, and whether the 100,000-row target in
MAX_ROWS is achievable for this instrument or whether history runs out first.

Usage:
    python scripts/probe_bco_5m_history.py                  # probe to the 100k target
    python scripts/probe_bco_5m_history.py --target 20000   # stop sooner (quicker)
    python scripts/probe_bco_5m_history.py --pair XAU_USD   # try another pair
    python scripts/probe_bco_5m_history.py --tf M15         # try another timeframe
    python scripts/probe_bco_5m_history.py --save out.csv   # optional dump, NEVER
                                                            # into data/forex_raw
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from oandapyV20.endpoints import instruments

sys.path.insert(0, str(Path(__file__).parent))
from download_forex import DATA_DIR, MAX_ROWS, get_oanda_api, parse_candles

PAGE = 5000
MAX_PAGES = 60
BARS_PER_WEEK = {"M5": 1440, "M15": 480, "H1": 120, "H4": 30}
SUFFIX = {"M5": "5_Min", "M15": "15_Min", "H1": "1_Hour", "H4": "4_Hour"}


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="BCO_USD")
    ap.add_argument("--tf", default="M5", choices=list(SUFFIX))
    ap.add_argument("--target", type=int, default=None,
                    help="stop after this many bars (default: the MAX_ROWS cap)")
    ap.add_argument("--save", default="",
                    help="optional CSV dump; refused if it points into data/forex_raw")
    args = ap.parse_args()

    target = args.target or MAX_ROWS.get(args.tf, 100_000)

    if args.save:
        dest = Path(args.save).resolve()
        if DATA_DIR.resolve() in dest.parents:
            sys.exit(f"Refusing to write into {DATA_DIR} — this probe must not touch live data.")

    api = get_oanda_api()
    if not api:
        sys.exit("No Oanda API — check OANDA_ACCESS_TOKEN in .env or backend/.env")

    local = DATA_DIR / f"{args.pair}_{SUFFIX[args.tf]}.csv"
    if local.exists():
        d = pd.read_csv(local, usecols=["Date"])
        d["Date"] = pd.to_datetime(d["Date"])
        print(f"Local file : {local.name} — {len(d):,} rows, "
              f"{d.Date.min()} → {d.Date.max()}")
    else:
        print(f"Local file : {local.name} — not present")

    print(f"Probing    : {args.pair} {args.tf}, target {target:,} bars, "
          f"{PAGE:,} per request (READ-ONLY)\n")

    cursor = datetime.now(timezone.utc).replace(tzinfo=None)
    frames, total, pages = [], 0, 0
    t0 = time.time()

    while total < target and pages < MAX_PAGES:
        try:
            candles = fetch_before(api, args.pair, args.tf, cursor)
        except Exception as e:
            print(f"  page {pages + 1}: request failed — {e}")
            break

        records = parse_candles(candles)
        if not records:
            print(f"  page {pages + 1}: Oanda returned nothing before {cursor} "
                  f"— history exhausted")
            break

        df = pd.DataFrame(records)
        df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_convert(None)
        df = df[df["Date"] < cursor]
        if df.empty:
            print(f"  page {pages + 1}: no bars older than {cursor} — history exhausted")
            break

        frames.append(df)
        total += len(df)
        pages += 1
        cursor = df["Date"].min()
        print(f"  page {pages:2d}: +{len(df):5,} bars  oldest now {cursor}  "
              f"(total {total:,})")
        time.sleep(0.2)

    if not frames:
        sys.exit("\nNo data returned at all — check the instrument name and credentials.")

    all_df = (pd.concat(frames)
                .drop_duplicates(subset=["Date"])
                .sort_values("Date"))
    oldest, newest = all_df.Date.min(), all_df.Date.max()
    span_days = (newest - oldest).days
    per_week = BARS_PER_WEEK.get(args.tf, 1440)

    print("\n" + "=" * 62)
    print(f"RESULT for {args.pair} {args.tf}")
    print("=" * 62)
    print(f"  bars retrieved : {len(all_df):,} over {pages} request(s), "
          f"{time.time() - t0:.1f}s")
    print(f"  oldest bar     : {oldest}")
    print(f"  newest bar     : {newest}")
    print(f"  calendar span  : {span_days:,} days (~{span_days / 30.4:.1f} months)")
    print(f"  target         : {target:,} bars "
          f"(~{target / per_week / 4.33:.1f} months of trading)")
    if len(all_df) >= target:
        print(f"  ✅ target reachable — the backfill will fill this file completely")
    else:
        print(f"  ⚠️  history ran out at {len(all_df):,} bars "
              f"({target - len(all_df):,} short of target)")
        print(f"     Not a failure: the backfill stops cleanly and keeps what exists.")

    gaps = all_df.Date.diff().dropna()
    if len(gaps):
        big = gaps[gaps > pd.Timedelta(hours=6)]
        print(f"  weekend/holiday breaks > 6h : {len(big)}")

    if args.save:
        all_df.to_csv(args.save, index=False)
        print(f"\n  dumped to {args.save} (live data untouched)")


if __name__ == "__main__":
    main()
