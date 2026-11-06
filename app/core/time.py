"""Bangladesh time helpers.

Servers usually run in UTC, so "today" must always come from here rather than
from date.today() or datetime.now().
"""

import datetime as dt
from zoneinfo import ZoneInfo

BD_TIMEZONE = ZoneInfo("Asia/Dhaka")


def now_bd() -> dt.datetime:
    return dt.datetime.now(BD_TIMEZONE)


def today_bd() -> dt.date:
    return now_bd().date()
