"""Define the four input modalities and explicit time conversion"""

import re
from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo


class Modality(StrEnum):
    """Name observed and future telemetry channels without inventing data"""

    METRIC = "metric"
    LOG = "log"
    TRACE = "trace"
    ALARM = "alarm"


def timestamp_seconds(value: Any, unit: str, timezone: str) -> float:
    """Convert declared timestamps to UTC epoch seconds

    Args:
        value: Epoch value or ISO date-time text.
        unit: s, ms, us, ns or iso.
        timezone: Source timezone for date-time text without offset.
    Returns:
        Finite UTC epoch seconds.
    Raises:
        ValueError: The value or declared unit is invalid.
    """
    if unit == "kibana_display":
        match = re.fullmatch(
            r"([A-Za-z]{3}) (\d{1,2}), (\d{4}) @ (\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)",
            str(value).strip(),
        )
        months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        if match is None or match[1].title() not in months:
            raise ValueError("Expected English Kibana display timestamp")
        month = months.index(match[1].title()) + 1
        value = f"{match[3]}-{month:02d}-{int(match[2]):02d}T{match[4]}"
        unit = "iso"
    if unit == "iso":
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
        result = parsed.timestamp()
    else:
        divisors = {"s": 1, "ms": 1000, "us": 1000000, "ns": 1000000000}
        if unit not in divisors:
            raise ValueError("Unsupported timestamp unit")
        result = float(value) / divisors[unit]
    if not isfinite(result):
        raise ValueError("Non-finite timestamp")
    return result
