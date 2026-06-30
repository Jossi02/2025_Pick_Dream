package com.example.pick_dream.notification

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.google.firebase.firestore.FirebaseFirestore

class ReservationAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!ReservationNotificationPreferences.isReservationUsageTimeEnabled(context)) return

        val notificationId = intent.getIntExtra(
            PickDreamNotificationManager.EXTRA_NOTIFICATION_ID,
            0
        )
        val title = intent.getStringExtra(PickDreamNotificationManager.EXTRA_TITLE)
            ?: "강의실 이용 시간 알림"
        val body = intent.getStringExtra(PickDreamNotificationManager.EXTRA_BODY)
            ?: "예약한 강의실 이용 시간이 다가왔습니다."
        val userId = intent.getStringExtra(PickDreamNotificationManager.EXTRA_USER_ID).orEmpty()
        val roomId = intent.getStringExtra(PickDreamNotificationManager.EXTRA_ROOM_ID).orEmpty()
        val startTime = intent.getStringExtra(PickDreamNotificationManager.EXTRA_START_TIME).orEmpty()
        val endTime = intent.getStringExtra(PickDreamNotificationManager.EXTRA_END_TIME).orEmpty()

        if (userId.isBlank() || roomId.isBlank() || startTime.isBlank()) {
            PickDreamNotificationManager.showUsageReminderFromAlarm(
                context,
                notificationId,
                title,
                body
            )
            return
        }

        val pendingResult = goAsync()
        FirebaseFirestore.getInstance()
            .collection("Reservations")
            .whereEqualTo("userID", userId)
            .whereEqualTo("roomID", roomId)
            .get()
            .addOnSuccessListener { snapshot ->
                val reservationStillExists = snapshot.documents.any { doc ->
                    val status = doc.getString("status").orEmpty()
                    doc.getString("startTime") == startTime &&
                            (endTime.isBlank() || doc.getString("endTime") == endTime) &&
                            status != "취소" &&
                            status != "거절"
                }

                if (reservationStillExists) {
                    PickDreamNotificationManager.showUsageReminderFromAlarm(
                        context,
                        notificationId,
                        title,
                        body
                    )
                }
                pendingResult.finish()
            }
            .addOnFailureListener {
                pendingResult.finish()
            }
    }
}
