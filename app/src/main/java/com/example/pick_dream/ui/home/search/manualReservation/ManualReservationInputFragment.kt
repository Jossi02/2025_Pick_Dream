package com.example.pick_dream.ui.home.search.manualReservation

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.navigation.NavOptions
import androidx.navigation.fragment.findNavController
import com.example.pick_dream.R
import com.example.pick_dream.model.Reservation
import com.google.android.material.button.MaterialButton
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore

class ManualReservationInputFragment : Fragment() {
    private val reservationViewModel: ManualReservationViewModel by activityViewModels()
    private val auth = FirebaseAuth.getInstance()
    private val db = FirebaseFirestore.getInstance()

    private lateinit var btnReserve: MaterialButton
    private lateinit var etEventName: EditText
    private lateinit var etEventDetail: EditText
    private lateinit var etEventTarget: EditText
    private lateinit var etEventPeople: EditText

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        return inflater.inflate(R.layout.fragment_manual_reservation_input, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val btnBack = view.findViewById<View>(R.id.btnBack)
        btnReserve = view.findViewById(R.id.btnReserve)
        etEventName = view.findViewById(R.id.etEventName)
        etEventDetail = view.findViewById(R.id.etEventDetail)
        etEventTarget = view.findViewById(R.id.etEventTarget)
        etEventPeople = view.findViewById(R.id.etEventPeople)
        val tvBuildingInfo = view.findViewById<TextView>(R.id.tvBuildingInfo)
        val tvRoomName = view.findViewById<TextView>(R.id.tvRoomName)

        setupWatchers()
        observeViewModel()

        btnBack.setOnClickListener {
            findNavController().popBackStack()
        }

        btnReserve.setOnClickListener {
            handleReservation()
        }

        arguments?.let { args ->
            tvBuildingInfo.text = args.getString("building") ?: ""
            tvRoomName.text = args.getString("roomName") ?: ""
        }
    }

