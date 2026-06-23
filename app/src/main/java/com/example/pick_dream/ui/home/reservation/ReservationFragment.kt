package com.example.pick_dream.ui.home.reservation

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.os.bundleOf
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.pick_dream.R
import com.example.pick_dream.databinding.FragmentReservationBinding
import com.example.pick_dream.model.Reservation

sealed class ReservationListItem {
    data class Header(val title: String) : ReservationListItem()
    data class ReservationItem(val reservation: Reservation, val imageUrl: String?) : ReservationListItem()
}

class ReservationFragment : Fragment() {
    private var _binding: FragmentReservationBinding? = null
    private val binding get() = _binding!!

    private lateinit var adapter: ReservationAdapter
    private val viewModel: ReservationViewModel by viewModels()

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentReservationBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        
        setupRecyclerView()
        setupListeners()
        observeViewModel()

        // 화면 진입 시 예약 목록 불러오기
        viewModel.loadReservations()
    }

    private fun setupRecyclerView() {
        adapter = ReservationAdapter(
            onCancelClick = { reservation -> confirmCancellation(reservation) },
            onDetailClick = { reservation -> showReservationDetails(reservation) },
            onWriteReviewClick = { reservation -> navigateToWriteReview(reservation) }
        )
        binding.rvReservations.layoutManager = LinearLayoutManager(context)
        binding.rvReservations.adapter = adapter
    }

    private fun setupListeners() {
        binding.btnBack.setOnClickListener {
            findNavController().popBackStack()
        }
    }

    private fun observeViewModel() {
        viewModel.listItems.observe(viewLifecycleOwner) { items ->
            adapter.submitList(items)
            if (items.isEmpty()) {
                binding.tvEmptyState.visibility = View.VISIBLE
                binding.rvReservations.visibility = View.GONE
            } else {
                binding.tvEmptyState.visibility = View.GONE
                binding.rvReservations.visibility = View.VISIBLE
            }
        }

        viewModel.isLoading.observe(viewLifecycleOwner) { isLoading ->
            binding.progressBar.visibility = if (isLoading) View.VISIBLE else View.GONE
        }

        viewModel.message.observe(viewLifecycleOwner) { msg ->
            if (msg.isNotBlank()) {
                Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun confirmCancellation(reservation: Reservation) {
        AlertDialog.Builder(requireContext())
            .setTitle("예약 취소")
            .setMessage(" 예약을 정말로 취소하시겠습니까?")
            .setPositiveButton("확인") { _, _ ->
                viewModel.cancelReservation(reservation)
            }
            .setNegativeButton("취소", null)
            .show()
    }

    private fun showReservationDetails(reservation: Reservation) {
        // 상세 정보 보기 로직 (예: BottomSheetDialogFragment)
    }
    
    private fun navigateToWriteReview(reservation: Reservation){
        val roomId = reservation.roomID
        if (roomId.isBlank()) {
            Toast.makeText(context, "강의실 정보가 없어 후기를 작성할 수 없습니다.", Toast.LENGTH_SHORT).show()
            return
        }
        val bundle = bundleOf("roomId" to roomId)
        findNavController().navigate(R.id.action_reservationFragment_to_reviewFragment, bundle)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
