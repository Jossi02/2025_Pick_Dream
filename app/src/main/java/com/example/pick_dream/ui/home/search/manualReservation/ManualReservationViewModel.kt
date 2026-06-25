package com.example.pick_dream.ui.home.search.manualReservation

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.pick_dream.model.Reservation
import com.example.pick_dream.ui.home.reservation.ReservationRepository
import com.prolificinteractive.materialcalendarview.CalendarDay
import kotlinx.coroutines.launch

class ManualReservationViewModel : ViewModel() {
    var selectedDay: CalendarDay? = null
    var startHour: Int? = null
    var startMinute: Int? = null
    var endHour: Int? = null
    var endMinute: Int? = null
    var selectedEquipments: List<String> = emptyList()

    private val _isSubmitting = MutableLiveData<Boolean>()
    val isSubmitting: LiveData<Boolean> get() = _isSubmitting

    private val _submitResult = MutableLiveData<Boolean?>()
    val submitResult: LiveData<Boolean?> get() = _submitResult
    
    private val _errorMessage = MutableLiveData<String?>()
    val errorMessage: LiveData<String?> get() = _errorMessage

    fun makeReservation(reservation: Reservation) {
        _isSubmitting.value = true
        viewModelScope.launch {
            try {
                // 1. Fetch existing reservations for this room
                val existingReservations = ReservationRepository.getReservationsByRoom(reservation.roomID)
                
                // 2. Check for time overlaps
                val format = java.text.SimpleDateFormat("yyyy년 M월 d일 a h시 m분 s초 'UTC+9'", java.util.Locale.KOREA)
                
                val newStartMs = format.parse(reservation.startTime!!)?.time ?: 0L
                val newEndMs = format.parse(reservation.endTime!!)?.time ?: 0L
                
                var isOverlapping = false
                for (res in existingReservations) {
                    if (res.status == "취소" || res.status == "거절") continue
                    if (res.startTime.isNullOrBlank() || res.endTime.isNullOrBlank()) continue
                    
                    val existingStartMs = format.parse(res.startTime)?.time ?: 0L
                    val existingEndMs = format.parse(res.endTime)?.time ?: 0L
                    
                    if (newStartMs < existingEndMs && newEndMs > existingStartMs) {
                        isOverlapping = true
                        break
                    }
                }
                
                if (isOverlapping) {
                    _errorMessage.value = "이미 예약된 시간입니다."
                    _submitResult.value = false
                } else {
                    val success = ReservationRepository.addReservation(reservation)
                    if (!success) {
                        _errorMessage.value = "예약 중 오류가 발생했습니다."
                    }
                    _submitResult.value = success
                }
            } catch (e: Exception) {
                _errorMessage.value = "예약 처리 중 오류가 발생했습니다."
                _submitResult.value = false
            } finally {
                _isSubmitting.value = false
            }
        }
    }

    fun clearSubmitResult() {
        _submitResult.value = null
        _errorMessage.value = null
    }
}
