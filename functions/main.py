from firebase_functions import https_fn, scheduler_fn
from firebase_admin import firestore, initialize_app, auth
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import re
import logging

from reservation_utils import (
    KST,
    coerce_capacity,
    extract_room_id,
    format_korean_time,
    intervals_overlap,
    parse_korean_time,
    parse_natural_korean_datetime,
    reservation_room_id,
)

# 환경 설정
load_dotenv()
initialize_app()


class _LazyFirestoreClient:
    """Create the Firestore client only when a function actually uses it.

    Firebase CLI imports this module during deployment discovery to read the
    function manifest. Creating firestore.client() at import time makes that
    discovery depend on local Application Default Credentials, so keep it lazy.
    """

    _client = None

    def _get_client(self):
        if self._client is None:
            self._client = firestore.client()
        return self._client

    def __getattr__(self, name):
        return getattr(self._get_client(), name)


db = _LazyFirestoreClient()
# API Key 기반 클라이언트 설정 (Vertex AI 자동 전환 방지)
api_key = os.environ.get("GEMINI_API_KEY")
genai_client = genai.Client(api_key=api_key, vertexai=False)

CHAT_HISTORY_MAX_MESSAGES = 10
CHAT_HISTORY_RETENTION_DAYS = 30


def is_reservation_confirmation(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    robust_confirmation_words = (
        "\uc608\uc57d\ud655\uc815",
        "\ud655\uc815",
        "\ud655\uc778\ud588\uc5b4",
        "\uc9c4\ud589\ud574",
        "\uc9c4\ud589",
        "\uadf8\uac78\ub85c",
        "\uadf8\uac83\uc73c\ub85c",
        "\uc88b\uc544",
        "\uc751",
        "\ub124",
        "\ub9de\uc544",
        "\uc608\uc57d\ud574",
        "ok",
        "okay",
    )
    robust_cancellation_words = (
        "\ucde8\uc18c",
        "\uc544\ub2c8",
        "\ub9d0\uace0",
        "\ubcc0\uacbd",
        "\ubc14\uafd4",
    )
    if any(word in normalized for word in robust_confirmation_words) and not any(
        word in normalized for word in robust_cancellation_words
    ):
        return True
    confirmation_words = (
        "예약확정",
        "확정",
        "확인했어",
        "진행해",
        "진행",
        "그걸로",
        "그대로",
        "좋아",
        "네",
        "응",
        "맞아",
        "오케이",
        "ok",
        "okay",
    )
    cancellation_words = ("취소", "아니", "말고", "변경", "바꿔")
    return any(word in normalized for word in confirmation_words) and not any(
        word in normalized for word in cancellation_words
    )


def is_alternative_room_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\ub2e4\ub978\uac15\uc758\uc2e4",
            "\ub2e4\ub978\ubc29",
            "\ub2e4\ub978\uacf3",
            "\ub2e4\ub978\ub370",
            "\ub300\uccb4\uac15\uc758\uc2e4",
            "\ub300\uccb4\ub85c",
            "\ube48\uac15\uc758\uc2e4",
            "\uac00\ub2a5\ud55c\uac15\uc758\uc2e4",
        )
    )


def is_cancel_reservation_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\uc608\uc57d\ucde8\uc18c",
            "\uc608\uc57d\uc744\ucde8\uc18c",
            "\ucde8\uc18c\ud574",
            "\ucde8\uc18c\ud574\uc918",
            "\ucde8\uc18c\ud558\uace0\uc2f6",
            "\ucde8\uc18c\ud560\uac8c",
            "\uc608\uc57d\uc0ad\uc81c",
            "\uc608\uc57d\uc5c6\uc560",
        )
    )


def is_change_reservation_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    if is_cancel_reservation_request(normalized):
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\uc608\uc57d\ubcc0\uacbd",
            "\ubcc0\uacbd\ud574",
            "\ubcc0\uacbd\ud574\uc918",
            "\ubc14\uafb8\uace0\uc2f6",
            "\ubc14\uafd4\uc918",
            "\ubc14\uafd4",
            "\uc2dc\uac04\ubc14",
            "\uc2dc\uac04\uc744\ubc14",
            "\uc778\uc6d0\ubc14",
            "\uba85\uc73c\ub85c\ubc14",
            "\uac15\uc758\uc2e4\ubc14",
        )
    )


def is_explicit_change_reservation_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\uae30\uc874\uc608\uc57d",
            "\ub0b4\uc608\uc57d",
            "\uc608\uc57d\ubcc0\uacbd",
            "\uc608\uc57d\uc744\ubcc0\uacbd",
            "\uc608\uc57d\ubc14",
            "\ubcc0\uacbd\ud574",
            "\ubcc0\uacbd\ud574\uc918",
            "\ubc14\uafd4\uc918",
            "\ubc14\uafd4",
        )
    )


def is_my_reservations_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\ub0b4\uc608\uc57d",
            "\uc608\uc57d\ub0b4\uc5ed",
            "\uc608\uc57d\ud655\uc778",
            "\uc608\uc57d\uc870\ud68c",
            "\uc608\uc57d\ubcf4\uc5ec",
            "\ubb50\uc608\uc57d",
        )
    ) and not is_reservation_confirmation(normalized)


def is_new_reservation_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\uc0c8\ub85c\uc6b4\uc608\uc57d",
            "\uc0c8\uc608\uc57d",
            "\uc2e0\uaddc\uc608\uc57d",
            "\uc0c8\ub85c\uc608\uc57d",
            "\ub2e4\uc2dc\uc608\uc57d",
            "\ucc98\uc74c\ubd80\ud130",
        )
    )


def is_reservation_request_text(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        word in normalized
        for word in (
            "\uc608\uc57d",
            "\ub300\uc5ec",
            "\ube4c\ub824",
            "\uc0ac\uc6a9",
            "\uc7a1\uc544",
        )
    )


def parse_participant_count(text):
    if not text:
        return None
    match = re.search(r"(?<!\d)(\d{1,3})\s*(?:\uba85|\uc0ac\ub78c|\uc778)(?!\d)", str(text))
    if match:
        return int(match.group(1))
    normalized = str(text).strip()
    if re.fullmatch(r"\d{1,3}", normalized):
        return int(normalized)
    return None


