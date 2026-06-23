package com.example.pick_dream.ui.mypage

import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import com.example.pick_dream.model.User
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore

/**
 * MypageFragment의 UI 상태를 관리하는 ViewModel.
 * 사용자 정보 조회는 Firestore를 통해 수행합니다.
 */
class MyPageViewModel : ViewModel() {

    private val _userData = MutableLiveData<User?>()
    val userData: LiveData<User?> get() = _userData

    fun loadUserData() {
        val uid = FirebaseAuth.getInstance().currentUser?.uid ?: run {
            Log.w("MyPageViewModel", "User not logged in.")
            return
        }

        FirebaseFirestore.getInstance()
            .collection("User").document(uid)
            .get()
            .addOnSuccessListener { doc ->
                val user = doc.toObject(User::class.java)
                if (user != null) {
                    _userData.value = user
                } else {
                    Log.w("MyPageViewModel", "User document is empty or malformed.")
                }
            }
            .addOnFailureListener { e ->
                Log.e("MyPageViewModel", "Failed to load user data", e)
            }
    }
}
