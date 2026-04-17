"""
Market Close Schedule

Defines weekly UTC close times for all active pairs and provides helper
functions for the pre-close position management job.
"""

import logging
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# All times in UTC. weekday: 0=Monday … 4=Friday
WEEKLY_CLOSE_UTC: Dict[str, dict] = {
    "EUR_USD":    {"weekday": 4, "hour": 21, "minute": 0},
    "USD_JPY":    {"weekday": 4, "hour": 21, "minute": 0},
    "XAU_USD":    {"weekday": 4, "hour": 21, "minute": 0},
    "XAG_USD":    {"weekday": 4, "hour": 21, "minute": 0},
    "BCO_USD":    {"weekday": 4, "hour": 21, "minute": 0},
    "NAS100_USD": {"weekday": 4, "hour": 21, "minute": 0},
    "UK100_GBP":  {"weekday": 4, "hour": 16, "minute": 30},
    "JP225_USD":  {"weekday": 4, "hour":  6, "minute":  0},
}

# Block window: 65 minutes before close → entry blocked
# Close window: 60 minutes before close → positions closed
BLOCK_MINUTES_BEFORE = 65
CLOSE_MINUTES_BEFORE = 60


def fetch_holidays() -> List[dict]:
    """
    Fetch the market_holidays document from Firestore.
    Returns a list of holiday dicts: {date, label, affects}.
    Returns [] on any error (Firestore unavailable, doc missing, etc.).
    """
    try:
        from ..firebase_setup import db
        doc = db.collection("config").document("market_holidays").get()
        if not doc.exists:
            return []
        data = doc.to_dict()
        return data.get("holidays", [])
    except Exception as e:
        logger.warning(f"fetch_holidays: could not read Firestore: {e}")
        return []


def is_next_day_closure(pair: str, check_date: date, holidays: List[dict]) -> bool:
    """
    Returns True if the calendar day after check_date is a non-trading day
    for the given pair (weekend or Firestore holiday).

    Args:
        pair: Instrument name, e.g. "XAU_USD"
        check_date: The date whose *next* day is evaluated
        holidays: List of holiday dicts from fetch_holidays()
    """
    tomorrow = check_date + timedelta(days=1)
    tomorrow_weekday = tomorrow.weekday()  # 0=Monday, 6=Sunday

    # Weekend gap
    if tomorrow_weekday in (5, 6):  # Saturday or Sunday
        return True

    # Monday holidays: intentionally ignored (weekend gap already covers them).
    if tomorrow_weekday == 0:
        return False

    # Check Firestore holiday list
    tomorrow_str = tomorrow.isoformat()  # "YYYY-MM-DD"
    for h in holidays:
        if h.get("date") != tomorrow_str:
            continue
        affects = h.get("affects", "all")
        if affects == "all":
            return True
        if isinstance(affects, list) and pair in affects:
            return True

    return False


def get_preclose_pairs(now: datetime) -> Dict[str, str]:
    """
    Compute which pairs are currently in a pre-close window.

    Returns a dict mapping symbol → phase:
      'block'  — T-65 to T-61 min  (new entries should be blocked, no close yet)
      'close'  — T-60 to T+0 min   (open positions should be closed)

    `now` MUST be a UTC-aware datetime.
    """
    if now.tzinfo is None:
        raise ValueError("get_preclose_pairs: `now` must be UTC-aware")

    today = now.date()
    holidays = fetch_holidays()
    result: Dict[str, str] = {}

    for pair, sched in WEEKLY_CLOSE_UTC.items():
        # Build the close datetime for today's weekday if it matches
        if now.weekday() != sched["weekday"]:
            continue

        # Also require that tomorrow is a non-trading day for this pair
        if not is_next_day_closure(pair, today, holidays):
            continue

        close_dt = datetime(
            today.year, today.month, today.day,
            sched["hour"], sched["minute"], 0,
            tzinfo=timezone.utc
        )

        minutes_to_close = (close_dt - now).total_seconds() / 60

        if 0 <= minutes_to_close <= BLOCK_MINUTES_BEFORE:
            if minutes_to_close <= CLOSE_MINUTES_BEFORE:
                result[pair] = "close"
            else:
                result[pair] = "block"

    return result


def get_holiday_preclose_pairs(now: datetime) -> Dict[str, str]:
    """
    On non-Friday weekdays, check if tomorrow is a Firestore holiday.
    When it is, return pairs that are within the block/close window of
    their *today* close time (using WEEKLY_CLOSE_UTC keyed by today's weekday).

    This handles e.g. Thursday before Good Friday: the pair's weekday close
    schedule entry for Thursday would need to exist — but since all pairs close
    on Friday (weekday=4), there is no Thursday entry.  Instead we synthesise
    a 21:00 UTC threshold for all affected pairs, consistent with the
    "day before holiday" trigger.

    We use 21:00 UTC as the default holiday-eve close time (same as the
    Forex/Metals Friday close).  UK100 and JP225 have earlier closes on
    Friday but for holiday-eve we apply the same 21:00 cutoff conservatively
    (they typically have their own holiday schedules that match).
    """
    if now.tzinfo is None:
        raise ValueError("get_holiday_preclose_pairs: `now` must be UTC-aware")

    # Friday already handled by get_preclose_pairs() above
    if now.weekday() == 4:
        return {}

    today = now.date()
    holidays = fetch_holidays()
    result: Dict[str, str] = {}

    for pair in WEEKLY_CLOSE_UTC:
        if not is_next_day_closure(pair, today, holidays):
            continue

        # Holiday-eve close: use 21:00 UTC today
        close_dt = datetime(
            today.year, today.month, today.day,
            21, 0, 0,
            tzinfo=timezone.utc
        )

        minutes_to_close = (close_dt - now).total_seconds() / 60

        if 0 <= minutes_to_close <= BLOCK_MINUTES_BEFORE:
            if minutes_to_close <= CLOSE_MINUTES_BEFORE:
                result[pair] = "close"
            else:
                result[pair] = "block"

    return result


def get_all_preclose_pairs(now: datetime) -> Dict[str, str]:
    """
    Combine weekly Friday closes and holiday-eve closes.
    Returns {symbol: phase} for all pairs currently in a pre-close window.
    """
    result = get_preclose_pairs(now)
    result.update(get_holiday_preclose_pairs(now))
    return result
