package com.example.pick_dream.ui.mypage

import android.content.Intent
import android.graphics.Paint
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import com.example.pick_dream.databinding.FragmentMypageBinding
import com.example.pick_dream.ui.login.LoginActivity
import com.example.pick_dream.ui.mypage.inquiry.InquiryActivity
import com.example.pick_dream.ui.mypage.review.ReviewActivity
import com.example.pick_dream.ui.mypage.setting.SettingActivity
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.example.pick_dream.R

class MypageFragment : Fragment() {

    private var _binding: FragmentMypageBinding? = null
    private val binding get() = _binding!!
    private val viewModel: MyPageViewModel by viewModels()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentMypageBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        setupClickListeners()
        observeViewModel()
        viewModel.loadUserData()
    }

    private fun observeViewModel() {
        viewModel.userData.observe(viewLifecycleOwner) { user ->
            if (user == null) return@observe
            binding.userName.text = user.name
            binding.userEmail.text = user.email
            binding.userMajor.text = user.major
            binding.userId.text = user.studentId
        }
    }

    private fun setupClickListeners() {
        binding.logoutTextView.paintFlags =
            binding.logoutTextView.paintFlags or Paint.UNDERLINE_TEXT_FLAG

        binding.logoutTextView.setOnClickListener {
            val intent = Intent(requireContext(), LoginActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
            startActivity(intent)
            requireActivity().finish()
        }

        binding.reviewButtonCard.setOnClickListener {
            startActivity(Intent(requireContext(), ReviewActivity::class.java))
        }

        binding.inquiryButtonCard.setOnClickListener {
            startActivity(Intent(requireContext(), InquiryActivity::class.java))
        }

        binding.settingButtonCard.setOnClickListener {
            startActivity(Intent(requireContext(), SettingActivity::class.java))
        }
    }

    override fun onResume() {
        super.onResume()
        val navView = requireActivity().findViewById<BottomNavigationView>(R.id.nav_view)
        navView?.visibility = View.VISIBLE
        if (navView?.selectedItemId != R.id.navigation_mypage) {
            navView?.selectedItemId = R.id.navigation_mypage
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
