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
