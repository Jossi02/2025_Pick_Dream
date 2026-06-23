package com.example.pick_dream.ui.mypage.review

import com.example.pick_dream.model.Review
import com.google.firebase.firestore.Query
import com.google.firebase.firestore.ktx.firestore
import com.google.firebase.ktx.Firebase
import kotlinx.coroutines.tasks.await

object ReviewRepository {
    private val db = Firebase.firestore

    /**
     * 특정 유저(학번)가 작성한 리뷰 목록을 최신순으로 가져옵니다.
     */
    suspend fun getReviewsByUser(studentId: String): List<Review> {
        return try {
            val snapshot = db.collection("Reviews")
                .whereEqualTo("userID", studentId)
                .orderBy("createdAt", Query.Direction.DESCENDING)
                .get()
                .await()

            snapshot.toObjects(Review::class.java)
        } catch (e: Exception) {
            emptyList()
        }
    }

    /**
     * 새로운 리뷰를 Firestore에 추가합니다.
     */
    suspend fun addReview(review: Review): Boolean {
        return try {
            db.collection("Reviews").add(review).await()
            true
        } catch (e: Exception) {
            false
        }
    }
}
