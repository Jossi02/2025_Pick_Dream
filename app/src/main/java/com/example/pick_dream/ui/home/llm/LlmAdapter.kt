package com.example.pick_dream.ui.home.llm

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.view.LayoutInflater
import android.view.ViewGroup
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import com.google.android.material.button.MaterialButton
import androidx.recyclerview.widget.RecyclerView
import com.example.pick_dream.databinding.ItemLlmMessageBinding
import com.example.pick_dream.R
import com.google.android.material.card.MaterialCardView

class LlmAdapter(
    private val messages: List<LlmMessage>,
    private val onQuickReplyClick: (String) -> Unit = {}
) :
    RecyclerView.Adapter<LlmAdapter.LlmViewHolder>() {

    inner class LlmViewHolder(val binding: ItemLlmMessageBinding) : RecyclerView.ViewHolder(binding.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): LlmViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        val binding = ItemLlmMessageBinding.inflate(inflater, parent, false)
        return LlmViewHolder(binding)
    }

    override fun onBindViewHolder(holder: LlmViewHolder, position: Int) {
        val message = messages[position]
        val context = holder.itemView.context

        holder.binding.reservationCardsContainer.removeAllViews()
        holder.binding.reservationCardsContainer.visibility = View.GONE
        holder.binding.quickActionsContainer.removeAllViews()
        holder.binding.quickActionsContainer.visibility = View.GONE
        holder.binding.textMessage.visibility = View.VISIBLE

        if (message.isUser) {
            holder.binding.textMessage.text = message.text
            holder.binding.layoutRoot.gravity = Gravity.END
            holder.binding.textMessage.setBackgroundResource(R.drawable.bg_rounded_16dp)
            holder.binding.textMessage.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#6391EE"))
            holder.binding.textMessage.setTextColor(context.getColor(android.R.color.white))
            holder.binding.imageBotIcon.visibility = android.view.View.GONE
        } else {
            holder.binding.layoutRoot.gravity = Gravity.START
            holder.binding.imageBotIcon.visibility = android.view.View.VISIBLE

            val reservations = parseReservationCards(message.text)
            if (reservations.isNotEmpty()) {
                holder.binding.textMessage.visibility = View.GONE
                holder.binding.reservationCardsContainer.visibility = View.VISIBLE
                val headerText = reservationHeaderText(message.text)
                addReservationHeader(context, holder.binding.reservationCardsContainer, headerText)
                reservations.forEach { reservation ->
                    holder.binding.reservationCardsContainer.addView(createReservationCard(context, reservation))
                }
            } else {
                holder.binding.textMessage.text = message.text
                holder.binding.textMessage.setBackgroundResource(R.drawable.bg_rounded_16dp)
                holder.binding.textMessage.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#F7F9FF"))
                holder.binding.textMessage.setTextColor(context.getColor(android.R.color.black))
            }

            val quickActions = if (reservations.any { !it.actionLabel.isNullOrBlank() }) {
                emptyList()
            } else {
                parseQuickActions(message.text)
            }
            if (quickActions.isNotEmpty()) {
                holder.binding.quickActionsContainer.visibility = View.VISIBLE
                quickActions.forEach { action ->
                    holder.binding.quickActionsContainer.addView(createQuickActionButton(context, action))
                }
            }
        }
    }

    override fun getItemCount() = messages.size

    private data class ReservationCard(
        val roomName: String,
        val startTime: String,
        val endTime: String,
        val participants: String?,
        val actionLabel: String? = null,
        val actionMessage: String? = null
    )

    private fun parseReservationCards(text: String): List<ReservationCard> {
        val isReservationList = text.startsWith("현재 예약 및 예정된 예약:")
        val isCancelSelection = text.startsWith("취소할 예약을 선택해 주세요:")
        if (!isReservationList && !isCancelSelection) {
            parseConfirmationCard(text)?.let { return listOf(it) }
            parseAlternativeRoomCard(text)?.let { return listOf(it) }
            return emptyList()
        }

        return text
            .lineSequence()
            .drop(1)
            .map { it.trim() }
            .filter { it.startsWith("- ") && ":" in it && "~" in it }
            .mapNotNull { line ->
                val content = line.removePrefix("- ").trim()
                val roomName = content.substringBefore(":").trim()
                val rest = content.substringAfter(":", "").trim()
                if (roomName.isBlank() || rest.isBlank()) return@mapNotNull null

                val timeAndPeople = rest.split(" / ", limit = 2)
                val timeRange = timeAndPeople[0].split(" ~ ", limit = 2)
                if (timeRange.size != 2) return@mapNotNull null

                ReservationCard(
                    roomName = roomName,
                    startTime = simplifyKoreanDateTime(timeRange[0]),
                    endTime = simplifyKoreanDateTime(timeRange[1]),
                    participants = timeAndPeople.getOrNull(1),
                    actionLabel = if (isCancelSelection) "이 예약 취소" else null,
                    actionMessage = if (isCancelSelection) {
                        "$roomName ${simplifyKoreanDateTime(timeRange[0])} 예약 취소해줘"
                    } else {
                        null
                    }
                )
            }
            .toList()
    }

    private fun reservationHeaderText(text: String): String {
        return when {
            text.startsWith("취소할 예약을 선택해 주세요:") -> "취소할 예약을 선택해 주세요"
            text.startsWith("예약 내용을 확인해 주세요") -> "예약 내용을 확인해 주세요"
            "대신" in text && "예약 가능" in text -> "대체 강의실 제안"
            else -> "현재 예약 및 예정된 예약"
        }
    }

    private fun parseConfirmationCard(text: String): ReservationCard? {
        if (!text.startsWith("예약 내용을 확인해 주세요")) return null

        val roomName = extractLineValue(text, "강의실") ?: return null
        val timeRange = extractLineValue(text, "시간") ?: return null
        val participants = extractLineValue(text, "인원")
        val times = splitTimeRange(timeRange) ?: return null

        return ReservationCard(
            roomName = roomName,
            startTime = simplifyKoreanDateTime(times.first),
            endTime = simplifyKoreanDateTime(times.second),
            participants = participants,
            actionLabel = "예약 확정",
            actionMessage = "예약확정"
        )
    }

    private fun parseAlternativeRoomCard(text: String): ReservationCard? {
        if (!("대신" in text && "예약 가능" in text)) return null

        val roomName = Regex("""대신\s+(.+?)은\s+같은\s+시간에\s+예약\s+가능""")
            .find(text)
            ?.groupValues
            ?.getOrNull(1)
            ?.trim()
            ?: return null
        val timeRange = extractLineValue(text, "시간") ?: return null
        val participants = extractLineValue(text, "인원")
        val times = splitTimeRange(timeRange) ?: return null

        return ReservationCard(
            roomName = roomName,
            startTime = simplifyKoreanDateTime(times.first),
            endTime = simplifyKoreanDateTime(times.second),
            participants = participants,
            actionLabel = "예약 확정",
            actionMessage = "예약확정"
        )
    }

    private fun extractLineValue(text: String, label: String): String? {
        return text
            .lineSequence()
            .map { it.trim() }
            .firstOrNull { it.startsWith("$label:") }
            ?.substringAfter(":")
            ?.trim()
            ?.takeIf { it.isNotBlank() }
    }

    private fun splitTimeRange(value: String): Pair<String, String>? {
        val parts = value.split(" ~ ", limit = 2)
        if (parts.size != 2) return null
        return parts[0].trim() to parts[1].trim()
    }

    private fun simplifyKoreanDateTime(value: String): String {
        return value
            .replace(" 0초 UTC+9", "")
            .replace(" UTC+9", "")
            .replace(" 0분", " 0분")
            .trim()
    }

    private fun addReservationHeader(context: Context, container: LinearLayout, title: String) {
        val header = TextView(context).apply {
            text = title
            setTextColor(Color.parseColor("#222222"))
            textSize = 16f
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            setPadding(dp(context, 4), 0, dp(context, 4), dp(context, 8))
        }
        container.addView(header)
    }

    private data class QuickAction(
        val label: String,
        val message: String
    )

    private fun parseQuickActions(text: String): List<QuickAction> {
        val actions = mutableListOf<QuickAction>()
        val normalized = text.replace(" ", "")

        val asksForConfirmation =
            ("예약확정" in normalized || "'예약확정'" in normalized) &&
                "예약되었습니다" !in normalized &&
                "변경되었습니다" !in normalized &&
                "취소되었습니다" !in normalized

        if (asksForConfirmation) {
            actions.add(QuickAction(label = "예약 확정", message = "예약확정"))
        }

        val suggestsAlternative =
            "다른강의실" in normalized &&
                ("말해주세요" in normalized || "입력해주세요" in normalized || "찾아드릴" in normalized) &&
                "예약확정" !in normalized

        if (suggestsAlternative) {
            actions.add(QuickAction(label = "다른 강의실 찾기", message = "기존 예약을 다른 강의실로 변경해줘"))
        }

        return actions
    }

    private fun createQuickActionButton(context: Context, action: QuickAction): View {
        return MaterialButton(context, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
            text = action.label
            textSize = 15f
            isAllCaps = false
            cornerRadius = dp(context, 10)
            strokeWidth = dp(context, 1)
            strokeColor = ColorStateList.valueOf(Color.parseColor("#5E8CFF"))
            setTextColor(Color.parseColor("#3F63C5"))
            backgroundTintList = ColorStateList.valueOf(Color.WHITE)
            minHeight = dp(context, 44)
            setPadding(dp(context, 12), 0, dp(context, 12), 0)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                bottomMargin = dp(context, 8)
            }
            setOnClickListener {
                onQuickReplyClick(action.message)
            }
        }
    }

    private fun createReservationCard(context: Context, reservation: ReservationCard): View {
        val card = MaterialCardView(context).apply {
            radius = dp(context, 12).toFloat()
            cardElevation = dp(context, 1).toFloat()
            setCardBackgroundColor(Color.parseColor("#F7F9FF"))
            strokeColor = Color.parseColor("#5E8CFF")
            strokeWidth = dp(context, 1)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                bottomMargin = dp(context, 10)
            }
        }

        val content = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 14), dp(context, 12), dp(context, 14), dp(context, 12))
        }

        val room = TextView(context).apply {
            text = reservation.roomName
            setTextColor(Color.parseColor("#222222"))
            textSize = 17f
            typeface = android.graphics.Typeface.DEFAULT_BOLD
        }

        val time = TextView(context).apply {
            text = "${reservation.startTime}\n~ ${reservation.endTime}"
            setTextColor(Color.parseColor("#444444"))
            textSize = 14f
            setPadding(0, dp(context, 6), 0, 0)
        }

        content.addView(room)
        content.addView(time)

        reservation.participants?.takeIf { it.isNotBlank() }?.let {
            val participants = TextView(context).apply {
                text = "인원: $it"
                setTextColor(Color.parseColor("#444444"))
                textSize = 14f
                setPadding(0, dp(context, 4), 0, 0)
            }
            content.addView(participants)
        }

        if (!reservation.actionLabel.isNullOrBlank() && !reservation.actionMessage.isNullOrBlank()) {
            content.addView(
                createQuickActionButton(
                    context,
                    QuickAction(
                        label = reservation.actionLabel,
                        message = reservation.actionMessage
                    )
                )
            )
        }

        card.addView(content)
        return card
    }

    private fun dp(context: Context, value: Int): Int {
        return (value * context.resources.displayMetrics.density).toInt()
    }
}
