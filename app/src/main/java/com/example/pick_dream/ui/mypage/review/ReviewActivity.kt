package com.example.pick_dream.ui.mypage.review

import android.os.Bundle
import android.widget.ImageButton
import android.widget.Toast
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.pick_dream.R

class ReviewActivity : AppCompatActivity() {
    private val viewModel: ReviewViewModel by viewModels()
    private lateinit var adapter: ReviewAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_review)

        val backButton = findViewById<ImageButton>(R.id.backButton)
        backButton.setOnClickListener {
            finish()
        }

        val recyclerView = findViewById<RecyclerView>(R.id.reviewRecyclerView)
        adapter = ReviewAdapter()
        recyclerView.layoutManager = LinearLayoutManager(this)
        recyclerView.adapter = adapter

        observeViewModel()
        
        // 화면 진입 시 리뷰 로드
        viewModel.loadReviews()
    }

    private fun observeViewModel() {
        viewModel.reviews.observe(this) { reviewList ->
            adapter.submitList(reviewList)
        }

        viewModel.message.observe(this) { msg ->
            if (msg.isNotBlank()) {
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
            }
        }
    }
}
