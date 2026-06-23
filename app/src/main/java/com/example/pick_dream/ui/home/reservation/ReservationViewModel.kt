package com.example.pick_dream.ui.home.reservation

import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.pick_dream.model.Reservation
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

class ReservationViewModel : ViewModel() {

    private val _listItems = MutableLiveData<List<ReservationListItem>>()
    val listItems: LiveData<List<ReservationListItem>> get() = _listItems

    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> get() = _isLoading

    private val _message = MutableLiveData<String>()
    val message: LiveData<String> get() = _message

    fun loadReservations() {
        val currentUser = FirebaseAuth.getInstance().currentUser ?: return
        _isLoading.value = true

        viewModelScope.launch {
            try {
                // User 컬렉션에서 studentId 가져오기
                val userDoc = FirebaseFirestore.getInstance()
                    .collection("User").document(currentUser.uid).get().await()
                
                val studentId = userDoc.getString("studentId") ?: userDoc.getString("userID")
                if (studentId.isNullOrBlank()) {
                    _listItems.value = emptyList()
                    _isLoading.value = false
                    return@launch
                }

                // 학번으로 예약 목록 조회
                val reservations = ReservationRepository.getReservationsByUser(studentId)
                if (reservations.isEmpty()) {
                    _listItems.value = emptyList()
                    _isLoading.value = false
                    return@launch
                }

                // 룸 이미지 조회
                val roomIds = reservations.map { it.roomID }
                val roomImageUrls = ReservationRepository.getRoomImages(roomIds)

                // 예약 분류 및 정렬
                val now = java.util.Date()
                val upcoming = mutableListOf<Reservation>()
                val past = mutableListOf<Reservation>()

                reservations.forEach { res ->
                    val endTime = parseFlexibleDate(res.endTime)
                    if (endTime != null && endTime.after(now)) {
                        upcoming.add(res)
                    } else {
                        past.add(res)
                    }
                }

                upcoming.sortBy { parseFlexibleDate(it.startTime)?.time ?: Long.MAX_VALUE }

                val items = mutableListOf<ReservationListItem>()
                if (upcoming.isNotEmpty()) {
                    items.add(ReservationListItem.Header("현재 예약 및 예정된 예약"))
                    items.addAll(upcoming.map { ReservationListItem.ReservationItem(it, roomImageUrls[it.roomID]) })
                }
                if (past.isNotEmpty()) {
                    items.add(ReservationListItem.Header("지난 예약"))
                    items.addAll(past.map { ReservationListItem.ReservationItem(it, roomImageUrls[it.roomID]) })
                }

                _listItems.value = items
            } catch (e: Exception) {
                Log.e("ReservationViewModel", "Failed to load reservations", e)
                _message.value = "예약 정보를 불러오는데 실패했습니다."
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun cancelReservation(reservation: Reservation) {
        val docId = reservation.documentId
        if (docId.isBlank()) {
            _message.value = "예약 ID가 없어 취소할 수 없습니다."
            return
        }

        viewModelScope.launch {
            _isLoading.value = true
            val success = ReservationRepository.cancelReservation(docId)
            if (success) {
                _message.value = "예약이 취소되었습니다."
                loadReservations() // 새로고침
            } else {
                _message.value = "예약 취소에 실패했습니다."
                _isLoading.value = false
            }
        }
    }

    private fun parseFlexibleDate(dateString: String?): java.util.Date? {
        if (dateString.isNullOrBlank()) return null

        val normalized = dateString
            .replace("PM", "오후", ignoreCase = true)
            .replace("AM", "오전", ignoreCase = true)

        val formats = listOf(
            java.text.SimpleDateFormat("yyyy년 M월 d일 a h시 m분 s초 'UTC+9'", java.util.Locale.KOREAN),
            java.text.SimpleDateFormat("yyyy년 M월 d일 a h시 m분 s초", java.util.Locale.KOREAN),
            java.text.SimpleDateFormat("yyyy년 M월 d일 a h시 m분", java.util.Locale.KOREAN)
        )

        for (format in formats) {
            try { return format.parse(normalized) } catch (e: Exception) { }
        }
        return null
    }
}
