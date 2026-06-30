package com.example.pick_dream.ui.home.search.manualReservation

import android.content.Context
import android.graphics.drawable.ColorDrawable
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.PopupWindow
import android.widget.TextView
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.pick_dream.R

class NumberDropdownPopup(
    private val context: Context
) {
    fun show(anchor: View, values: List<Int>, selectedValue: Int?, onSelect: (Int) -> Unit) {
        if (values.isEmpty()) return

        val inflater = LayoutInflater.from(context)
        val popupView = inflater.inflate(R.layout.popup_month_dropdown, null)
        val recyclerView = popupView.findViewById<RecyclerView>(R.id.recyclerMonth)
        recyclerView.layoutManager = LinearLayoutManager(context)
        recyclerView.adapter = NumberAdapter(values, selectedValue ?: values.first()) { value ->
            onSelect(value)
            popupWindow?.dismiss()
        }

        val density = context.resources.displayMetrics.density
        val minWidth = (55 * density).toInt()
        val width = maxOf(anchor.width, minWidth)
        val yOffset = (8 * density).toInt()

        popupWindow = PopupWindow(popupView, width, ViewGroup.LayoutParams.WRAP_CONTENT, true).apply {
            setBackgroundDrawable(ColorDrawable(0x00000000))
            isOutsideTouchable = true
            isFocusable = true
            elevation = 16f
            showAsDropDown(anchor, 0, yOffset)
        }
    }

    private var popupWindow: PopupWindow? = null

    private class NumberAdapter(
        private val values: List<Int>,
        private val selectedValue: Int,
        private val onClick: (Int) -> Unit
    ) : RecyclerView.Adapter<NumberAdapter.NumberViewHolder>() {
        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): NumberViewHolder {
            val view = LayoutInflater.from(parent.context).inflate(R.layout.item_month_dropdown, parent, false)
            return NumberViewHolder(view)
        }

        override fun getItemCount(): Int = values.size

        override fun onBindViewHolder(holder: NumberViewHolder, position: Int) {
            holder.bind(values[position], values[position] == selectedValue, onClick)
        }

        private class NumberViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
            fun bind(value: Int, isSelected: Boolean, onClick: (Int) -> Unit) {
                val textView = itemView.findViewById<TextView>(R.id.tvMonth)
                textView.text = value.toString()
                textView.isSelected = isSelected
                textView.setTextColor(
                    if (isSelected) itemView.context.getColor(R.color.white)
                    else itemView.context.getColor(R.color.neutral_700)
                )
                itemView.setOnClickListener { onClick(value) }
            }
        }
    }
}
