package com.example.pick_dream.ui.home.notice

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch

class NoticeViewModel : ViewModel() {

    private val _allNotices = MutableLiveData<List<Notice>>()
    private val _pagedNotices = MutableLiveData<List<Notice>>()
    val pagedNotices: LiveData<List<Notice>> get() = _pagedNotices

    private val _currentPage = MutableLiveData(1)
    val currentPage: LiveData<Int> get() = _currentPage

    private val _totalPages = MutableLiveData(1)
    val totalPages: LiveData<Int> get() = _totalPages

    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> get() = _isLoading

    private val pageSize = 8
    private var currentSearchQuery = ""
    private var currentFilteredList: List<Notice> = emptyList()

    init {
        loadNotices()
    }

    fun loadNotices() {
        _isLoading.value = true
        viewModelScope.launch {
            val notices = NoticeRepository.fetchAllNotices()
            _allNotices.value = notices
            currentFilteredList = notices
            updatePagination()
            _isLoading.value = false
        }
    }

    fun searchNotices(query: String) {
        currentSearchQuery = query.trim()
        val all = _allNotices.value ?: emptyList()
        
        currentFilteredList = if (currentSearchQuery.isNotEmpty()) {
            all.filter {
                it.title.contains(currentSearchQuery, ignoreCase = true) || 
                it.content.contains(currentSearchQuery, ignoreCase = true)
            }
        } else {
            all
        }
        
        _currentPage.value = 1
        updatePagination()
    }

    fun setPage(page: Int) {
        if (page in 1..(_totalPages.value ?: 1)) {
            _currentPage.value = page
            updatePagedList()
        }
    }

    fun nextPage() {
        val current = _currentPage.value ?: 1
        val total = _totalPages.value ?: 1
        if (current < total) {
            setPage(current + 1)
        }
    }

    fun prevPage() {
        val current = _currentPage.value ?: 1
        if (current > 1) {
            setPage(current - 1)
        }
    }

    private fun updatePagination() {
        val total = (currentFilteredList.size + pageSize - 1) / pageSize
        _totalPages.value = if (total == 0) 1 else total
        updatePagedList()
    }

    private fun updatePagedList() {
        val page = _currentPage.value ?: 1
        val fromIndex = (page - 1) * pageSize
        val toIndex = minOf(fromIndex + pageSize, currentFilteredList.size)
        
        if (fromIndex < toIndex) {
            _pagedNotices.value = currentFilteredList.subList(fromIndex, toIndex)
        } else {
            _pagedNotices.value = emptyList()
        }
    }
}