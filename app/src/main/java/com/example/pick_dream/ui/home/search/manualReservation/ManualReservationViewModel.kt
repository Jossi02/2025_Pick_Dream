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

    fun makeReservation(reservation: Reservation) {
        _isSubmitting.value = true
        viewModelScope.launch {
            val success = ReservationRepository.addReservation(reservation)
            _submitResult.value = success
            _isSubmitting.value = false
        }
    }

    fun clearSubmitResult() {
        _submitResult.value = null
    }
}
