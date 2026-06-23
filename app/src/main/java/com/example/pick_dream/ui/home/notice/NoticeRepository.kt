package com.example.pick_dream.ui.home.notice

import com.example.pick_dream.model.Notice
import com.google.firebase.firestore.ktx.firestore
import com.google.firebase.ktx.Firebase
import kotlinx.coroutines.tasks.await
import java.text.SimpleDateFormat
import java.util.Locale

object NoticeRepository {
    private val db = Firebase.firestore
    private val formatter = SimpleDateFormat("yy.MM.dd", Locale.getDefault())

    /**
     * Firestore에서 모든 공지사항을 가져옵니다.
     */
    suspend fun fetchAllNotices(): List<Notice> {
        return try {
            val result = db.collection("Notices").get().await()
            result.map { doc ->
                val timestamp = doc.getTimestamp("createdAt")
                val formattedDate = timestamp?.toDate()?.let { formatter.format(it) } ?: ""

                Notice(
                    id = doc.id,
                    iconEmoji = "📢", // 기본 이모지, 뷰모델/어댑터에서 타이틀에 따라 이벤트 아이콘으로 변경 가능
                    title = doc.getString("title") ?: "",
                    date = formattedDate,
                    content = doc.getString("content") ?: ""
                )
            }.sortedByDescending { it.date } // 최신순 정렬 보장
        } catch (e: Exception) {
            emptyList()
        }
    }
}
