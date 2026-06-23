package com.example.pick_dream.ui.mypage.review

import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.pick_dream.model.Review
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

class ReviewViewModel : ViewModel() {

    private val _reviews = MutableLiveData<List<Review>>()
    val reviews: LiveData<List<Review>> get() = _reviews

    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> get() = _isLoading

    private val _message = MutableLiveData<String>()
    val message: LiveData<String> get() = _message

    fun loadReviews() {
        val uid = FirebaseAuth.getInstance().currentUser?.uid ?: return
        _isLoading.value = true

        viewModelScope.launch {
            try {
                // User 컬렉션에서 studentId 가져오기
                val userDoc = FirebaseFirestore.getInstance().collection("User").document(uid).get().await()
                val studentId = userDoc.getString("studentId")

                if (studentId.isNullOrBlank()) {
                    _message.value = "학번 정보를 찾을 수 없습니다."
                    _reviews.value = emptyList()
                    _isLoading.value = false
                    return@launch
                }

                // 학번을 기준으로 리뷰 목록 조회
                val reviewList = ReviewRepository.getReviewsByUser(studentId)
                _reviews.value = reviewList

            } catch (e: Exception) {
                Log.e("ReviewViewModel", "리뷰 로딩 실패", e)
                _message.value = "리뷰 목록을 불러오는데 실패했습니다."
            } finally {
                _isLoading.value = false
            }
        }
    }
}
