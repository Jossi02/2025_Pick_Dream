package com.example.pick_dream.ui.home.search

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.navigation.fragment.findNavController
import androidx.navigation.fragment.navArgs
import com.example.pick_dream.R
import com.example.pick_dream.databinding.FragmentLectureRoomDetailBinding
import com.google.android.material.button.MaterialButton
import com.google.android.material.bottomnavigation.BottomNavigationView

class LectureRoomDetailFragment : Fragment() {
    private val viewModel: LectureRoomDetailViewModel by viewModels()
    private var _binding: FragmentLectureRoomDetailBinding? = null
    private val binding get() = _binding!!
    private val args: LectureRoomDetailFragmentArgs by navArgs()

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentLectureRoomDetailBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.GONE

        viewModel.loadRoomDetail(args.roomName)

        viewModel.roomDetail.observe(viewLifecycleOwner) { room ->
            if (room == null) return@observe

            binding.tvRoomName.text = room.name
            val floorNumber = room.name.take(2).toIntOrNull()?.let { "${it / 10}층" } ?: "층수 정보 없음"
            binding.tvRoomDesc.text = buildString {
                append("${room.buildingName} $floorNumber\n")
                append("수용 인원: 최대 ${room.capacity}명\n")
                append("기자재: ${room.equipment.joinToString(", ")}")
            }

            // 상세 정보 박스 채우기
            binding.infoBoxRoomName.text = "강의실 : ${room.name}"
            binding.infoBoxEquipment.text = "기자재 목록 : ${room.equipment.joinToString(", ")}"
            // TODO: 의자 종류, 빔 프로젝터, 전자칠판 여부는 Firestore 데이터 필드 추가 후 연동 필요
            binding.infoBoxChairType.text = "의자 : 정보 없음"
            binding.infoBoxProjector.text = "빔 프로젝터 대여 여부 : 정보 없음"
            binding.infoBoxBlackboard.text = "전자 칠판 대여 여부 : 정보 없음"
            binding.infoBoxRentalAvailability.text =
                if (room.isRentalAvailable) "앱에서 바로 예약 가능" else "예약 불가"

            // 대여 가능 여부에 따라 버튼 상태 변경
            val bgColor: Int
            val textColor: Int
            if (room.isRentalAvailable) {
                bgColor = ContextCompat.getColor(requireContext(), R.color.primary_400)
                textColor = ContextCompat.getColor(requireContext(), android.R.color.white)
            } else {
                bgColor = ContextCompat.getColor(requireContext(), R.color.neutral_200)
                textColor = ContextCompat.getColor(requireContext(), R.color.neutral_400)
            }
            binding.btnReserve.isEnabled = room.isRentalAvailable
            binding.btnReserve.setBackgroundColor(bgColor)
            binding.btnReserve.setTextColor(textColor)

            val updateFavoriteUi = { isFav: Boolean ->
                if (isFav) {
                    binding.btnFavorite.setImageResource(R.drawable.ic_heart_filled)
                    binding.btnFavorite.setColorFilter(ContextCompat.getColor(requireContext(), R.color.Red))
                } else {
                    binding.btnFavorite.setImageResource(R.drawable.ic_heart_border)
                    binding.btnFavorite.clearColorFilter()
                }
            }

            updateFavoriteUi(room.isFavorite)
            binding.btnFavorite.setOnClickListener {
                LectureRoomRepository.toggleFavorite(room.id)
                room.isFavorite = !room.isFavorite
                updateFavoriteUi(room.isFavorite)
            }
        }

        binding.btnBack.setOnClickListener {
            findNavController().popBackStack()
        }

        binding.btnReserve.setOnClickListener {
            val room = viewModel.roomDetail.value
            if (room != null) {
                val action = LectureRoomDetailFragmentDirections.actionLectureRoomDetailFragmentToManualReservationFragment(
                    building = room.displayBuildingName,
                    roomName = room.name
                )
                findNavController().navigate(action)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.GONE
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}