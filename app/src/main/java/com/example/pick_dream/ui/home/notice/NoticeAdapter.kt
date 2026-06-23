package com.example.pick_dream.ui.home.notice

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.example.pick_dream.databinding.ItemNoticeBinding
import com.example.pick_dream.model.Notice

class NoticeAdapter(
    private val onClick: (Notice) -> Unit
) : ListAdapter<Notice, NoticeAdapter.NoticeViewHolder>(NoticeDiffCallback()) {

    inner class NoticeViewHolder(val binding: ItemNoticeBinding) : RecyclerView.ViewHolder(binding.root) {
        fun bind(notice: Notice) {
            binding.tvIcon.text = notice.iconEmoji
            binding.tvTitle.text = notice.title
            binding.tvDate.text = notice.date
            binding.root.setOnClickListener { onClick(notice) }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): NoticeViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        val binding = ItemNoticeBinding.inflate(inflater, parent, false)
        return NoticeViewHolder(binding)
    }

    override fun onBindViewHolder(holder: NoticeViewHolder, position: Int) {
        holder.bind(getItem(position))
    }
}

class NoticeDiffCallback : DiffUtil.ItemCallback<Notice>() {
    override fun areItemsTheSame(oldItem: Notice, newItem: Notice): Boolean {
        return oldItem.id == newItem.id
    }

    override fun areContentsTheSame(oldItem: Notice, newItem: Notice): Boolean {
        return oldItem == newItem
    }
}