package com.example.pick_dream.ui.home.reservation

import com.example.pick_dream.model.Reservation
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.Query
import com.google.firebase.firestore.ktx.firestore
import com.google.firebase.firestore.ktx.toObject
import com.google.firebase.ktx.Firebase
import kotlinx.coroutines.tasks.await

object ReservationRepository {
    private val db = Firebase.firestore

    /**
     * 특정 유저(학번)의 예약 목록을 최신순으로 가져옵니다.
     */
    suspend fun getReservationsByUser(studentId: String): List<Reservation> {
        return try {
            val snapshot = db.collection("Reservations")
                .whereEqualTo("userID", studentId)
                // 인덱스 오류 방지를 위해 orderBy 제거 후 앱 단에서 정렬
                .get()
                .await()

            snapshot.documents.mapNotNull { doc ->
                doc.toObject<Reservation>()?.apply { documentId = doc.id }
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    /**
     * 특정 방의 예약 목록을 가져옵니다.
     */
    suspend fun getReservationsByRoom(roomId: String): List<Reservation> {
        return try {
            val snapshot = db.collection("Reservations")
                .whereEqualTo("roomID", roomId)
                .get()
                .await()

            snapshot.documents.mapNotNull { doc ->
                doc.toObject<Reservation>()?.apply { documentId = doc.id }
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    /**
     * 예약 목록의 방 ID들을 기반으로 방 이미지를 가져옵니다.
     */
    suspend fun getRoomImages(roomIds: List<String>): Map<String, String?> {
        val uniqueIds = roomIds.distinct().filter { it.isNotBlank() }
        if (uniqueIds.isEmpty()) return emptyMap()

        val map = mutableMapOf<String, String?>()
        try {
            // Note: Firestore의 in 쿼리는 최대 10개까지 가능하므로, 
            // 예약 수가 많을 경우 청크로 나누거나 개별 조회가 필요할 수 있음.
            // 기존 로직은 개별 조회를 Tasks.whenAllSuccess 로 처리했음. 코루틴으로 개별 조회 진행
            uniqueIds.forEach { roomId ->
                val doc = db.collection("rooms").document(roomId).get().await()
                if (doc.exists()) {
                    map[roomId] = doc.getString("image")
                }
            }
        } catch (e: Exception) {
            // 실패 시 빈 맵 반환 (기본 이미지 처리를 위해)
        }
        return map
    }

    /**
     * 새로운 예약을 추가합니다.
     */
    suspend fun addReservation(reservation: Reservation): Boolean {
        return try {
            val ownerUid = FirebaseAuth.getInstance().currentUser?.uid ?: return false
            db.collection("Reservations")
                .add(reservation.copy(ownerUid = ownerUid))
                .await()
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * 특정 예약을 취소(삭제)합니다.
     */
    suspend fun cancelReservation(documentId: String): Boolean {
        return try {
            db.collection("Reservations").document(documentId).delete().await()
            true
        } catch (e: Exception) {
            false
        }
    }
}
