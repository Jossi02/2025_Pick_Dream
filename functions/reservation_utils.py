import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional


KST = timezone(timedelta(hours=9))

_BUILDING_MAP = {
    "덕문관": "5",
    "집현관": "7",
    "예지관": "4",
}


def extract_room_id(text: Any) -> Optional[str]:
    """Return the numeric room ID used by the Android app (for example, 7202)."""
    if text is None:
        return None

    normalized = str(text).strip()
    if not normalized:
        return None

    for name, number in _BUILDING_MAP.items():
        normalized = normalized.replace(name, f"{number}강의동")

    match = re.search(
        r"(?<!\d)(\d)\s*(?:강의동|동|관)?\s*[-\s]?\s*(\d{2,3})(?!\d)\s*호?",
        normalized,
    )
    if match:
        return match.group(1) + match.group(2)

    match = re.search(r"(?<!\d)(\d{3,4})(?!\d)\s*호?", normalized)
    return match.group(1) if match else None


def reservation_room_id(document_id: str, room_data: Mapping[str, Any]) -> str:
    """Resolve a room document to the canonical ID stored in Reservations."""
    explicit_id = room_data.get("roomID") or room_data.get("roomId")
    if explicit_id is not None and str(explicit_id).strip():
        return str(explicit_id).strip()
    return extract_room_id(room_data.get("name")) or document_id


def coerce_capacity(value: Any) -> int:
    """Convert Firestore capacity values to a sortable integer without raising."""
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value or ""))
        return int(match.group()) if match else 0


def parse_korean_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or KST)

    clean_value = (
        str(value)
        .replace("오전", "AM")
        .replace("오후", "PM")
        .replace(" UTC+9", "")
        .strip()
    )
    try:
        parsed = datetime.strptime(clean_value, "%Y년 %m월 %d일 %p %I시 %M분 %S초")
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=KST)


def intervals_overlap(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return start < other_end and end > other_start


def format_korean_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    value = value.astimezone(KST)
    period = "오전" if value.hour < 12 else "오후"
    hour = value.hour % 12 or 12
    return (
        f"{value.year}년 {value.month}월 {value.day}일 {period} "
        f"{hour}시 {value.minute}분 {value.second}초 UTC+9"
    )

_RELATIVE_DAY_OFFSETS = {
    "\uC624\uB298": 0,
    "\uB0B4\uC77C": 1,
    "\uBAA8\uB808": 2,
    "\uAE00\uD53C": 3,
}


_PERIOD_PM = {"\uC624\uD6C4", "\uC800\uB141", "\uBC24"}
_PERIOD_AM = {"\uC624\uC804", "\uC544\uCE68", "\uC0C8\uBCBD"}
_WEEKDAY_INDEX = {
    "\uC6D4": 0,
    "\uC6D4\uC694\uC77C": 0,
    "\uD654": 1,
    "\uD654\uC694\uC77C": 1,
    "\uC218": 2,
    "\uC218\uC694\uC77C": 2,
    "\uBAA9": 3,
    "\uBAA9\uC694\uC77C": 3,
    "\uAE08": 4,
    "\uAE08\uC694\uC77C": 4,
    "\uD1A0": 5,
    "\uD1A0\uC694\uC77C": 5,
    "\uC77C": 6,
    "\uC77C\uC694\uC77C": 6,
}


def parse_natural_korean_datetime(
    text: Any,
    now: Optional[datetime] = None,
    default_date: Optional[datetime] = None,
) -> Optional[datetime]:
    """Parse common Korean date/time phrases such as 'day after tomorrow at 11 AM'.

    This is a guardrail for LLM function calls: if the model omits or mangles a
    reservation time, the server can still recover the user's explicit intent.
    """
    if not text:
        return None

    source = str(text).strip()
    if not source:
        return None

    base_now = now or datetime.now(KST)
    if base_now.tzinfo is None:
        base_now = base_now.replace(tzinfo=KST)
    base_now = base_now.astimezone(KST)

    date_value = None
    for word, offset in _RELATIVE_DAY_OFFSETS.items():
        if word in source:
            date_value = (base_now + timedelta(days=offset)).date()
            break

    if date_value is None:
        explicit = re.search(
            r"(?:(\d{4})\s*\uB144\s*)?(\d{1,2})\s*\uC6D4\s*(\d{1,2})\s*\uC77C",
            source,
        )
        if explicit:
            year = int(explicit.group(1) or base_now.year)
            month = int(explicit.group(2))
            day = int(explicit.group(3))
            try:
                date_value = datetime(year, month, day, tzinfo=KST).date()
            except ValueError:
                return None

    if date_value is None:
        next_week = re.search(
            r"\uB2E4\uC74C\s*\uC8FC\s*(\uC6D4\uC694\uC77C|\uD654\uC694\uC77C|\uC218\uC694\uC77C|\uBAA9\uC694\uC77C|\uAE08\uC694\uC77C|\uD1A0\uC694\uC77C|\uC77C\uC694\uC77C|\uC6D4|\uD654|\uC218|\uBAA9|\uAE08|\uD1A0|\uC77C)",
            source,
        )
        if next_week:
            weekday = _WEEKDAY_INDEX[next_week.group(1)]
            days_until_next_monday = 7 - base_now.weekday()
            date_value = (base_now + timedelta(days=days_until_next_monday + weekday)).date()

    time_match = re.search(
        r"(\uC624\uC804|\uC624\uD6C4|\uC544\uCE68|\uC800\uB141|\uBC24|\uC0C8\uBCBD)\s*"
        r"(\d{1,2})(?:(?::(\d{1,2}))|(?:\s*\uC2DC\s*(?:(\d{1,2})\s*\uBD84|(\uBC18))?))",
        source,
    )
    if time_match:
        period = time_match.group(1)
        hour = int(time_match.group(2))
        minute = 30 if time_match.group(5) else int(time_match.group(3) or time_match.group(4) or 0)
    else:
        time_match = re.search(
            r"(?<!\d)(\d{1,2})(?:(?::(\d{1,2}))|(?:\s*\uC2DC\s*(?:(\d{1,2})\s*\uBD84|(\uBC18))?))(?!\d)",
            source,
        )
        if not time_match:
            return None
        period = None
        hour = int(time_match.group(1))
        minute = 30 if time_match.group(4) else int(time_match.group(2) or time_match.group(3) or 0)

    if hour > 23 or minute > 59:
        return None

    if period in _PERIOD_PM and hour < 12:
        hour += 12
    elif period in _PERIOD_AM and hour == 12:
        hour = 0

    if date_value is None and default_date is not None:
        if default_date.tzinfo is None:
            default_date = default_date.replace(tzinfo=KST)
        date_value = default_date.astimezone(KST).date()

    if date_value is None:
        candidate = base_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= base_now:
            candidate += timedelta(days=1)
        return candidate

    return datetime(
        date_value.year,
        date_value.month,
        date_value.day,
        hour,
        minute,
        0,
        tzinfo=KST,
    )