    private fun setupWatchers() {
        val watcher = object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                updateButtonState()
            }
            override fun afterTextChanged(s: Editable?) {}
        }
        etEventName.addTextChangedListener(watcher)
        etEventDetail.addTextChangedListener(watcher)
        etEventTarget.addTextChangedListener(watcher)
        etEventPeople.addTextChangedListener(watcher)
        updateButtonState()
    }

    private fun updateButtonState() {
        val isFilled = etEventName.text.isNotBlank() &&
                etEventDetail.text.isNotBlank() &&
                etEventTarget.text.isNotBlank() &&
                etEventPeople.text.isNotBlank()

        btnReserve.isEnabled = isFilled
        if (isFilled) {
            btnReserve.setBackgroundColor(resources.getColor(R.color.primary_400, null))
            btnReserve.setTextColor(resources.getColor(android.R.color.white, null))
        } else {
            btnReserve.setBackgroundColor(resources.getColor(R.color.primary_050, null))
            btnReserve.setTextColor(resources.getColor(R.color.primary_400, null))
        }
    }

    private fun observeViewModel() {
        reservationViewModel.submitResult.observe(viewLifecycleOwner) { isSuccess ->
            if (isSuccess == null) return@observe

            if (isSuccess) {
                showSuccessDialog()
            } else {
                Toast.makeText(context, "예약 중 오류가 발생했습니다.", Toast.LENGTH_SHORT).show()
            }
            reservationViewModel.clearSubmitResult()
        }

        reservationViewModel.isSubmitting.observe(viewLifecycleOwner) { isSubmitting ->
            btnReserve.isEnabled = !isSubmitting
            btnReserve.text = if (isSubmitting) "예약 중..." else "대여하기"
        }
    }

    private fun handleReservation() {
        val eventName = etEventName.text.toString()
        val eventDescription = etEventDetail.text.toString()
        val eventParticipants = etEventPeople.text.toString().toIntOrNull() ?: 0
        val eventTarget = etEventTarget.text.toString()

        if (eventName.isBlank() || eventDescription.isBlank() || eventParticipants <= 0 || eventTarget.isBlank()) {
            Toast.makeText(context, "행사명, 목적, 인원수, 참여대상을 모두 입력해주세요.", Toast.LENGTH_SHORT).show()
            return
        }

        val currentUser = auth.currentUser
        if (currentUser == null) {
            Toast.makeText(context, "로그인이 필요합니다.", Toast.LENGTH_SHORT).show()
            return
        }

        // 학번은 User 컬렉션에서 가져와야 함 (이 부분은 사용자 정보라 여기서 조회 유지, 
        // 혹은 UserViewModel 도입 시 개선 가능하지만 일단 Firestore 직접 접근으로 유지하거나 개선)
        db.collection("User").document(currentUser.uid).get()
            .addOnSuccessListener { document ->
                val studentId = document.getString("studentId") ?: document.getString("userID") ?: ""
                if (studentId.isBlank()) {
                    Toast.makeText(context, "학번 정보를 찾을 수 없습니다.", Toast.LENGTH_SHORT).show()
                    return@addOnSuccessListener
                }

                arguments?.let { args ->
                    val roomId = args.getString("roomId") ?: ""
                    val startTimeStr = toKorean12HourString(
                        args.getInt("selectedYear"),
                        args.getInt("selectedMonth") + 1,
                        args.getInt("selectedDay"),
                        args.getInt("startHour"),
                        args.getInt("startMinute")
                    )
                    val endTimeStr = toKorean12HourString(
                        args.getInt("selectedYear"),
                        args.getInt("selectedMonth") + 1,
                        args.getInt("selectedDay"),
                        args.getInt("endHour"),
                        args.getInt("endMinute")
                    )
                    
                    val reservation = Reservation(
                        userID = studentId,
                        roomID = roomId,
                        eventName = eventName,
                        eventDescription = eventDescription,
                        eventTarget = eventTarget,
                        eventParticipants = eventParticipants,
                        startTime = startTimeStr,
                        endTime = endTimeStr,
                        status = "대기"
                    )
                    
                    reservationViewModel.makeReservation(reservation)
                }
            }
            .addOnFailureListener {
                Toast.makeText(context, "사용자 정보를 불러올 수 없습니다.", Toast.LENGTH_SHORT).show()
            }
    }

    private fun showSuccessDialog() {
        val dialogView = layoutInflater.inflate(R.layout.dialog_result, null)
        dialogView.findViewById<TextView>(R.id.tvDialogMessage).text = "대여가 완료되었습니다."
        val dialog = androidx.appcompat.app.AlertDialog.Builder(requireContext(), R.style.CustomDialog)
            .setView(dialogView)
            .setCancelable(false)
            .create()
            
        val background = android.graphics.drawable.GradientDrawable()
        background.setColor(android.graphics.Color.WHITE)
        val radius = resources.displayMetrics.density * 16
        background.cornerRadius = radius
        dialog.setOnShowListener {
            dialog.window?.setBackgroundDrawable(background)
        }
        
        dialogView.findViewById<TextView>(R.id.btnDialogOk).setOnClickListener {
            dialog.dismiss()
            findNavController().navigate(
                R.id.homeFragment,
                null,
                NavOptions.Builder()
                    .setPopUpTo(R.id.homeFragment, true)
                    .build()
            )
        }
        dialog.show()
    }

    override fun onResume() {
        super.onResume()
        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.GONE
    }

    override fun onPause() {
        super.onPause()
        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.VISIBLE
    }

    private fun toKorean12HourString(year: Int, month: Int, day: Int, hour24: Int, minute: Int): String {
        val ampm = if (hour24 < 12) "오전" else "오후"
        val hour12 = when {
            hour24 == 0 -> 12
            hour24 > 12 -> hour24 - 12
            else -> hour24
        }
        return String.format("%d년 %d월 %d일 %s %d시 %d분 0초 UTC+9", year, month, day, ampm, hour12, minute)
    }
}
