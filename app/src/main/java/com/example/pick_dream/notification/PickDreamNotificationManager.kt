package com.example.pick_dream.notification

import android.annotation.SuppressLint
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.example.pick_dream.MainActivity
import com.example.pick_dream.R
import com.example.pick_dream.model.Reservation
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import java.util.TimeZone

object PickDreamNotificationManager {
    private const val CHANNEL_ID = "reservation_notifications"
    private const val CHANNEL_NAME = "강의실 예약 알림"
    private const val CHANNEL_DESCRIPTION = "강의실 예약 완료, 취소, 이용 시간 알림"
    private const val USAGE_REMINDER_OFFSET_MILLIS = 10 * 60 * 1000L

    const val EXTRA_NOTIFICATION_ID = "notification_id"
    const val EXTRA_TITLE = "title"
    const val EXTRA_BODY = "body"
    const val EXTRA_USER_ID = "user_id"
    const val EXTRA_ROOM_ID = "room_id"
    const val EXTRA_START_TIME = "start_time"
    const val EXTRA_END_TIME = "end_time"

    fun createChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        val channel = NotificationChannel(
            CHANNEL_ID,
            CHANNEL_NAME,
            NotificationManager.IMPORTANCE_DEFAULT
        ).apply {
            description = CHANNEL_DESCRIPTION
        }

