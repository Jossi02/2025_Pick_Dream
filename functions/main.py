from firebase_functions import https_fn
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
    reservation_room_id,
)

# 환경 설정
load_dotenv()
initialize_app()

db = firestore.client()
# API Key 기반 클라이언트 설정 (Vertex AI 자동 전환 방지)
api_key = os.environ.get("GEMINI_API_KEY")
genai_client = genai.Client(api_key=api_key, vertexai=False)

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

        pending = db.collection("PendingReservations").document(userID).get()
        if pending.exists:
            pending_data = pending.to_dict()
            if not room_id and not room_raw:
                room_id, room_data = find_room(pending_data.get("room"))
            for field in ("startTime", "duration", "eventName", "eventParticipants"):
                query[field] = query.get(field) or pending_data.get(field)
        query["duration"] = query.get("duration") or 2

        if not room_id and query.get("room"):
            return https_fn.Response("해당 강의실 정보를 확인할 수 없어요.", status=400)
            
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
                
            matched = []
            for doc in db.collection("rooms").stream():
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

        if has_conflict("userID", userID, start, end):
            return https_fn.Response("해당 시간에 이미 예약한 강의실이 있어요. 다른 시간대를 선택해 주세요.", status=409)
            
        _, room_data = find_room(query["room"])
        if has_conflict("roomID", query["room"], start, end):
            room_name = room_data.get("name", query["room"]) if room_data else query["room"]
            return https_fn.Response(f"{room_name}은 해당 시간에 이미 예약되어 있어요.", status=409)

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
            doc_ref = db.collection("Reservations").add(res_doc)
        except Exception as e:
            logging.exception("[handle_reserve] 예약 저장 실패")
            return https_fn.Response("예약 저장 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)

        try:
            db.collection("PendingReservations").document(userID).delete()
        except Exception as e:
            logging.warning(f"[handle_reserve] Pending 삭제 실패: {e}")

        logging.info(f"[handle_reserve] 예약 성공: {doc_ref[1].id}")
        room_name = room_data.get("name", query["room"]) if room_data else query["room"]
        return https_fn.Response(f"{room_name}이 예약되었습니다 ✅", status=200)

    except Exception as e:
        logging.exception("[handle_reserve] 최상위 예외 발생")
        return https_fn.Response("예약 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)



def handle_cancel_reservation(query, userID):
    try:
        target_room_id, target_room_data = find_room(query.get("room"))
        target_reservation_room_id = (
            reservation_room_id(target_room_id, target_room_data)
            if target_room_id and target_room_data
            else None
        )
        logging.info(
            "[handle_cancel_reservation] target_room_id=%s, "
            "target_reservation_room_id=%s, userID=%s",
            target_room_id,
            target_reservation_room_id,
            userID,
        )

        # 가장 최근 예약 1건 조회 (startTime 기준)
        col = db.collection("Reservations").where("userID", "==", userID)
        if target_reservation_room_id:
            col = col.where("roomID", "==", target_reservation_room_id)
        
        # .limit(1)을 추가하여 가장 최근 예약 1건만 가져옴
        docs_query = col.order_by("startTimestamp", direction=firestore.Query.DESCENDING).limit(1)

        try:
            # 쿼리를 실행하여 문서 목록을 가져옴
            docs = list(docs_query.stream())
        except Exception as e:
            logging.exception("[handle_cancel_reservation] 예약 조회 실패")
            return https_fn.Response("예약 조회 중 문제가 발생했어요. 로그를 확인해주세요.", status=500)

        if not docs:
            return https_fn.Response("취소할 예약이 없습니다.", status=404)

        # 첫 번째 (가장 최근) 문서만 처리
        doc_to_delete = docs[0]
        cancelled_room_id = doc_to_delete.to_dict().get("roomID")
        _, cancelled_room_data = find_room(cancelled_room_id)
        cancelled_room_name = cancelled_room_data.get("name", cancelled_room_id) if cancelled_room_data else cancelled_room_id
        db.collection("Reservations").document(doc_to_delete.id).delete()

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
        logging.info(
            "[handle_change_reservation] target_room_id=%s, "
            "target_reservation_room_id=%s, userID=%s",
            target_room_id,
            target_reservation_room_id,
            userID,
        )

        col = db.collection("Reservations").where("userID", "==", userID)
        if target_reservation_room_id:
            col = col.where("roomID", "==", target_reservation_room_id)
        
        docs_query = col.order_by("startTimestamp", direction=firestore.Query.DESCENDING).limit(1)
        docs = list(docs_query.stream())

        if not docs:
            return https_fn.Response("변경할 예약이 없습니다.", status=404)

        doc_to_update = docs[0]
        res_data = doc_to_update.to_dict()
        res_id = doc_to_update.id

        new_duration = query.get("duration")
        new_participants = query.get("eventParticipants")
        new_start_time = query.get("startTime")

        start = res_data.get("startTimestamp")
        end = res_data.get("endTimestamp")
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
        if has_conflict("roomID", res_data.get("roomID"), start, end, exclude_id=res_id):
            return https_fn.Response("해당 시간에 이미 강의실이 예약되어 있어요.", status=409)

        update_data = {
            "startTime": format_korean_time(start),
            "endTime": format_korean_time(end),
            "startTimestamp": start,
            "endTimestamp": end,
        }

        if new_participants:
            participants_str = str(new_participants).strip()
            numeric_part = re.search(r'\d+', participants_str)
            if numeric_part:
                update_data["eventParticipants"] = int(numeric_part.group())

        db.collection("Reservations").document(res_id).update(update_data)
        
        _, room_data = find_room(res_data.get("roomID"))
        room_name = room_data.get("name", res_data.get("roomID")) if room_data else res_data.get("roomID")
        
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
            if has_conflict("roomID", room_id, base_time, base_time + timedelta(minutes=1)):
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
🏫 강의실: {best.get("name", room_id)} (최대 {capacity}명)
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
        "duration": query.get("duration", 2),
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
    room_name = room_data.get("name", room_id)
    now = datetime.now(KST)
    one_day_later = now + timedelta(days=1)
    docs = db.collection("Reservations") \
        .where("roomID", "==", room_id) \
        .where("startTimestamp", ">", now) \
        .where("startTimestamp", "<", one_day_later).stream()
    times = [d.to_dict().get("startTime", "?") for d in docs]
    if not times:
        return https_fn.Response(f"{room_name}은 앞으로 24시간 예약이 없습니다.", status=200)
    return https_fn.Response(f"{room_name} 예약 시간 목록: {', '.join(times)}", status=200)

def handle_my_reservations(query, userID):
    docs = db.collection("Reservations").where("userID", "==", userID).stream()
    res_list = []
    rooms_cache = {}
    for doc in db.collection("rooms").stream():
        rooms_cache[doc.id] = doc.to_dict().get("name", doc.id)
        
    for d in docs:
        data = d.to_dict()
        room_id = data.get('roomID')
        room_name = rooms_cache.get(room_id, room_id)
        res_list.append(f"{room_name} ({data.get('startTime', '?')} ~ {data.get('endTime', '?')})")
    if not res_list:
        return https_fn.Response("예약된 강의실이 없습니다.", status=200)
    return https_fn.Response("내 예약 내역:\n" + "\n".join(res_list), status=200)

handlers = {
    "query_equipment": handle_query_equipment,
    "reserve": handle_reserve,
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

        # ----------------------------------------------------
        # 2. Function Calling 도구(Tools) 정의
        # ----------------------------------------------------
        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(name="query_equipment", description="특정 강의실의 특정 기자재 유무 확인", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING"), "item": types.Schema(type="STRING")}, required=["room", "item"])),
                    types.FunctionDeclaration(name="reserve", description="특정 강의실 예약. 사용자가 빈 강의실을 알아서 예약해달라고 하면 room 파라미터를 생략해서 호출하세요.", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING", description="강의실 이름. 빈 강의실 알아서 예약시 생략가능"), "startTime": types.Schema(type="STRING"), "duration": types.Schema(type="INTEGER"), "eventParticipants": types.Schema(type="INTEGER")}, required=["startTime", "eventParticipants"])),
                    types.FunctionDeclaration(name="cancel_reservation", description="예약 취소", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING")}, required=["room"])),
                    types.FunctionDeclaration(name="change_reservation", description="예약 변경", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING"), "startTime": types.Schema(type="STRING"), "duration": types.Schema(type="INTEGER"), "eventParticipants": types.Schema(type="INTEGER")}, required=["room"])),
                    types.FunctionDeclaration(name="latest_notice", description="최신 공지 확인", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="my_reviews", description="내가 쓴 리뷰 확인", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="recommend_room", description="조건에 맞는 빈 강의실 추천/검색. 예약 의사가 있으나 조건이 다 채워지지 않았을 때도 호출.", parameters=types.Schema(type="OBJECT", properties={"keywords": types.Schema(type="ARRAY", items=types.Schema(type="STRING")), "afterTime": types.Schema(type="STRING")})),
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
- 사용자가 "알아서 예약해줘", "빈 방 예약해줘" 등 강의실 이름을 명시하지 않고 예약을 원하면 직접 되묻지 말고, **'reserve' 도구의 'room' 파라미터를 생략**하여 즉시 알아서 예약되도록 하세요.
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
                
                if "room" in query and query["room"]:
                    room_id, _ = find_room(query["room"])
                    if room_id:
                        query["room"] = room_id

                if action == "recommend_room":
                    query["keywords"] = list(query.get("keywords", []))
                elif action in ["reserve", "change_reservation"]:
                    if query.get("eventParticipants"):
                        query["eventParticipants"] = str(query["eventParticipants"])
                    if query.get("duration"):
                        query["duration"] = int(query["duration"])
                        
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
            history_ref.set({"messages": (stored_messages + new_messages)[-10:]}, merge=True)

        return https_fn.Response(bot_text, status=200)

    except Exception:
        logging.exception("예외 발생:")
        return https_fn.Response("알 수 없는 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)
