package com.example.pick_dream.ui.mypage.setting

import android.Manifest
import android.os.Bundle
import android.widget.ImageButton
import android.view.View
import android.widget.ImageView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import com.example.pick_dream.R
import com.example.pick_dream.notification.PickDreamNotificationManager
import com.example.pick_dream.notification.ReservationNotificationPreferences

class SettingActivity : AppCompatActivity() {
    private lateinit var backButton: ImageButton
    private lateinit var switch1: SwitchCompat
    private lateinit var switch2: SwitchCompat
    private lateinit var switch3: SwitchCompat
    private lateinit var checkKorean: ImageView
    private lateinit var checkEnglish: ImageView
    private lateinit var checkJapanese: ImageView
    private lateinit var checkChinese: ImageView
    private var pendingNotificationSwitch: SwitchCompat? = null
    private var pendingNotificationKey: String? = null
    private var isUpdatingSwitchState = false

    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { isGranted ->
            val switch = pendingNotificationSwitch
            val key = pendingNotificationKey
            pendingNotificationSwitch = null
            pendingNotificationKey = null

            if (switch == null || key == null) return@registerForActivityResult

            if (isGranted) {
                ReservationNotificationPreferences.setEnabled(this, key, true)
            } else {
                Toast.makeText(this, "알림 권한이 없어 알림을 켤 수 없습니다.", Toast.LENGTH_SHORT).show()
                setSwitchCheckedSilently(switch, false)
                ReservationNotificationPreferences.setEnabled(this, key, false)
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_setting)
        PickDreamNotificationManager.createChannels(this)

        initializeViews()
        setupInitialState()
        setupListeners()

    }

    private fun initializeViews() {
        backButton = findViewById(R.id.backButton)
        switch1 = findViewById(R.id.switch1)
        switch2 = findViewById(R.id.switch2)
        switch3 = findViewById(R.id.switch3)
        checkKorean = findViewById(R.id.checkKorean)
        checkEnglish = findViewById(R.id.checkEnglish)
        checkJapanese = findViewById(R.id.checkJapanese)
        checkChinese = findViewById(R.id.checkChinese)
    }

    private fun setupListeners() {
        backButton.setOnClickListener {
            finish()
        }

        switch1.setOnCheckedChangeListener { _, isChecked ->
            handleNotificationSwitchChanged(
                switch1,
                ReservationNotificationPreferences.KEY_RESERVATION_COMPLETE,
                isChecked
            )
        }

        switch2.setOnCheckedChangeListener { _, isChecked ->
            handleNotificationSwitchChanged(
                switch2,
                ReservationNotificationPreferences.KEY_RESERVATION_CANCEL,
                isChecked
            )
        }

        switch3.setOnCheckedChangeListener { _, isChecked ->
            handleNotificationSwitchChanged(
                switch3,
                ReservationNotificationPreferences.KEY_RESERVATION_USAGE_TIME,
                isChecked
            )
        }

        findViewById<View>(R.id.langKorean).setOnClickListener {
            setLanguage("ko")
        }

        findViewById<View>(R.id.langEnglish).setOnClickListener {
            setLanguage("en")
        }

        findViewById<View>(R.id.langJapanese).setOnClickListener {
            setLanguage("ja")
        }

        findViewById<View>(R.id.langChinese).setOnClickListener {
            setLanguage("zh")
        }
    }

    private fun setupInitialState() {
        val hasNotificationPermission =
            ReservationNotificationPreferences.hasPostNotificationPermission(this)

        switch1.isChecked = getSwitchState(ReservationNotificationPreferences.KEY_RESERVATION_COMPLETE) &&
                hasNotificationPermission
        switch2.isChecked = getSwitchState(ReservationNotificationPreferences.KEY_RESERVATION_CANCEL) &&
                hasNotificationPermission
        switch3.isChecked = getSwitchState(ReservationNotificationPreferences.KEY_RESERVATION_USAGE_TIME) &&
                hasNotificationPermission

        if (!hasNotificationPermission) {
            saveSwitchState(ReservationNotificationPreferences.KEY_RESERVATION_COMPLETE, false)
            saveSwitchState(ReservationNotificationPreferences.KEY_RESERVATION_CANCEL, false)
            saveSwitchState(ReservationNotificationPreferences.KEY_RESERVATION_USAGE_TIME, false)
        }

        val currentLang = getCurrentLanguage()
        setLanguage(currentLang)
    }

    private fun handleNotificationSwitchChanged(
        switch: SwitchCompat,
        key: String,
        isChecked: Boolean
    ) {
        if (isUpdatingSwitchState) return

        if (isChecked && !ReservationNotificationPreferences.hasPostNotificationPermission(this)) {
            pendingNotificationSwitch = switch
            pendingNotificationKey = key
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            return
        }

        saveSwitchState(key, isChecked)
    }

    private fun setSwitchCheckedSilently(switch: SwitchCompat, isChecked: Boolean) {
        isUpdatingSwitchState = true
        switch.isChecked = isChecked
        isUpdatingSwitchState = false
    }

    private fun saveSwitchState(key: String, isChecked: Boolean) {
        getSharedPreferences("settings", MODE_PRIVATE)
            .edit()
            .putBoolean(key, isChecked)
            .apply()
    }

    private fun getSwitchState(key: String): Boolean {
        return getSharedPreferences("settings", MODE_PRIVATE)
            .getBoolean(key, false)
    }

    private fun setLanguage(langCode: String) {
        // 모든 체크 표시 숨기기
        checkKorean.visibility = View.GONE
        checkEnglish.visibility = View.GONE
        checkJapanese.visibility = View.GONE
        checkChinese.visibility = View.GONE

        // 선택된 언어 체크 표시
        when (langCode) {
            "ko" -> checkKorean.visibility = View.VISIBLE
            "en" -> checkEnglish.visibility = View.VISIBLE
            "ja" -> checkJapanese.visibility = View.VISIBLE
            "zh" -> checkChinese.visibility = View.VISIBLE
        }

        // 언어 설정 저장
        getSharedPreferences("settings", MODE_PRIVATE)
            .edit()
            .putString("language", langCode)
            .apply()
    }

    private fun getCurrentLanguage(): String {
        return getSharedPreferences("settings", MODE_PRIVATE)
            .getString("language", "ko") ?: "ko"
    }
}
