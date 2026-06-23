package com.example.pick_dream.ui.reviewpage

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.CheckBox
import android.widget.ImageView
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.navigation.fragment.navArgs
import com.example.pick_dream.R
import com.example.pick_dream.databinding.FragmentReviewBinding
import com.example.pick_dream.model.Review
import com.example.pick_dream.ui.mypage.review.ReviewRepository
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

class ReviewFragment : Fragment() {

    private var _binding: FragmentReviewBinding? = null
    private val binding get() = _binding!!

    private val args: ReviewFragmentArgs by navArgs()

    private val starIds = listOf(R.id.star1, R.id.star2, R.id.star3, R.id.star4, R.id.star5)
    private var selectedStars = 0

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentReviewBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.GONE

        binding.tvGuideText.text = " 이용 후기를 남겨주세요!"

        setupStarRating()
        setupCheckBoxStyle(binding.layoutPurpose)
        setupCheckBoxStyle(binding.layoutEquip)

        binding.btnSubmit.setOnClickListener { submitReview() }
        binding.btnClose.setOnClickListener { findNavController().popBackStack() }
    }

    private fun setupStarRating() {
        val starViews = starIds.map { binding.root.findViewById<ImageView>(it) }
        starViews.forEachIndexed { index, imageView ->
            imageView.setOnClickListener {
                selectedStars = index + 1
                updateStars(starViews, selectedStars)
            }
        }
        updateStars(starViews, selectedStars)
    }

    private fun setupCheckBoxStyle(layout: ViewGroup) {
        for (i in 0 until layout.childCount) {
            val child = layout.getChildAt(i)
            if (child is CheckBox) {
                child.buttonDrawable =
                    ContextCompat.getDrawable(requireContext(), R.drawable.checkbox_selector)
            }
        }
    }

    private fun getCheckedTexts(layout: ViewGroup): List<String> {
        return (0 until layout.childCount)
            .mapNotNull { layout.getChildAt(it) as? CheckBox }
            .filter { it.isChecked }
            .map { it.text.toString().trim() }
    }

    private fun submitReview() {
        binding.btnSubmit.isEnabled = false // 중복 제출 방지

        val currentUser = FirebaseAuth.getInstance().currentUser
        if (currentUser == null) {
            Toast.makeText(context, "로그인이 필요합니다.", Toast.LENGTH_SHORT).show()
            binding.btnSubmit.isEnabled = true
            return
        }

        lifecycleScope.launch {
            try {
                // 학번은 User 컬렉션에서 조회
                val userDoc = FirebaseFirestore.getInstance()
                    .collection("User").document(currentUser.uid).get().await()

                val studentId = userDoc.getString("studentId") ?: userDoc.getString("userID")
                if (studentId.isNullOrBlank()) {
                    Toast.makeText(context, "사용자 정보를 찾을 수 없습니다.", Toast.LENGTH_SHORT).show()
                    binding.btnSubmit.isEnabled = true
                    return@launch
                }

                val review = Review(
                    userID = studentId,
                    roomID = args.roomId,
                    rating = selectedStars.toFloat(),
                    comment = binding.etComment.text.toString(),
                    purpose = getCheckedTexts(binding.layoutPurpose),
                    equipment = getCheckedTexts(binding.layoutEquip)
                )

                // 리뷰 추가를 Repository 로 위임
                val success = ReviewRepository.addReview(review)
                if (success) {
                    Log.d("ReviewFragment", "Review successfully submitted")
                    findNavController().navigate(R.id.action_reviewFragment_to_reviewCompleteFragment)
                } else {
                    Toast.makeText(context, "리뷰 제출에 실패했습니다.", Toast.LENGTH_SHORT).show()
                    binding.btnSubmit.isEnabled = true
                }
            } catch (e: Exception) {
                Log.e("ReviewFragment", "Failed to fetch user info or submit review", e)
                Toast.makeText(context, "오류가 발생했습니다.", Toast.LENGTH_SHORT).show()
                binding.btnSubmit.isEnabled = true
            }
        }
    }

    private fun updateStars(starViews: List<ImageView>, selectedCount: Int) {
        starViews.forEachIndexed { index, imageView ->
            imageView.setImageResource(
                if (index < selectedCount) R.drawable.ic_star_color else R.drawable.ic_star_empty
            )
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.VISIBLE
        _binding = null
    }
}