def parse_duration_hours(text):
    if not text:
        return None
    raw = str(text)
    match = re.search(r"(?<!\d)(\d{1,2})\s*(?:\uc2dc\uac04|hours?|h)(?!\d)", raw, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def extract_room_ids(text):
    if not text:
        return []
    found = []
    for match in re.finditer(r"(?<!\d)([1-9]\d{3})(?!\d)", str(text)):
        room_id = match.group(1)
        if room_id not in found:
            found.append(room_id)
    single = extract_room_id(text)
    if single and single not in found:
        found.insert(0, single)
    return found


# 방 식별자(이름, 번호, 문서 ID)로 Firestore 강의실 검색하는 헬퍼 함수
def find_room(room_identifier):
    if not room_identifier:
        return None, None
    
    room_identifier = str(room_identifier).strip()
    
    # 1. 문서 ID로 직접 조회 시도
    doc = db.collection("rooms").document(room_identifier).get()
    if doc.exists:
        return doc.id, doc.to_dict()
        
    # 2. 'name' 필드 매칭 시도
    docs = db.collection("rooms").where("name", "==", room_identifier).get()
    if docs:
        return docs[0].id, docs[0].to_dict()
        
    # 3. 방 번호(숫자 추출)로 매칭 시도
    room_num = extract_room_id(room_identifier)
    if room_num:
        all_rooms = db.collection("rooms").stream()
        for r_doc in all_rooms:
            r_data = r_doc.to_dict()
            if reservation_room_id(r_doc.id, r_data) == room_num:
                return r_doc.id, r_data
                
    # 4. 부분 검색/퍼지 매칭 시도
    all_rooms = db.collection("rooms").stream()
    for r_doc in all_rooms:
        r_data = r_doc.to_dict()
        name = r_data.get("name", "")
        if room_identifier in name or name in room_identifier:
            return r_doc.id, r_data
            
    return None, None


def has_conflict(field: str, value: str, start, end, exclude_id: str = None):
    # 인덱스 문제와 안드로이드 앱의 Extra Fields 크래시 문제를 해결하기 위해,
    # startTimestamp/endTimestamp 필드 대신 문자열 startTime/endTime을 파싱하여 메모리에서 모두 비교합니다.
    conflicts = db.collection("Reservations").where(field, "==", value).stream()
        
    logging.info(f"[has_conflict] field={field}, value={value}, exclude_id={exclude_id}")
    
    for doc in conflicts:
        if exclude_id and doc.id == exclude_id:
            continue
            
        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue
        
        c_start = data.get("startTimestamp")
        c_end = data.get("endTimestamp")
        
        # 만약 Timestamp 객체가 없다면 문자열에서 파싱
        if not c_start or not hasattr(c_start, 'timestamp'):
            c_start = parse_korean_time(data.get("startTime"))
        if not c_end or not hasattr(c_end, 'timestamp'):
            c_end = parse_korean_time(data.get("endTime"))
            
        if not c_start or not c_end:
            continue
            
        try:
            # 겹치는 조건: 기존 예약의 시작시간이 새 예약의 종료시간보다 앞서고, 기존 예약의 종료시간이 새 예약의 시작시간보다 뒤일 때
            if intervals_overlap(start, end, c_start, c_end):
                return True
        except Exception as e:
            logging.warning(f"[has_conflict] 날짜 비교 중 오류 무시 (문서 ID: {doc.id}): {e}")
            continue
            
    return False


def find_conflicting_reservation(field: str, value: str, start, end, exclude_id: str = None):
    conflicts = db.collection("Reservations").where(field, "==", value).stream()
    for doc in conflicts:
        if exclude_id and doc.id == exclude_id:
            continue

        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue

        c_start = data.get("startTimestamp")
        c_end = data.get("endTimestamp")
        if not c_start or not hasattr(c_start, "timestamp"):
            c_start = parse_korean_time(data.get("startTime"))
        if not c_end or not hasattr(c_end, "timestamp"):
            c_end = parse_korean_time(data.get("endTime"))

        if c_start and c_end and intervals_overlap(start, end, c_start, c_end):
            return doc.id, data
    return None, None


def find_available_rooms(start, end, person_count=0, exclude_room_ids=None):
    exclude_room_ids = {str(room_id) for room_id in (exclude_room_ids or []) if room_id}
    matched = []
    for doc in db.collection("rooms").stream():
        r_data = doc.to_dict()
        canonical_room_id = reservation_room_id(doc.id, r_data)
        if canonical_room_id in exclude_room_ids:
            continue

        cap = coerce_capacity(r_data.get("capacity"))
        if person_count > 0 and cap < person_count:
            continue

        if not has_conflict("roomID", canonical_room_id, start, end):
            matched.append((cap, canonical_room_id, doc.id, r_data))

    matched.sort()
    return matched


def reservation_time_range(data):
    start = data.get("startTimestamp")
    end = data.get("endTimestamp")
    if not start or not hasattr(start, "timestamp"):
        start = parse_korean_time(data.get("startTime"))
    if not end or not hasattr(end, "timestamp"):
        end = parse_korean_time(data.get("endTime"))
    return start, end


def find_user_reservation(userID, room_id=None, target_start=None):
    now = datetime.now(KST)
    candidates = []
    for doc in db.collection("Reservations").where("userID", "==", userID).stream():
        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue

        doc_room_id = str(data.get("roomID") or data.get("room") or "").strip()
        if room_id and doc_room_id != str(room_id):
            continue

        start, end = reservation_time_range(data)
        if target_start and start and end:
            if not (start <= target_start < end or start.date() == target_start.date()):
                continue

        if start:
            priority = 0 if start >= now else 1
            distance = abs((start - (target_start or now)).total_seconds())
        else:
            priority = 2
            distance = 10**12
        candidates.append((priority, distance, doc.id, data, start, end))

    if not candidates:
        return None, None, None, None

    candidates.sort(key=lambda item: (item[0], item[1]))
    _, _, doc_id, data, start, end = candidates[0]
    return doc_id, data, start, end


def list_user_upcoming_reservations(userID, limit=3):
    now = datetime.now(KST)
    rooms_cache = {}
    for doc in db.collection("rooms").stream():
        data = doc.to_dict()
        room_id = reservation_room_id(doc.id, data)
        rooms_cache[room_id] = display_room_label(room_id, data)

    reservations = []
    for doc in db.collection("Reservations").where("userID", "==", userID).stream():
        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue
        start, end = reservation_time_range(data)
        if end and end < now:
            continue
        room_id = str(data.get("roomID") or "")
        room_name = rooms_cache.get(room_id, display_room_label(room_id))
        reservations.append((start or datetime.max.replace(tzinfo=KST), room_name, data))

    reservations.sort(key=lambda item: item[0])
    return reservations[:limit]


def display_room_label(room_id, room_data=None):
    canonical_id = None
    if room_data:
        canonical_id = reservation_room_id(str(room_id or ""), room_data)
    canonical_id = canonical_id or extract_room_id(room_id) or str(room_id or "").strip()
    if canonical_id:
        return f"{canonical_id} \uac15\uc758\uc2e4"
    if room_data and room_data.get("name"):
        return room_data.get("name")
    return "\uac15\uc758\uc2e4"


def suggest_alternative_room_response(
    original_room_name,
    start,
    end,
    duration,
    event_participants,
    owner_uid,
    userID,
    exclude_room_ids=None,
    replace_reservation_id=None,
):
    numeric_part = re.search(r"\d+", str(event_participants or ""))
    person_count = int(numeric_part.group()) if numeric_part else 0
    alternatives = find_available_rooms(
        start,
        end,
        person_count=person_count,
        exclude_room_ids=exclude_room_ids,
    )
    if not alternatives:
        return https_fn.Response(
            f"{original_room_name}\uc740 \ud574\ub2f9 \uc2dc\uac04\uc5d0 \uc774\ubbf8 \uc608\uc57d\ub418\uc5b4 \uc788\uace0, "
            "\uac19\uc740 \uc2dc\uac04\uc5d0 \uc870\uac74\uc5d0 \ub9de\ub294 \ub2e4\ub978 \uac15\uc758\uc2e4\ub3c4 \ucc3e\uc9c0 \ubabb\ud588\uc5b4\uc694. "
            "\ub2e4\ub978 \uc2dc\uac04\ub300\ub97c \uc120\ud0dd\ud574 \uc8fc\uc138\uc694.",
            status=409,
        )

    _, alt_room_id, _, alt_room_data = alternatives[0]
    alt_room_name = display_room_label(alt_room_id, alt_room_data)
    pending_data = {
        "room": alt_room_id,
        "startTime": start.isoformat(),
        "duration": duration,
        "eventName": "\ucd94\ucc9c \uc608\uc57d",
        "eventDescription": "",
        "eventTarget": "",
        "eventParticipants": str(event_participants or "").strip(),
        "ownerUid": owner_uid,
    }
    if replace_reservation_id:
        pending_data["replaceReservationId"] = replace_reservation_id
    db.collection("PendingReservations").document(userID).set(pending_data)
    confirmation_action = "\ubcc0\uacbd" if replace_reservation_id else "\uc608\uc57d"
    return https_fn.Response(
        f"{original_room_name}\uc740 \ud574\ub2f9 \uc2dc\uac04\uc5d0 \uc774\ubbf8 \uc608\uc57d\ub418\uc5b4 \uc788\uc5b4\uc694.\n\n"
        f"\ub300\uc2e0 {alt_room_name}\uc740 \uac19\uc740 \uc2dc\uac04\uc5d0 \uc608\uc57d \uac00\ub2a5\ud574\uc694.\n"
        f"\uc2dc\uac04: {format_korean_time(start)} ~ {format_korean_time(end)}\n"
        f"\uc778\uc6d0: {pending_data['eventParticipants']}\n\n"
        f"\uc774 \uac15\uc758\uc2e4\ub85c {confirmation_action}\ud558\uc2dc\ub824\uba74 '\uc608\uc57d \ud655\uc815'\uc774\ub77c\uace0 \uc785\ub825\ud574 \uc8fc\uc138\uc694.",
        status=200,
    )

def handle_query_equipment(query, userID):
    room_id, room_data = find_room(query.get("room"))
    if not room_id:
        return https_fn.Response("강의실이 존재하지 않습니다.", status=404)
    eq = room_data.get("equipment", [])
    item = query.get("item")
    room_name = room_data.get("name", room_id)
    if not item or item in ["뭐", "무엇", "있는지", "있는가"]:
        eq_list = ", ".join(eq) if eq else "없음"
        return https_fn.Response(f"{room_name}에 있는 기자재: {eq_list}", status=200)
    return https_fn.Response(f"{room_name}에 '{item}'이(가) {'있습니다' if item in eq else '없습니다' }.", status=200)


def handle_reserve(query, userID):
    try:
        logging.info(f"[handle_reserve] input query: {query}")
        owner_uid = query.pop("ownerUid", "")
        query["userID"] = userID

        room_raw = query.get("room")
        room_id, room_data = find_room(room_raw)
        allow_alternative_room = bool(query.pop("allowAlternativeRoom", False))

        pending = db.collection("PendingReservations").document(userID).get()
        if pending.exists:
            pending_data = pending.to_dict()
            if allow_alternative_room and pending_data.get("blockedByReservationId") and not query.get("explicitChangeReservation"):
                pending_room_id = pending_data.get("room")
                _, pending_room_data = find_room(pending_room_id)
                pending_room_name = display_room_label(pending_room_id, pending_room_data)
                return https_fn.Response(
                    f"이미 {pending_room_name}을(를) 해당 시간에 예약해두셨어요.\n\n"
                    "새 예약을 추가로 만들 수는 없어요. 다른 시간대를 선택해 주세요.\n"
                    "기존 예약을 다른 강의실로 바꾸려면 '기존 예약을 다른 강의실로 변경해줘'라고 입력해 주세요.",
                    status=409,
                )
            if not room_id and not room_raw and not allow_alternative_room:
                room_id, room_data = find_room(pending_data.get("room"))
            for field in ("startTime", "duration", "eventName", "eventParticipants"):
                query[field] = query.get(field) or pending_data.get(field)
            if allow_alternative_room:
                query["room"] = ""
        query["duration"] = query.get("duration") or 2

        if not room_id and query.get("room"):
            return https_fn.Response("해당 강의실 정보를 확인할 수 없어요.", status=400)
            
        if allow_alternative_room and not room_id:
            query["room"] = ""
        else:
            room_name = room_data.get("name", "") if room_data else ""
            extracted = extract_room_id(room_name)
            if room_data and room_data.get("roomID"):
                query["room"] = str(room_data.get("roomID"))
            elif room_data and room_data.get("roomId"):
                query["room"] = str(room_data.get("roomId"))
            elif extracted:
                query["room"] = extracted
            else:
                query["room"] = room_id

        query["eventName"] = query.get("eventName") or "추천 예약"
        query["eventDescription"] = query.get("eventDescription") or ""
        query["eventTarget"] = query.get("eventTarget") or ""
        
        # 'eventParticipants' 키의 값을 가져옵니다.
        event_participants_value = query.get("eventParticipants")
        
        # 값이 없으면 keywords에서 추출 시도
        if not event_participants_value and query.get("keywords"):
            person_count = next(
                (int(k.replace("명", "")) for k in query.get("keywords", []) if isinstance(k, str) and k.endswith("명") and k[:-1].isdigit()), 
                None
            )
            if person_count:
                event_participants_value = str(person_count)

        # 값이 문자열인 경우, 공백을 제거합니다.
        if isinstance(event_participants_value, str):
            query["eventParticipants"] = event_participants_value.strip()
        else:
            query["eventParticipants"] = str(event_participants_value or "").strip()
            
        query["status"] = "대기"

        has_room_and_time = bool(query.get("room")) and bool(query.get("startTime"))
        missing_participants_only = (
            has_room_and_time
            and bool(query.get("duration"))
            and not query.get("eventParticipants")
        )
        if missing_participants_only:
            try:
                preview_duration = int(query.get("duration") or 2)
                preview_start = datetime.fromisoformat(str(query["startTime"]))
                if preview_start.tzinfo is None:
                    preview_start = preview_start.replace(tzinfo=KST)
                preview_end = preview_start + timedelta(hours=preview_duration)
                preview_room_id = str(query["room"])
                preview_room_name = display_room_label(preview_room_id, room_data)

                user_conflict_id, user_conflict_data = find_conflicting_reservation(
                    "userID",
                    userID,
                    preview_start,
                    preview_end,
                )
                if user_conflict_id:
                    conflict_room_id = user_conflict_data.get("roomID") or user_conflict_data.get("room")
                    _, conflict_room_data = find_room(conflict_room_id)
                    conflict_room_name = display_room_label(conflict_room_id, conflict_room_data)
                    db.collection("PendingReservations").document(userID).set(
                        {
                            "room": conflict_room_id,
                            "startTime": preview_start.isoformat(),
                            "duration": preview_duration,
                            "eventName": query.get("eventName", "추천 예약"),
                            "eventDescription": query.get("eventDescription", ""),
                            "eventTarget": query.get("eventTarget", ""),
                            "ownerUid": owner_uid,
                            "blockedByReservationId": user_conflict_id,
                        },
                        merge=True,
                    )
                    return https_fn.Response(
                        f"이미 {conflict_room_name}을(를) 해당 시간에 예약해두셨어요. "
                        "새 예약을 만들려면 다른 시간대를 선택해 주세요. "
                        "기존 예약을 바꾸려는 목적이라면 '기존 예약을 다른 강의실로 변경해줘'라고 말해 주세요.",
                        status=409,
                    )

                if has_conflict("roomID", preview_room_id, preview_start, preview_end):
                    db.collection("PendingReservations").document(userID).set(
                        {
                            "room": preview_room_id,
                            "startTime": preview_start.isoformat(),
                            "duration": preview_duration,
                            "eventName": query.get("eventName", "추천 예약"),
                            "eventDescription": query.get("eventDescription", ""),
                            "eventTarget": query.get("eventTarget", ""),
                            "ownerUid": owner_uid,
                        },
                        merge=True,
                    )
                    return https_fn.Response(
                        f"{preview_room_name}은 해당 시간에 이미 예약되어 있어요.\n"
                        "다른 강의실을 찾아드릴 수 있어요. 원하시면 인원 수와 함께 '다른 강의실로 해줘'라고 말해 주세요.",
                        status=409,
                    )
            except Exception as e:
                logging.warning("[handle_reserve] early conflict check skipped: %s", e)

        missing_details = [
            field
            for field in ("startTime", "duration", "eventParticipants")
            if not query.get(field) or not str(query.get(field)).strip()
        ]
        if missing_details:
            db.collection("PendingReservations").document(userID).set(query, merge=True)
            friendly_names = {
                "startTime": "시작 시간",
                "duration": "이용 시간",
                "eventParticipants": "이용 인원 수",
            }
            readable = ", ".join(friendly_names[field] for field in missing_details)
            return https_fn.Response(f"다음 정보가 필요해요: {readable}", status=400)

        try:
            query["duration"] = int(query["duration"])
            start = datetime.fromisoformat(query["startTime"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=KST)
        except Exception as e:
            logging.exception(f"[handle_reserve] 시간 파싱 실패: {query.get('startTime')}")
            return https_fn.Response("시작 시간이 올바른 형식이 아니에요. (예: 내일 오후 3시)", status=400)

        if query["duration"] < 1 or query["duration"] > 6:
            return https_fn.Response("예약 시간은 최소 1시간, 최대 6시간까지만 가능합니다.", status=400)

        now = datetime.now(KST)
        if start < now:
            return https_fn.Response("예약 시작 시간은 현재 시간 이후여야 해요.", status=400)

        end = start + timedelta(hours=query["duration"])

        # 자동으로 빈 강의실 찾기 로직
        if not query.get("room") or str(query.get("room")).strip() == "":
            try:
                person_count = int(re.search(r'\d+', str(query.get("eventParticipants", "0"))).group())
            except:
                person_count = 0
                
            matched = find_available_rooms(start, end, person_count=person_count)
            for doc in []:
                r_data = doc.to_dict()
                canonical_room_id = reservation_room_id(doc.id, r_data)
                cap = coerce_capacity(r_data.get("capacity"))
                if person_count > 0 and cap < person_count:
                    continue

                # 중복 예약 확인
                if not has_conflict("roomID", canonical_room_id, start, end):
                    matched.append((cap, canonical_room_id, doc.id, r_data))
            
            if not matched:
                return https_fn.Response("해당 시간에 원하시는 인원을 수용할 수 있는 빈 강의실이 없습니다 😥", status=409)
            
            # 수용 인원이 가장 꼭 맞는 방 선택 (오름차순)
            matched.sort()
            _, best_room_id, _, best_r_data = matched[0]
            query["room"] = best_room_id
            room_data = best_r_data

        required_fields = ["room", "startTime", "duration", "userID", "eventParticipants", "ownerUid"]
        query["ownerUid"] = owner_uid
        missing = [f for f in required_fields if not query.get(f) or str(query.get(f)).strip() == ""]
        if missing:
            db.collection("PendingReservations").document(userID).set(query, merge=True)
            friendly_names = {
                "room": "강의실",
                "startTime": "시작 시간",
                "duration": "이용 시간",
                "userID": "사용자 정보",
                "eventParticipants": "이용 인원 수",
                "ownerUid": "사용자 인증 정보",
            }
            readable = ", ".join(friendly_names.get(f, f) for f in missing)
            return https_fn.Response(f"다음 정보가 필요해요: {readable}", status=400)

        replace_reservation_id = query.get("replaceReservationId")
        user_conflict_id, user_conflict_data = find_conflicting_reservation(
            "userID",
            userID,
            start,
            end,
            exclude_id=replace_reservation_id,
        )
        if user_conflict_id:
            conflict_room_id = user_conflict_data.get("roomID") or user_conflict_data.get("room")
            _, conflict_room_data = find_room(conflict_room_id)
            conflict_room_name = display_room_label(conflict_room_id, conflict_room_data)
            if allow_alternative_room and query.get("explicitChangeReservation"):
                return suggest_alternative_room_response(
                    conflict_room_name,
                    start,
                    end,
                    query["duration"],
                    query.get("eventParticipants"),
                    owner_uid,
                    userID,
                    exclude_room_ids={conflict_room_id},
                    replace_reservation_id=user_conflict_id,
                )
            if allow_alternative_room:
                return https_fn.Response(
                    f"이미 {conflict_room_name}을(를) 해당 시간에 예약해두셨어요.\n\n"
                    "새 예약을 추가로 만들 수는 없어요. 다른 시간대를 선택해 주세요.\n"
                    "기존 예약을 다른 강의실로 바꾸려면 '기존 예약을 다른 강의실로 변경해줘'라고 입력해 주세요.",
                    status=409,
                )
            db.collection("PendingReservations").document(userID).set(
                {
                    "room": conflict_room_id,
                    "startTime": start.isoformat(),
                    "duration": query["duration"],
                    "eventName": query.get("eventName", "\ucd94\ucc9c \uc608\uc57d"),
                    "eventDescription": query.get("eventDescription", ""),
                    "eventTarget": query.get("eventTarget", ""),
                    "eventParticipants": str(query.get("eventParticipants", "")).strip(),
                    "ownerUid": owner_uid,
                    "blockedByReservationId": user_conflict_id,
                },
                merge=True,
            )
            return https_fn.Response(
                f"\uc774\ubbf8 {conflict_room_name}\uc744(\ub97c) \ud574\ub2f9 \uc2dc\uac04\uc5d0 \uc608\uc57d\ud574\ub450\uc168\uc5b4\uc694. "
                "\uc0c8 \uc608\uc57d\uc744 \ub9cc\ub4e4\ub824\uba74 \ub2e4\ub978 \uc2dc\uac04\ub300\ub97c \uc120\ud0dd\ud574 \uc8fc\uc138\uc694. "
                "\uae30\uc874 \uc608\uc57d\uc744 \ubc14\uafb8\ub824\ub294 \ubaa9\uc801\uc774\ub77c\uba74 '\uae30\uc874 \uc608\uc57d\uc744 \ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ubcc0\uacbd\ud574\uc918'\ub77c\uace0 \ub9d0\ud574 \uc8fc\uc138\uc694.",
                status=409,
            )

        if False and has_conflict("userID", userID, start, end):
            return https_fn.Response("해당 시간에 이미 예약한 강의실이 있어요. 다른 시간대를 선택해 주세요.", status=409)
            
        _, room_data = find_room(query["room"])
        if has_conflict("roomID", query["room"], start, end):
            room_name = display_room_label(query["room"], room_data)
            replace_room_conflict_id, _ = find_conflicting_reservation(
                "userID",
                userID,
                start,
                end,
            )
            return suggest_alternative_room_response(
                room_name,
                start,
                end,
                query["duration"],
                query.get("eventParticipants"),
                owner_uid,
                userID,
                exclude_room_ids={query["room"]},
                replace_reservation_id=replace_room_conflict_id,
            )
            return https_fn.Response(f"{room_name}은 해당 시간에 이미 예약되어 있어요.", status=409)

        room_name = display_room_label(query["room"], room_data)
        if query.pop("needsConfirmation", False):
            pending_data = {
                "room": query["room"],
                "startTime": start.isoformat(),
                "duration": query["duration"],
                "eventName": query.get("eventName", "추천 예약"),
                "eventDescription": query.get("eventDescription", ""),
                "eventTarget": query.get("eventTarget", ""),
                "eventParticipants": str(query.get("eventParticipants", "")).strip(),
                "ownerUid": owner_uid,
            }
            if query.get("replaceReservationId"):
                pending_data["replaceReservationId"] = query["replaceReservationId"]
            db.collection("PendingReservations").document(userID).set(pending_data, merge=True)
            return https_fn.Response(
                "예약 내용을 확인해 주세요 😊\n\n"
                f"강의실: {room_name}\n"
                f"시간: {format_korean_time(start)} ~ {format_korean_time(end)}\n"
                f"인원: {pending_data['eventParticipants']}\n\n"
                "맞다면 '예약 확정'이라고 입력해 주세요.",
                status=200,
            )

        try:
            # 안전하게 eventParticipants를 정수로 변환
            participants_str = str(query.get("eventParticipants", "0")).strip()
            # 숫자만 추출
            numeric_part = re.search(r'\d+', participants_str)
            event_participants_int = int(numeric_part.group()) if numeric_part else 1

            # 시간 문자열 생성 후 한국어 형식으로 변환 (안드로이드 앱과 동일한 형식 맞추기 위해 %-M, %-S 사용)
            start_str = format_korean_time(start)
            end_str = format_korean_time(end)

            res_doc = {
                "documentId": "",
                "roomID": query["room"],
                "startTime": start_str,
                "endTime": end_str,
                "eventName": query.get("eventName", "추천 예약"),
                "eventDescription": query.get("eventDescription", ""),
                "eventTarget": query.get("eventTarget", ""),
                "eventParticipants": event_participants_int,
                "status": query.get("status", "대기"),
                "userID": userID,
                "ownerUid": owner_uid,
            }
            if replace_reservation_id:
                update_doc = dict(res_doc)
                update_doc["startTimestamp"] = firestore.DELETE_FIELD
                update_doc["endTimestamp"] = firestore.DELETE_FIELD
                db.collection("Reservations").document(replace_reservation_id).update(update_doc)
                doc_ref = (None, type("_DocRef", (), {"id": replace_reservation_id})())
            else:
                doc_ref = db.collection("Reservations").add(res_doc)
        except Exception as e:
            logging.exception("[handle_reserve] 예약 저장 실패")
            return https_fn.Response("예약 저장 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)

        try:
            db.collection("PendingReservations").document(userID).delete()
        except Exception as e:
            logging.warning(f"[handle_reserve] Pending 삭제 실패: {e}")

        logging.info(f"[handle_reserve] 예약 성공: {doc_ref[1].id}")
        if replace_reservation_id:
            return https_fn.Response(f"{room_name}로 예약이 변경되었습니다 ✅", status=200)
        return https_fn.Response(f"{room_name}이 예약되었습니다 ✅", status=200)

    except Exception as e:
        logging.exception("[handle_reserve] 최상위 예외 발생")
        return https_fn.Response("예약 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)


def handle_confirm_reservation(query, userID):
    pending_ref = db.collection("PendingReservations").document(userID)
    pending = pending_ref.get()
    if not pending.exists:
        return https_fn.Response("확정할 예약 내용이 없어요. 먼저 예약할 시간과 인원을 알려 주세요.", status=400)

    pending_data = pending.to_dict()
    pending_data["ownerUid"] = query.get("ownerUid", pending_data.get("ownerUid", ""))
    pending_data["confirmed"] = True
    pending_data.pop("needsConfirmation", None)
    return handle_reserve(pending_data, userID)



def handle_cancel_reservation(query, userID):
    try:
        target_room_id, target_room_data = find_room(query.get("room"))
        target_reservation_room_id = (
            reservation_room_id(target_room_id, target_room_data)
            if target_room_id and target_room_data
            else None
        )
        target_start = None
        if query.get("startTime"):
            try:
                target_start = datetime.fromisoformat(str(query.get("startTime")))
                if target_start.tzinfo is None:
                    target_start = target_start.replace(tzinfo=KST)
            except (TypeError, ValueError):
                target_start = None
        logging.info(
            "[handle_cancel_reservation] target_room_id=%s, "
            "target_reservation_room_id=%s, userID=%s",
            target_room_id,
            target_reservation_room_id,
            userID,
        )

        if not target_reservation_room_id and not target_start and not query.get("forceClosest"):
            candidates = list_user_upcoming_reservations(userID, limit=3)
            if not candidates:
                return https_fn.Response("취소할 예약이 없습니다.", status=404)

            lines = []
            for _, room_name, data in candidates:
                start_text = data.get("startTime", "?")
                end_text = data.get("endTime", "?")
                participants = data.get("eventParticipants")
                participant_text = f" / {participants}명" if participants else ""
                lines.append(f"- {room_name}: {start_text} ~ {end_text}{participant_text}")

            return https_fn.Response(
                "취소할 예약을 선택해 주세요:\n" + "\n".join(lines),
                status=200,
            )

        res_id, res_data, _, _ = find_user_reservation(
            userID,
            room_id=target_reservation_room_id,
            target_start=target_start,
        )
        if not res_id:
            return https_fn.Response("취소할 예약이 없습니다.", status=404)

        cancelled_room_id = res_data.get("roomID")
        _, cancelled_room_data = find_room(cancelled_room_id)
        cancelled_room_name = display_room_label(cancelled_room_id, cancelled_room_data)
        db.collection("Reservations").document(res_id).delete()

        return https_fn.Response(f"{cancelled_room_name} 예약이 취소되었습니다 ✅", status=200)

    except Exception as e:
        logging.exception("[handle_cancel_reservation] 예외 발생")
        return https_fn.Response("예약 취소 중 오류가 발생했어요. 로그를 확인해주세요.", status=500)

def handle_change_reservation(query, userID):
    try:
        target_room_id, target_room_data = find_room(query.get("room"))
        target_reservation_room_id = (
            reservation_room_id(target_room_id, target_room_data)
            if target_room_id and target_room_data
            else None
        )
        new_room_id, new_room_data = find_room(query.get("newRoom"))
        new_reservation_room_id = (
            reservation_room_id(new_room_id, new_room_data)
            if new_room_id and new_room_data
            else None
        )
        logging.info(
            "[handle_change_reservation] target_room_id=%s, "
            "target_reservation_room_id=%s, userID=%s",
            target_room_id,
            target_reservation_room_id,
            userID,
        )

        target_start = None
        if query.get("targetStartTime"):
            try:
                target_start = datetime.fromisoformat(str(query.get("targetStartTime")))
                if target_start.tzinfo is None:
                    target_start = target_start.replace(tzinfo=KST)
            except (TypeError, ValueError):
                target_start = None

        res_id, res_data, start, end = find_user_reservation(
            userID,
            room_id=target_reservation_room_id,
            target_start=target_start,
        )
        if not res_id:
            return https_fn.Response("변경할 예약이 없습니다.", status=404)

        new_duration = query.get("duration")
        new_participants = query.get("eventParticipants")
        new_start_time = query.get("startTime")
        duration_hours = int((end - start).total_seconds() / 3600) if end and start else 2

        if new_start_time:
            try:
                start = datetime.fromisoformat(new_start_time)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=KST)
            except:
                pass

        if new_duration:
            duration_hours = int(new_duration)

        if duration_hours < 1 or duration_hours > 6:
            return https_fn.Response("예약 시간은 최소 1시간, 최대 6시간까지만 가능합니다.", status=400)

        end = start + timedelta(hours=duration_hours)
        now = datetime.now(KST)
        if start < now:
            return https_fn.Response("예약 시작 시간은 현재 시간 이후여야 해요.", status=400)

        if has_conflict("userID", userID, start, end, exclude_id=res_id):
            return https_fn.Response("해당 시간에 이미 예약한 다른 강의실이 있어요.", status=409)
        final_room_id = new_reservation_room_id or res_data.get("roomID")
        if has_conflict("roomID", final_room_id, start, end, exclude_id=res_id):
            return https_fn.Response("해당 시간에 이미 강의실이 예약되어 있어요.", status=409)

        update_data = {
            "roomID": final_room_id,
            "startTime": format_korean_time(start),
            "endTime": format_korean_time(end),
            "startTimestamp": firestore.DELETE_FIELD,
            "endTimestamp": firestore.DELETE_FIELD,
        }

        if new_participants:
            participants_str = str(new_participants).strip()
            numeric_part = re.search(r'\d+', participants_str)
            if numeric_part:
                update_data["eventParticipants"] = int(numeric_part.group())

        db.collection("Reservations").document(res_id).update(update_data)
        
        _, room_data = find_room(final_room_id)
        room_name = display_room_label(final_room_id, room_data)
        
        return https_fn.Response(f"{room_name} 예약이 성공적으로 변경되었습니다 ✅", status=200)

    except Exception as e:
        logging.exception("[handle_change_reservation] 예외 발생")
        return https_fn.Response("예약 변경 중 오류가 발생했어요. 로그를 확인해주세요.", status=500)

def handle_latest_notice(query, userID):
    docs = db.collection("Notices").order_by("createdAt", direction=firestore.Query.DESCENDING).limit(1).get()
    if not docs:
        return https_fn.Response("공지사항이 없습니다.", status=200)
    notice = docs[0].to_dict()
    return https_fn.Response(f"[{notice['title']}]\n{notice['content']}", status=200)

def handle_my_reviews(query, userID):
    docs = db.collection("Reviews").where("userID", "==", userID).stream()
    reviews = [d.to_dict() for d in docs]
    if not reviews:
        return https_fn.Response("작성한 리뷰가 없습니다.", status=200)
    sorted_reviews = sorted(reviews, key=lambda x: x.get("createdAt", datetime.min), reverse=True)
    preview = sorted_reviews[:2]
    reply_lines = [f"{r.get('roomID', '?')}호: {r.get('comment', '')} (★{r.get('rating', '?')})" for r in preview]
    reply_lines.append("\n자세한 리뷰는 마이페이지에서 확인해 주세요 😊")
    return https_fn.Response("\n\n".join(reply_lines), status=200)

def handle_review_summary(query, userID):
    room_id, room_data = find_room(query.get("room"))
    if not room_id:
        return https_fn.Response("강의실을 찾을 수 없습니다.", status=404)
    room_name = room_data.get("name", room_id)
    docs = db.collection("Reviews").where("roomID", "==", room_id).stream()
    ratings, pos_comments, neg_comments = [], [], []
    for r in docs:
        review = r.to_dict()
        rating = review.get("rating")
        comment = review.get("comment", "")
        if rating is not None:
            ratings.append(rating)
            if rating >= 4:
                pos_comments.append(comment)
            elif rating <= 2:
                neg_comments.append(comment)
    if not ratings:
        return https_fn.Response(f"{room_name}에 등록된 후기가 없어요.", status=200)
    avg = round(sum(ratings) / len(ratings), 1)
    pos_ratio = round(len(pos_comments) / len(ratings) * 100)
    neg_ratio = 100 - pos_ratio
    pos_line = f'🟢 긍정 후기: "{pos_comments[-1]}"' if pos_comments else ""
    neg_line = f'🔴 부정 후기: "{neg_comments[-1]}"' if neg_comments else ""
    summary = f"""[{room_name} 강의실 평가 요약]
{pos_line}
{neg_line}
⭐ 평균 평점: {avg}점
📊 긍정 {pos_ratio}%, 부정 {neg_ratio}%"""
    return https_fn.Response(summary, status=200)

def handle_recommend_room(query, userID):
    keywords = query.get("keywords", [])
    now = datetime.now(KST)
    try:
        duration = int(query.get("duration") or 2)
    except (TypeError, ValueError):
        return https_fn.Response("이용 시간은 숫자로 입력해 주세요.", status=400)
    if duration < 1 or duration > 6:
        return https_fn.Response("예약 시간은 최소 1시간, 최대 6시간까지만 가능합니다.", status=400)

    # 🔍 인원 조건 추출
    person_count = next(
        (int(k.replace("명", "")) for k in keywords if k.endswith("명") and k[:-1].isdigit()), 
        None
    )
    if person_count is None and query.get("eventParticipants"):
        try:
            num = re.search(r'\d+', str(query.get("eventParticipants")))
            if num:
                person_count = int(num.group())
        except:
            pass


    # 🔍 시간 기준: "지금" 또는 명시적 예약 시작 시간
    require_available_now = "지금" in keywords
    after_time_str = query.get("afterTime") or query.get("startTime")
    base_time = now

    if after_time_str:
        try:
            base_time = datetime.fromisoformat(after_time_str)
            if base_time.tzinfo is None:
                base_time = base_time.replace(tzinfo=KST)
            require_available_now = True  # afterTime이 있으면 무조건 검사
        except (TypeError, ValueError):
            return https_fn.Response("조회 시간이 올바른 형식이 아니에요.", status=400)

    base_time = base_time.astimezone(KST)
    if after_time_str and base_time <= now:
        return https_fn.Response("예약 시작 시간은 현재 시간 이후여야 해요.", status=400)
    end_time = base_time + timedelta(hours=duration)

    matched = []

    for doc in db.collection("rooms").stream():
        data = doc.to_dict()
        room_id = reservation_room_id(doc.id, data)
        eq = data.get("equipment", [])
        cap = coerce_capacity(data.get("capacity"))

        # 인원 조건
        if person_count is not None and cap < person_count:
            continue

        # ✅ base_time에 사용 중인지 확인
        if require_available_now:
            if has_conflict("roomID", room_id, base_time, end_time):
                continue

        # 기자재 키워드 일치 점수 계산
        score = sum(1 for k in keywords if k in eq)

        if score > 0 or person_count is not None or require_available_now:
            matched.append((-score, cap, room_id, data))

    if not matched:
        return https_fn.Response("조건에 맞는 강의실이 없어요 😥", status=200)

    matched.sort(key=lambda item: item[:3])
    _, _, room_id, best = matched[0]

    location = best.get("location") or best.get("buildingName") or "정보 없음"
    capacity = best.get("capacity", "정보 없음")
    equipment = ", ".join(best.get("equipment", [])) or "없음"

    # 🔍 후기 분석
    reviews = db.collection("Reviews").where("roomID", "==", room_id).stream()
    ratings, pos_comments, neg_comments, latest_comment, latest_time = [], [], [], None, None
    for r in reviews:
        review = r.to_dict()
        rating = review.get("rating")
        comment = review.get("comment", "")
        created = review.get("createdAt")
        if rating is not None:
            ratings.append(rating)
            if rating >= 4:
                pos_comments.append(comment)
            elif rating <= 2:
                neg_comments.append(comment)
        if created and comment and (not latest_time or str(created) > str(latest_time)):
            latest_comment, latest_time = comment, created

    avg = round(sum(ratings) / len(ratings), 1) if ratings else None
    pos_rate = round(len(pos_comments) / len(ratings) * 100) if ratings else 0
    neg_rate = 100 - pos_rate if ratings else 0

    response = f"""조건에 맞는 강의실을 찾아봤어요! 😊
📍 위치: {location}
🏫 강의실: {display_room_label(room_id, best)} (최대 {capacity}명)
🛠️ 기자재: {equipment}"""
    if latest_comment:
        response += f'\n📝 최근 후기: "{latest_comment}"'
    if avg is not None:
        response += f"\n⭐ 평균 평점: {avg}점\n📊 긍정 {pos_rate}%, 부정 {neg_rate}%"
        
    response += "\n\n이 강의실로 예약하시겠어요?"

    if after_time_str:
        pending_start_time = base_time.astimezone(KST).isoformat()
    else:
        pending_start_time = (base_time + timedelta(minutes=10)).astimezone(KST).isoformat()

    pending_data = {
        "room": room_id,
        "startTime": pending_start_time,
        "duration": duration,
        "eventName": query.get("eventName", "추천 예약")
    }
    if person_count is not None:
        pending_data["eventParticipants"] = f"{person_count}명"

    db.collection("PendingReservations").document(userID).set(pending_data, merge=True)

    return https_fn.Response(response, status=200)


def handle_list_rooms(query, userID):
    docs = db.collection("rooms").stream()
    rooms = [doc.id for doc in docs]
    return https_fn.Response("전체 강의실: " + ", ".join(rooms), status=200)

def handle_list_rooms_by_building(query, userID):
    target = query.get("building")
    if not target:
        return https_fn.Response("건물명을 입력해 주세요. 예: '5강의동'", status=400)
    docs = db.collection("rooms").where("buildingDetail", "==", target).stream()
    room_ids = [doc.id for doc in docs]
    if not room_ids:
        return https_fn.Response(f"'{target}'에 해당하는 강의실이 없어요.", status=200)
    return https_fn.Response(f"{target}의 강의실 목록: {', '.join(room_ids)}", status=200)

def handle_list_rooms_by_equipment(query, userID):
    item = query.get("item")
    if not item:
        return https_fn.Response("기자재를 입력해 주세요. 예: '마이크'", status=400)
    docs = db.collection("rooms").where("equipment", "array_contains", item).stream()
    room_ids = [doc.id for doc in docs]
    if not room_ids:
        return https_fn.Response(f"'{item}'이(가) 있는 강의실이 없어요.", status=200)
    return https_fn.Response(f"'{item}'이(가) 있는 강의실: {', '.join(room_ids)}", status=200)

def handle_room_availability(query, userID):
    room_id, room_data = find_room(query.get("room"))
    if not room_id:
        return https_fn.Response("강의실을 찾을 수 없습니다.", status=404)
    room_name = display_room_label(room_id, room_data)
    now = datetime.now(KST)
    one_day_later = now + timedelta(days=1)
    docs = db.collection("Reservations").where("roomID", "==", room_id).stream()
    times = []
    for doc in docs:
        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue
        start, _ = reservation_time_range(data)
        if start and now <= start < one_day_later:
            times.append((start, data.get("startTime", "?")))
    times.sort(key=lambda item: item[0])
    if not times:
        return https_fn.Response(f"{room_name}은 앞으로 24시간 예약이 없습니다.", status=200)
    return https_fn.Response(f"{room_name} 예약 시간 목록: {', '.join(time for _, time in times)}", status=200)

def handle_my_reservations(query, userID):
    reservations = list_user_upcoming_reservations(userID, limit=10)
    if not reservations:
        return https_fn.Response("현재 예약 및 예정된 예약이 없습니다.", status=200)

    lines = []
    for _, room_name, data in reservations[:10]:
        start_text = data.get("startTime", "?")
        end_text = data.get("endTime", "?")
        participants = data.get("eventParticipants")
        participant_text = f" / {participants}명" if participants else ""
        lines.append(f"- {room_name}: {start_text} ~ {end_text}{participant_text}")
    return https_fn.Response("현재 예약 및 예정된 예약:\n" + "\n".join(lines), status=200)

handlers = {
    "query_equipment": handle_query_equipment,
    "reserve": handle_reserve,
    "confirm_reservation": handle_confirm_reservation,
    "change_reservation": handle_change_reservation,
    "cancel_reservation": handle_cancel_reservation,
    "latest_notice": handle_latest_notice,
    "my_reviews": handle_my_reviews,
    "recommend_room": handle_recommend_room,
    "review_summary": handle_review_summary,
    "list_rooms": handle_list_rooms,
    "list_rooms_by_building": handle_list_rooms_by_building,
    "list_rooms_by_equipment": handle_list_rooms_by_equipment,
    "room_availability": handle_room_availability,
    "my_reservations": handle_my_reservations
}

FAQ_RULES = """
[강의실 이용 수칙 및 안내]
- 예약 가능 시간: 오전 9시부터 오후 10시까지 예약 가능합니다. (밤 10시 이후 예약 불가)
- 예약 단위: 최소 1시간부터 최대 6시간까지 예약 가능합니다.
- 취소 규정: 예약 시작 1시간 전까지 취소 가능하며, 노쇼(No-show) 시 1개월간 예약이 정지됩니다.
- 프로젝터 사용법: 프로젝터 리모컨은 각 강의실 앞 교탁 서랍에 비치되어 있습니다.
- 음식물 반입: 생수 외의 음료나 음식물 반입은 엄격히 금지됩니다.
- 최소 예약 인원: 최소 1명 이상이어야 예약이 가능합니다.
"""

@https_fn.on_request()
def ai_assistant(req: https_fn.Request) -> https_fn.Response:
    try:
        data = req.get_json(silent=True)
        if not isinstance(data, dict):
            return https_fn.Response("JSON 요청 본문이 필요합니다.", status=400)
        user_input = str(data.get("message", "")).strip()
        if not user_input:
            return https_fn.Response("메시지를 입력해 주세요.", status=400)
        if len(user_input) > 2000:
            return https_fn.Response("메시지는 2,000자 이내로 입력해 주세요.", status=400)

        authorization = req.headers.get("Authorization", "")
        id_token = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
        uid = "unknown"
        if id_token:
            try:
                decoded_token = auth.verify_id_token(id_token)
                uid = decoded_token.get("uid", "unknown")
            except Exception as e:
                logging.warning(f"Failed to verify token: {e}")
                return https_fn.Response("유효하지 않은 토큰입니다.", status=401)
        
        if uid == "unknown":
            logging.warning("UserID is unknown. Authentication is required.")
            return https_fn.Response("사용자 인증이 필요합니다. 다시 로그인해주세요.", status=401)

        # uid로 사용자 문서 조회하여 학번(studentId) 가져오기
        try:
            user_doc_ref = db.collection("User").document(uid)
            user_doc = user_doc_ref.get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                raw_student_id = user_data.get("studentId")
                if not raw_student_id:
                    return https_fn.Response("사용자 정보에서 학번을 찾을 수 없습니다.", status=404)
                userID = str(raw_student_id)
            else:
                return https_fn.Response("사용자 정보를 찾을 수 없습니다.", status=404)
        except Exception:
            logging.exception("사용자 정보 조회 실패")
            return https_fn.Response("사용자 정보 조회 중 오류가 발생했습니다.", status=500)

        # ----------------------------------------------------
        # 1. Chat History 불러오기
        # ----------------------------------------------------
        history_ref = db.collection("ChatHistory").document(userID)
        history_doc = history_ref.get()
        stored_messages = []
        if history_doc.exists:
            messages = history_doc.to_dict().get("messages", [])
            if isinstance(messages, list):
                stored_messages = messages[-10:]

        chat_history = []
        for msg in stored_messages:
            if isinstance(msg, dict) and msg.get("role") in {"user", "model"} and msg.get("text"):
                chat_history.append({"role": msg["role"], "parts": [{"text": str(msg["text"])}]})

        now_kst = datetime.now(KST)

        def _store_direct_response(bot_text, status=200):
            history_ref.set(
                {
                    "messages": (
                        stored_messages
                        + [
                            {"role": "user", "text": user_input},
                            {"role": "model", "text": bot_text},
                        ]
                    )[-CHAT_HISTORY_MAX_MESSAGES:],
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                    "expiresAt": datetime.now(KST) + timedelta(days=CHAT_HISTORY_RETENTION_DAYS),
                },
                merge=True,
            )
            return https_fn.Response(bot_text, status=status)

        pending_ref = db.collection("PendingReservations").document(userID)
        pending_doc_for_guard = pending_ref.get()
        pending_data_for_guard = pending_doc_for_guard.to_dict() if pending_doc_for_guard.exists else {}
        pending_start_for_guard = None
        pending_start_raw = pending_data_for_guard.get("startTime")
        if pending_start_raw:
            try:
                pending_start_for_guard = datetime.fromisoformat(str(pending_start_raw))
                if pending_start_for_guard.tzinfo is None:
                    pending_start_for_guard = pending_start_for_guard.replace(tzinfo=KST)
            except (TypeError, ValueError):
                pending_start_for_guard = None

        preliminary_room_id = extract_room_id(user_input)
        preliminary_change_request = is_change_reservation_request(user_input)
        preliminary_cancel_request = is_cancel_reservation_request(user_input)
        default_date_for_direct_parse = pending_start_for_guard
        if not default_date_for_direct_parse and (preliminary_change_request or preliminary_cancel_request):
            try:
                _, _, existing_start_for_guard, _ = find_user_reservation(
                    userID,
                    room_id=preliminary_room_id,
                )
                if existing_start_for_guard:
                    default_date_for_direct_parse = existing_start_for_guard
            except Exception as e:
                logging.warning("[ai_assistant] Existing reservation date lookup failed: %s", e)

        direct_start = parse_natural_korean_datetime(
            user_input,
            now_kst,
            default_date=default_date_for_direct_parse,
        )
        direct_room_id = extract_room_id(user_input)
        direct_room_ids = extract_room_ids(user_input)
        direct_participants = parse_participant_count(user_input)
        direct_duration = parse_duration_hours(user_input)
        wants_alternative_room = is_alternative_room_request(user_input)
        wants_new_reservation = is_new_reservation_request(user_input)
        wants_cancel_reservation = preliminary_cancel_request
        wants_change_reservation = preliminary_change_request
        explicitly_changes_existing_reservation = is_explicit_change_reservation_request(user_input)
        wants_my_reservations = is_my_reservations_request(user_input)
        confirms_pending = (
            pending_doc_for_guard.exists
            and not wants_new_reservation
            and is_reservation_confirmation(user_input)
        )

        if wants_new_reservation and not any([direct_start, direct_room_id, direct_participants]):
            pending_ref.delete()
            return _store_direct_response(
                "\uc88b\uc544\uc694. \uc0c8 \uc608\uc57d\uc73c\ub85c \uc2dc\uc791\ud560\uac8c\uc694. "
                "\uc6d0\ud558\ub294 \ub0a0\uc9dc, \uc2dc\uac04, \uac15\uc758\uc2e4, \uc778\uc6d0\uc744 \uc54c\ub824\uc8fc\uc138\uc694.\n"
                "\uc608: \ubaa8\ub808 \uc624\uc804 11\uc2dc\uc5d0 7202 \uac15\uc758\uc2e4 5\uba85",
                status=200,
            )

        if confirms_pending:
            res = handle_confirm_reservation({"ownerUid": uid}, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        if wants_cancel_reservation:
            direct_query = {"ownerUid": uid}
            if direct_room_id:
                direct_query["room"] = direct_room_id
            if direct_start:
                direct_query["startTime"] = direct_start.isoformat()
            res = handle_cancel_reservation(direct_query, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        if wants_my_reservations:
            res = handle_my_reservations({"ownerUid": uid}, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        if wants_change_reservation and not wants_alternative_room:
            direct_query = {"ownerUid": uid}
            if len(direct_room_ids) >= 2:
                direct_query["room"] = direct_room_ids[0]
                direct_query["newRoom"] = direct_room_ids[1]
            elif len(direct_room_ids) == 1:
                if direct_start or direct_participants is not None or direct_duration is not None:
                    direct_query["room"] = direct_room_ids[0]
                else:
                    direct_query["newRoom"] = direct_room_ids[0]
            if direct_start:
                direct_query["startTime"] = direct_start.isoformat()
            if pending_start_for_guard:
                direct_query["targetStartTime"] = pending_start_for_guard.isoformat()
            if direct_participants is not None:
                direct_query["eventParticipants"] = str(direct_participants)
            if direct_duration is not None:
                direct_query["duration"] = direct_duration
            if not any(key in direct_query for key in ("newRoom", "startTime", "eventParticipants", "duration")):
                return _store_direct_response(
                    "\ubcc0\uacbd\ud560 \ub0b4\uc6a9\uc744 \uc54c\ub824\uc8fc\uc138\uc694. "
                    "\uc608: '12\uc2dc\ub85c \ubcc0\uacbd\ud574\uc918', '5101 \uac15\uc758\uc2e4\ub85c \ubc14\uafd4\uc918', '6\uba85\uc73c\ub85c \ubcc0\uacbd\ud574\uc918'",
                    status=400,
                )
            res = handle_change_reservation(direct_query, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        should_handle_reservation_directly = (
            wants_alternative_room
            or (pending_doc_for_guard.exists and direct_participants is not None)
            or (is_reservation_request_text(user_input) and (direct_start or direct_room_id))
            or (direct_start and direct_room_id)
            or (wants_new_reservation and (direct_start or direct_room_id or direct_participants is not None))
        )
        if should_handle_reservation_directly:
            if wants_new_reservation:
                pending_ref.delete()
            direct_query = {"ownerUid": uid, "needsConfirmation": True}
            if direct_room_id:
                direct_query["room"] = direct_room_id
            if direct_start:
                direct_query["startTime"] = direct_start.isoformat()
            if direct_participants is not None:
                direct_query["eventParticipants"] = str(direct_participants)
            if wants_alternative_room:
                direct_query["allowAlternativeRoom"] = True
                if explicitly_changes_existing_reservation:
                    direct_query["explicitChangeReservation"] = True
                direct_query.pop("room", None)

            res = handle_reserve(direct_query, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        # ----------------------------------------------------
        # 2. Function Calling 도구(Tools) 정의
        # ----------------------------------------------------
        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(name="query_equipment", description="특정 강의실의 특정 기자재 유무 확인", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING"), "item": types.Schema(type="STRING")}, required=["room", "item"])),
                    types.FunctionDeclaration(name="reserve", description="강의실 예약 제안 또는 확정. 첫 예약 요청은 서버가 확인 메시지로 돌려주며, 사용자가 명시적으로 확정하면 confirmed=true로 호출하세요. 사용자가 빈 강의실을 알아서 예약해달라고 하면 room 파라미터를 생략할 수 있습니다.", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING", description="강의실 이름. 빈 강의실 알아서 예약시 생략가능"), "startTime": types.Schema(type="STRING"), "duration": types.Schema(type="INTEGER"), "eventParticipants": types.Schema(type="INTEGER"), "confirmed": types.Schema(type="BOOLEAN")}, required=["startTime", "eventParticipants"])),
                    types.FunctionDeclaration(name="confirm_reservation", description="사용자가 직전에 제안된 pending 예약을 '예약 확정', '네', '그걸로' 등으로 승인했을 때 호출", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="cancel_reservation", description="예약 취소. 강의실이나 시간이 없으면 사용자의 가장 가까운 예정 예약을 취소합니다.", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING"), "startTime": types.Schema(type="STRING")})),
                    types.FunctionDeclaration(name="change_reservation", description="예약 변경. room은 변경 대상 기존 예약의 강의실, newRoom은 새 강의실입니다. 시간/인원만 바꾸는 경우 newRoom은 생략합니다.", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING"), "newRoom": types.Schema(type="STRING"), "targetStartTime": types.Schema(type="STRING"), "startTime": types.Schema(type="STRING"), "duration": types.Schema(type="INTEGER"), "eventParticipants": types.Schema(type="INTEGER")})),
                    types.FunctionDeclaration(name="latest_notice", description="최신 공지 확인", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="my_reviews", description="내가 쓴 리뷰 확인", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="recommend_room", description="Recommend or search available lecture rooms. If the user mentioned a reservation time, pass it as ISO 8601 in afterTime or startTime. Also pass duration and eventParticipants when available.", parameters=types.Schema(type="OBJECT", properties={"keywords": types.Schema(type="ARRAY", items=types.Schema(type="STRING")), "afterTime": types.Schema(type="STRING"), "startTime": types.Schema(type="STRING"), "duration": types.Schema(type="INTEGER"), "eventParticipants": types.Schema(type="INTEGER")})),
                    types.FunctionDeclaration(name="review_summary", description="특정 강의실 리뷰 요약", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING")}, required=["room"])),
                    types.FunctionDeclaration(name="list_rooms", description="전체 강의실 조회", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="list_rooms_by_building", description="특정 건물 강의실 조회 (예: 5강의동)", parameters=types.Schema(type="OBJECT", properties={"building": types.Schema(type="STRING")}, required=["building"])),
                    types.FunctionDeclaration(name="list_rooms_by_equipment", description="특정 기자재 있는 강의실 조회", parameters=types.Schema(type="OBJECT", properties={"item": types.Schema(type="STRING")}, required=["item"])),
                    types.FunctionDeclaration(name="room_availability", description="특정 강의실의 오늘 예약 내역 확인", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING")}, required=["room"])),
                    types.FunctionDeclaration(name="my_reservations", description="내 예약 내역 확인", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="get_facility_rules", description="강의실 이용 수칙, 취소 규정, 기자재 사용법 등을 조회", parameters=types.Schema(type="OBJECT", properties={"query": types.Schema(type="STRING")}, required=["query"])),
                ]
            )
        ]

        now_kst = datetime.now(KST)
        system_prompt = f"""당신은 세종대학교 대양AI센터의 강의실 예약 및 안내를 돕는 AI 비서 '세종이'입니다.
항상 존댓말을 사용하고 이모지(😊)를 적절히 사용해 친절하게 응답하세요.

오늘 날짜와 현재 시간은 {now_kst.strftime('%Y-%m-%d %H:%M:%S KST')}입니다.
이를 기준으로 '내일', '모레', '오후 2시' 등의 시간을 정확한 ISO 8601 형식(예: 2025-03-15T14:00:00)으로 변환해 도구 파라미터로 넘기세요.

**중요 지침:**
- 단순 대화는 텍스트로 자연스럽게 답변하세요.
- 예약, 검색, 정보 조회가 필요하면 반드시 적절한 도구(Function)를 호출하세요.
- 예약을 확정(reserve)하려면 '시작 시간', '인원수'가 반드시 필요합니다.
- 첫 예약 요청에서는 예약 내용을 먼저 확인받아야 합니다. 서버가 확인 메시지를 반환하면 사용자에게 그대로 안내하세요.
- 사용자가 "예약 확정", "네", "그걸로", "진행해"처럼 방금 제안된 예약을 명시적으로 승인하면 confirm_reservation 도구를 호출하세요.
- 사용자가 "알아서 예약해줘", "빈 방 예약해줘" 등 강의실 이름을 명시하지 않고 예약을 원하면 직접 되묻지 말고, **'reserve' 도구의 'room' 파라미터를 생략**하여 서버가 빈 강의실을 찾아 예약 내용을 먼저 제안하도록 하세요.
- 절대 임의의 강의실이나 시간을 지어내지 마세요.
"""

        # ----------------------------------------------------
        # 3. LLM 호출
        # ----------------------------------------------------
        contents = chat_history + [{"role": "user", "parts": [{"text": user_input}]}]

        try:
            response = genai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=tools,
                    temperature=0.1
                )
            )
        except Exception:
            logging.exception("Gemini 호출 실패")
            return https_fn.Response("AI 서버가 혼잡하여 요청을 처리할 수 없어요. 잠시 후 다시 시도해 주세요.", status=503)

        bot_text = ""
        is_history_clear = False

        # ----------------------------------------------------
        # 4. 도구 호출(Function Calls) 처리
        # ----------------------------------------------------
        if response.function_calls:
            fc = response.function_calls[0]
            action = fc.name
            logging.info(f"[Function Call] {action} args: {fc.args}")
            
            if action == "get_facility_rules":
                bot_text = f"알려드릴게요! 🧐\n\n{FAQ_RULES}\n\n도움이 더 필요하신가요? 😊"
            else:
                query = {"action": action}
                for k, v in fc.args.items():
                    query[k] = v
                query["ownerUid"] = uid
                if action in {"reserve", "recommend_room"} and is_alternative_room_request(user_input):
                    query["allowAlternativeRoom"] = True
                    if is_explicit_change_reservation_request(user_input):
                        query["explicitChangeReservation"] = True
                    query.pop("room", None)
                
                if "room" in query and query["room"]:
                    room_id, _ = find_room(query["room"])
                    if room_id:
                        query["room"] = room_id
                if "newRoom" in query and query["newRoom"]:
                    new_room_id, _ = find_room(query["newRoom"])
                    if new_room_id:
                        query["newRoom"] = new_room_id

                pending_start_for_date = None
                if action in {"reserve", "change_reservation", "recommend_room", "cancel_reservation"}:
                    try:
                        pending_doc = db.collection("PendingReservations").document(userID).get()
                        if pending_doc.exists:
                            pending_start_raw = (pending_doc.to_dict() or {}).get("startTime")
                            if pending_start_raw:
                                pending_start_for_date = datetime.fromisoformat(str(pending_start_raw))
                                if pending_start_for_date.tzinfo is None:
                                    pending_start_for_date = pending_start_for_date.replace(tzinfo=KST)
                    except Exception as e:
                        logging.warning("[ai_assistant] Pending start date lookup failed: %s", e)

                inferred_start = parse_natural_korean_datetime(
                    user_input,
                    now_kst,
                    default_date=pending_start_for_date,
                )
                if inferred_start and action in {"reserve", "change_reservation", "recommend_room"}:
                    inferred_start_iso = inferred_start.isoformat()
                    if action == "recommend_room":
                        # Guardrail: recommend_room used to default to now+10min when the
                        # model omitted time. Preserve the user's explicit Korean time.
                        query["afterTime"] = inferred_start_iso
                        query["startTime"] = inferred_start_iso
                    else:
                        query["startTime"] = inferred_start_iso
                elif inferred_start and action == "cancel_reservation":
                    query["startTime"] = inferred_start.isoformat()

                if action == "recommend_room":
                    query["keywords"] = list(query.get("keywords", []))
                    if query.get("eventParticipants"):
                        query["eventParticipants"] = str(query["eventParticipants"])
                    if query.get("duration"):
                        query["duration"] = int(query["duration"])
                elif action in ["reserve", "change_reservation"]:
                    if query.get("eventParticipants"):
                        query["eventParticipants"] = str(query["eventParticipants"])
                    if query.get("duration"):
                        query["duration"] = int(query["duration"])
                    if action == "reserve" and not query.get("confirmed") and not is_reservation_confirmation(user_input):
                        query["needsConfirmation"] = True
                        
                if action in handlers:
                    res = handlers[action](query, userID)
                    bot_text = res.data.decode('utf-8') if hasattr(res, 'data') else str(res)
                    
                    if action == "reserve" and "예약되었습니다" in bot_text:
                        is_history_clear = True
                    elif action == "cancel_reservation" and "취소되었습니다" in bot_text:
                        is_history_clear = True
                else:
                    bot_text = "지원하지 않는 기능을 호출했어요."
        else:
            bot_text = (response.text or "응답을 생성하지 못했어요. 다시 시도해 주세요.").strip()

        # ----------------------------------------------------
        # 5. Chat History 업데이트
        # ----------------------------------------------------
        if is_history_clear:
            history_ref.delete()
        else:
            new_messages = [
                {"role": "user", "text": user_input},
                {"role": "model", "text": bot_text}
            ]
            history_ref.set(
                {
                    "messages": (stored_messages + new_messages)[-CHAT_HISTORY_MAX_MESSAGES:],
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                    "expiresAt": datetime.now(KST) + timedelta(days=CHAT_HISTORY_RETENTION_DAYS),
                },
                merge=True,
            )

        return https_fn.Response(bot_text, status=200)

    except Exception:
        logging.exception("예외 발생:")
        return https_fn.Response("알 수 없는 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)


def _delete_expired_chat_history(limit=450):
    now = datetime.now(KST)
    cutoff = now - timedelta(days=CHAT_HISTORY_RETENTION_DAYS)
    expired_docs = list(
        db.collection("ChatHistory")
        .where("expiresAt", "<=", now)
        .limit(limit)
        .stream()
    )
    deleted = 0

    batch = db.batch()
    for doc in expired_docs:
        batch.delete(doc.reference)
        deleted += 1
    if expired_docs:
        batch.commit()

    remaining_limit = max(limit - deleted, 0)
    if remaining_limit <= 0:
        return deleted

    legacy_docs = list(db.collection("ChatHistory").limit(remaining_limit).stream())
    batch = db.batch()
    operations = 0
    for doc in legacy_docs:
        data = doc.to_dict() or {}
        if data.get("expiresAt"):
            continue

        reference_time = data.get("updatedAt") or getattr(doc, "update_time", None)
        if not isinstance(reference_time, datetime):
            continue
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=KST)
        else:
            reference_time = reference_time.astimezone(KST)

        if reference_time <= cutoff:
            batch.delete(doc.reference)
            deleted += 1
        else:
            batch.update(
                doc.reference,
                {"expiresAt": reference_time + timedelta(days=CHAT_HISTORY_RETENTION_DAYS)},
            )
        operations += 1

    if operations:
        batch.commit()
    return deleted


@scheduler_fn.on_schedule(schedule="0 4 * * *", timezone="Asia/Seoul")
def cleanup_old_chat_history(event: scheduler_fn.ScheduledEvent) -> None:
    deleted = _delete_expired_chat_history()
    logging.info("Deleted %s expired ChatHistory documents.", deleted)
