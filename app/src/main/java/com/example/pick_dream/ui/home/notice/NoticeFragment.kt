package com.example.pick_dream.ui.home.notice

import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.pick_dream.databinding.FragmentNoticeBinding

class NoticeFragment : Fragment() {

    private var _binding: FragmentNoticeBinding? = null
    private val binding get() = _binding!!

    private lateinit var adapter: NoticeAdapter
    private val viewModel: NoticeViewModel by viewModels()

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentNoticeBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        setupRecyclerView()
        setupListeners()
        observeViewModel()
    }

    private fun setupRecyclerView() {
        adapter = NoticeAdapter { notice ->
            val action = NoticeFragmentDirections.actionNoticeFragmentToNoticeDetailFragment(
                title = notice.title,
                date = notice.date,
                content = notice.content
            )
            findNavController().navigate(action)
        }
        binding.rvNotice.layoutManager = LinearLayoutManager(requireContext())
        binding.rvNotice.adapter = adapter
    }

    private fun setupListeners() {
        binding.btnBack.setOnClickListener {
            findNavController().popBackStack()
        }

        binding.btnSearch.setOnClickListener {
            performSearch()
        }

        binding.etSearch.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                performSearch()
                return@setOnEditorActionListener true
            }
            false
        }

        binding.tvPrev.setOnClickListener {
            viewModel.prevPage()
        }

        binding.tvNext.setOnClickListener {
            viewModel.nextPage()
        }
    }

    private fun performSearch() {
        val query = binding.etSearch.text.toString()
        viewModel.searchNotices(query)
    }

    private fun observeViewModel() {
        viewModel.pagedNotices.observe(viewLifecycleOwner) { notices ->
            adapter.submitList(notices)
        }

        viewModel.currentPage.observe(viewLifecycleOwner) {
            setupPagination() // 페이지나 총 페이지 수가 변경될 때마다 UI 업데이트
        }

        viewModel.totalPages.observe(viewLifecycleOwner) {
            setupPagination()
        }
    }

    private fun setupPagination() {
        val pagesContainer = binding.pagesContainer
        pagesContainer.removeAllViews()

        val currentPage = viewModel.currentPage.value ?: 1
        val totalPages = viewModel.totalPages.value ?: 1

        for (i in 1..totalPages) {
            val pageButton = createPageButton(i.toString(), i == currentPage) {
                viewModel.setPage(i)
            }
            pagesContainer.addView(pageButton)
        }
    }

    private fun createPageButton(text: String, isSelected: Boolean = false, onClick: () -> Unit): View {
        val tv = TextView(requireContext())
        tv.text = text
        tv.textSize = 16f
        tv.setPadding(8, 0, 8, 0)
        tv.setTextColor(if (isSelected) Color.parseColor("#3C5ABD") else Color.parseColor("#888888"))
        tv.setTypeface(null, if (isSelected) Typeface.BOLD else Typeface.NORMAL)
        tv.setOnClickListener { onClick() }
        tv.isClickable = true
        tv.isFocusable = true
        return tv
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
