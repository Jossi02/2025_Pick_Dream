package com.example.pick_dream.notification

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat

object ReservationNotificationPreferences {
    private const val PREFS_NAME = "settings"

    const val KEY_RESERVATION_COMPLETE = "switch1"
    const val KEY_RESERVATION_CANCEL = "switch2"
    const val KEY_RESERVATION_USAGE_TIME = "switch3"

    fun setEnabled(context: Context, key: String, enabled: Boolean) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(key, enabled)
            .apply()
    }

    fun isEnabled(context: Context, key: String): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(key, false)
    }

    fun isReservationCompleteEnabled(context: Context): Boolean {
        return isEnabled(context, KEY_RESERVATION_COMPLETE)
    }

    fun isReservationCancelEnabled(context: Context): Boolean {
        return isEnabled(context, KEY_RESERVATION_CANCEL)
    }

    fun isReservationUsageTimeEnabled(context: Context): Boolean {
        return isEnabled(context, KEY_RESERVATION_USAGE_TIME)
    }

    fun hasPostNotificationPermission(context: Context): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.POST_NOTIFICATIONS
                ) == PackageManager.PERMISSION_GRANTED
    }
}
