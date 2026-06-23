package com.example.pick_dream.ui.home

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import com.example.pick_dream.R
import com.example.pick_dream.databinding.FragmentHomeBinding
import com.example.pick_dream.model.Reservation
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.firebase.firestore.FirebaseFirestore
import com.squareup.picasso.Picasso
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import com.example.pick_dream.ui.home.notice.NoticeRepository
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

class HomeFragment : Fragment() {

    private var _binding: FragmentHomeBinding? = null
    private val binding get() = _binding!!

    private val handler = Handler(Looper.getMainLooper())
    private var timerRunnable: Runnable? = null

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentHomeBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // 화면 로드 시 로딩 상태 표시
        binding.layoutReservationDetails.visibility = View.GONE
        binding.flReservationStatusVisual.visibility = View.GONE
        binding.layoutNoReservation.visibility = View.VISIBLE
        binding.tvNoReservationMessage.text = "예약 정보를 불러오는 중입니다..."

        setupClickListeners()
    }

    private fun setupClickListeners() {
        listOf(binding.btnLlm, binding.btnSearch, binding.btnInquiry, binding.btnMap).forEach { button ->
            button.setOnClickListener { onButtonClick(it) }
        }
        binding.btnNotice.setOnClickListener {
            findNavController().navigate(R.id.action_homeFragment_to_noticeFragment)
        }
        binding.cardReservationInfo.setOnClickListener {
            findNavController().navigate(R.id.action_homeFragment_to_reservationFragment)
        }
    }

    private fun onButtonClick(view: View) {
        val originalColor = ContextCompat.getColor(requireContext(), R.color.white)
        val clickedColor = ContextCompat.getColor(requireContext(), R.color.button_clicked)

        view.setBackgroundColor(clickedColor)
        Handler(Looper.getMainLooper()).postDelayed({ view.setBackgroundColor(originalColor) }, 200)

        when (view.id) {
            R.id.btn_llm -> findNavController().navigate(R.id.action_homeFragment_to_llmFragment)
            R.id.btn_search -> findNavController().navigate(R.id.action_homeFragment_to_lectureRoomListFragment)
            R.id.btn_inquiry -> findNavController().navigate(R.id.action_homeFragment_to_reservationFragment)
            R.id.btn_map -> findNavController().navigate(R.id.action_homeFragment_to_mapsFragment)
        }
    }

    override fun onResume() {
        super.onResume()
        val navView = requireActivity().findViewById<BottomNavigationView>(R.id.nav_view)
        navView?.visibility = View.VISIBLE
        if (navView?.selectedItemId != R.id.navigation_home) {
            navView?.selectedItemId = R.id.navigation_home
        }
        loadMyReservation()
        loadLatestNotice()
    }

    private fun loadLatestNotice() {
        viewLifecycleOwner.lifecycleScope.launch {
            val notice = NoticeRepository.fetchLatestNotice()
            if (_binding == null || !isAdded) return@launch
            
            if (notice != null) {
                binding.tvNoticeLatest.text = notice.title
                binding.layoutNoticeBar.setOnClickListener {
                    val action = HomeFragmentDirections.actionHomeFragmentToNoticeDetailFragment(
                        title = notice.title,
                        date = notice.date,
                        content = notice.content
                    )
                    findNavController().navigate(action)
                }
            } else {
                binding.tvNoticeLatest.text = "등록된 공지사항이 없습니다."
                binding.layoutNoticeBar.setOnClickListener(null)
            }
        }
    }

    /**
     * HomeRepository�� ���� ���� ������ ������ UI�� ������Ʈ�մϴ�.
     * DB ��� ������ HomeRepository�� �����մϴ�.
     */
    private fun loadMyReservation() {
        handler.removeCallbacksAndMessages(null)
        HomeRepository.fetchActiveOrUpcomingReservation { reservation ->
            if (_binding == null || !isAdded) return@fetchActiveOrUpcomingReservation
            updateReservationCard(reservation)
        }
    }

    private fun updateReservationCard(reservation: Reservation?) {
        if (_binding == null || !isAdded) return

        if (reservation == null) {
            binding.layoutNoReservation.visibility = View.VISIBLE
            binding.tvNoReservationMessage.text = "현재 진행 중인 예약이 없습니다.\n"
            binding.layoutReservationDetails.visibility = View.GONE
            binding.flReservationStatusVisual.visibility = View.GONE
            return
        }

        binding.layoutNoReservation.visibility = View.GONE
        binding.layoutReservationDetails.visibility = View.VISIBLE
        binding.flReservationStatusVisual.visibility = View.VISIBLE

        // ���ǽ� �̹��� �� �̸� �ε�
        val roomIdOnly = reservation.roomID.replace(Regex("[^0-9]"), "")
        FirebaseFirestore.getInstance().collection("rooms").document(roomIdOnly).get()
            .addOnSuccessListener { roomDoc ->
                if (_binding == null || !isAdded) return@addOnSuccessListener
                if (roomDoc.exists()) {
                    binding.tvReservationRoom.text = "���� ��� : "
                    val imageUrl = roomDoc.getString("image")
                    if (!imageUrl.isNullOrEmpty()) {
                        Picasso.get().load(imageUrl).into(binding.ivRoomBackground)
                    } else {
                        binding.ivRoomBackground.setImageResource(R.drawable.sample_room)
                    }
                } else {
                    binding.tvReservationRoom.text = "���� ��� : "
                    binding.ivRoomBackground.setImageResource(R.drawable.sample_room)
                }
            }

        val startCal = reservation.startTime?.let { parseKoreanDateToCalendar(it) }
        val endCal = reservation.endTime?.let { parseKoreanDateToCalendar(it) }

        if (startCal != null && endCal != null) {
            binding.tvReservationTime.text = "�뿩 �ð� :  - "

            // ���� ���� ���� SharedPreferences�� ���� (Repository�� ����)
            HomeRepository.saveReservationPrefs(requireContext(), endCal.timeInMillis, reservation.roomID)

            startCountdownTimer(startCal, endCal)
        }
    }

    /**
     * ���� ���� �ð� ī��Ʈ�ٿ� Ÿ�̸Ӹ� �����մϴ�.
     */
    private fun startCountdownTimer(startCal: Calendar, endCal: Calendar) {
        timerRunnable = object : Runnable {
            override fun run() {
                val now = Calendar.getInstance()
                val isActive = !now.before(startCal)

                if (isActive) {
                    val remainingMillis = endCal.timeInMillis - now.timeInMillis
                    if (remainingMillis > 0) {
                        val totalDuration = endCal.timeInMillis - startCal.timeInMillis
                        val progress = ((now.timeInMillis - startCal.timeInMillis) * 100 / totalDuration)
                            .toInt().coerceIn(0, 100)

                        binding.pbReservationProgress.progress = progress
                        binding.tvProgressPercentage.text = "%"

                        val hours = TimeUnit.MILLISECONDS.toHours(remainingMillis)
                        val minutes = TimeUnit.MILLISECONDS.toMinutes(remainingMillis) % 60
                        binding.tvRemainingTime.text = if (hours > 0) {
                            String.format("%d�ð� %d�� �� ����", hours, minutes)
                        } else {
                            String.format("%d�� �� ����", minutes)
                        }
                        handler.postDelayed(this, 30_000L) // 30�ʸ��� ������Ʈ
                    } else {
                        loadMyReservation()
                    }
                } else { // ���� ��� ��
                    val remainingMillis = startCal.timeInMillis - now.timeInMillis
                    if (remainingMillis > 0) {
                        val hours = TimeUnit.MILLISECONDS.toHours(remainingMillis)
                        val minutes = TimeUnit.MILLISECONDS.toMinutes(remainingMillis) % 60
                        binding.pbReservationProgress.progress = 0
                        binding.tvProgressPercentage.text = "������"
                        binding.tvRemainingTime.text = String.format("%d�ð� %d�� �� ����", hours, minutes)
                        handler.postDelayed(this, 60_000L) // 1�и��� ������Ʈ
                    } else {
                        loadMyReservation()
                    }
                }
            }
        }
        handler.post(timerRunnable!!)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacksAndMessages(null)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        handler.removeCallbacksAndMessages(null)
        _binding = null
    }
}

// --- ��¥ �Ľ� ��ƿ �Լ� ---

/**
 * Firestore�� ����� �ѱ��� ��¥ ���ڿ��� Calendar ��ü�� ��ȯ�մϴ�.
 * ��(second) ���� ���İ� ������ ���� ��� �����մϴ�.
 */
fun parseKoreanDateToCalendar(dateStr: String): Calendar? {
    val formats = listOf(
        SimpleDateFormat("yyyy�� M�� d�� a h�� m�� s�� 'UTC+9'", Locale.KOREAN),
        SimpleDateFormat("yyyy�� M�� d�� a h�� m��", Locale.KOREAN)
    )
    for (format in formats) {
        try {
            return Calendar.getInstance().apply { time = format.parse(dateStr)!! }
        } catch (e: Exception) {
            continue
        }
    }
    return null
}

fun formatKoreanTime(calendar: Calendar): String {
    return SimpleDateFormat("a h:mm", Locale.KOREAN).format(calendar.time)
}