        val notificationManager =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.createNotificationChannel(channel)
    }

    fun showReservationComplete(context: Context, reservation: Reservation) {
        if (!ReservationNotificationPreferences.isReservationCompleteEnabled(context)) return

        showNotification(
            context = context,
            notificationId = nextNotificationId(),
            title = "강의실 예약 완료",
            body = buildReservationBody(reservation, "예약이 완료되었습니다.")
        )
    }

    fun showReservationComplete(context: Context, roomName: String? = null) {
        if (!ReservationNotificationPreferences.isReservationCompleteEnabled(context)) return

        val target = roomName?.takeIf { it.isNotBlank() } ?: "강의실"
        showNotification(
            context = context,
            notificationId = nextNotificationId(),
            title = "강의실 예약 완료",
            body = "$target 예약이 완료되었습니다."
        )
    }

    fun showReservationCanceled(context: Context, reservation: Reservation) {
        if (!ReservationNotificationPreferences.isReservationCancelEnabled(context)) return

        showNotification(
            context = context,
            notificationId = nextNotificationId(),
            title = "강의실 예약 취소",
            body = buildReservationBody(reservation, "예약이 취소되었습니다.")
        )
    }

    fun showReservationCanceled(context: Context, roomName: String? = null) {
        if (!ReservationNotificationPreferences.isReservationCancelEnabled(context)) return

        val target = roomName?.takeIf { it.isNotBlank() } ?: "강의실"
        showNotification(
            context = context,
            notificationId = nextNotificationId(),
            title = "강의실 예약 취소",
            body = "$target 예약이 취소되었습니다."
        )
    }

    fun scheduleUsageReminder(context: Context, reservation: Reservation) {
        if (!ReservationNotificationPreferences.isReservationUsageTimeEnabled(context)) return

        val startTime = reservation.startTime ?: return
        val startCal = parseKoreanDateToCalendar(startTime) ?: return
        val now = System.currentTimeMillis()
        if (startCal.timeInMillis <= now) return

        val reminderAt = (startCal.timeInMillis - USAGE_REMINDER_OFFSET_MILLIS)
            .takeIf { it > now }
            ?: startCal.timeInMillis

        val notificationId = requestCodeFor(reservation)
        val intent = Intent(context, ReservationAlarmReceiver::class.java).apply {
            putExtra(EXTRA_NOTIFICATION_ID, notificationId)
            putExtra(EXTRA_TITLE, "강의실 이용 시간 알림")
            putExtra(EXTRA_BODY, buildUsageReminderBody(reservation, reminderAt, startCal.timeInMillis))
            putExtra(EXTRA_USER_ID, reservation.userID)
            putExtra(EXTRA_ROOM_ID, reservation.roomID)
            putExtra(EXTRA_START_TIME, reservation.startTime)
            putExtra(EXTRA_END_TIME, reservation.endTime)
        }

        val pendingIntent = PendingIntent.getBroadcast(
            context,
            notificationId,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, reminderAt, pendingIntent)
        } else {
            alarmManager.set(AlarmManager.RTC_WAKEUP, reminderAt, pendingIntent)
        }
    }

    fun cancelUsageReminder(context: Context, reservation: Reservation) {
        val notificationId = requestCodeFor(reservation)
        val pendingIntent = PendingIntent.getBroadcast(
            context,
            notificationId,
            Intent(context, ReservationAlarmReceiver::class.java),
            PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
        )

        if (pendingIntent != null) {
            val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            alarmManager.cancel(pendingIntent)
            pendingIntent.cancel()
        }
    }

    fun showUsageReminderFromAlarm(context: Context, notificationId: Int, title: String, body: String) {
        if (!ReservationNotificationPreferences.isReservationUsageTimeEnabled(context)) return
        showNotification(context, notificationId, title, body)
    }

    @SuppressLint("MissingPermission")
    private fun showNotification(
        context: Context,
        notificationId: Int,
        title: String,
        body: String
    ) {
        if (!ReservationNotificationPreferences.hasPostNotificationPermission(context)) return

        createChannels(context)

        val contentIntent = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(contentIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()

        NotificationManagerCompat.from(context).notify(notificationId, notification)
    }

    private fun buildReservationBody(reservation: Reservation, suffix: String): String {
        val roomName = reservation.roomID.takeIf { it.isNotBlank() }?.let { "$it 강의실" } ?: "강의실"
        val timeText = buildTimeRangeText(reservation)
        return if (timeText.isBlank()) {
            "$roomName $suffix"
        } else {
            "$roomName $suffix\n$timeText"
        }
    }

    private fun buildUsageReminderBody(
        reservation: Reservation,
        reminderAtMillis: Long,
        startAtMillis: Long
    ): String {
        val roomName = reservation.roomID.takeIf { it.isNotBlank() }?.let { "$it 강의실" } ?: "강의실"
        val prefix = if (startAtMillis - reminderAtMillis >= USAGE_REMINDER_OFFSET_MILLIS) {
            "10분 뒤"
        } else {
            "곧"
        }
        val timeText = buildTimeRangeText(reservation)
        return if (timeText.isBlank()) {
            "$prefix $roomName 이용이 시작됩니다."
        } else {
            "$prefix $roomName 이용이 시작됩니다.\n$timeText"
        }
    }

    private fun buildTimeRangeText(reservation: Reservation): String {
        val startCal = reservation.startTime?.let { parseKoreanDateToCalendar(it) }
        val endCal = reservation.endTime?.let { parseKoreanDateToCalendar(it) }
        if (startCal == null || endCal == null) return ""

        val dateFormat = SimpleDateFormat("M월 d일(E)", Locale.KOREAN).apply {
            timeZone = TimeZone.getTimeZone("Asia/Seoul")
        }
        val timeFormat = SimpleDateFormat("a h:mm", Locale.KOREAN).apply {
            timeZone = TimeZone.getTimeZone("Asia/Seoul")
        }

        return "${dateFormat.format(startCal.time)} ${timeFormat.format(startCal.time)} ~ ${timeFormat.format(endCal.time)}"
    }

    private fun parseKoreanDateToCalendar(dateString: String): Calendar? {
        val normalized = dateString
            .replace("PM", "오후", ignoreCase = true)
            .replace("AM", "오전", ignoreCase = true)

        val formats = listOf(
            "yyyy년 M월 d일 a h시 m분 s초 'UTC+9'",
            "yyyy년 M월 d일 a h시 m분 s초",
            "yyyy년 M월 d일 a h시 m분"
        ).map {
            SimpleDateFormat(it, Locale.KOREAN).apply {
                timeZone = TimeZone.getTimeZone("Asia/Seoul")
            }
        }

        for (format in formats) {
            try {
                return Calendar.getInstance(TimeZone.getTimeZone("Asia/Seoul")).apply {
                    time = format.parse(normalized) ?: return null
                }
            } catch (_: Exception) {
            }
        }
        return null
    }

    private fun requestCodeFor(reservation: Reservation): Int {
        val key = listOf(
            reservation.userID,
            reservation.roomID,
            reservation.startTime.orEmpty(),
            reservation.endTime.orEmpty()
        ).joinToString("|")
        return key.hashCode() and 0x7fffffff
    }

    private fun nextNotificationId(): Int {
        return (System.currentTimeMillis() % Int.MAX_VALUE).toInt()
    }
}
