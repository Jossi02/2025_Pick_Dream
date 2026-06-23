package com.example.pick_dream.ui.favorite

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.pick_dream.R
import com.example.pick_dream.databinding.FragmentFavoriteBinding
import com.example.pick_dream.ui.home.search.LectureRoomRepository
import com.example.pick_dream.ui.home.search.ListItem
import com.google.android.material.bottomnavigation.BottomNavigationView

class FavoriteFragment : Fragment() {

    private var _binding: FragmentFavoriteBinding? = null
    private val binding get() = _binding!!

    private lateinit var adapter: FavoriteRoomsAdapter

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentFavoriteBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        setupRecyclerView()
        observeFavoriteRooms()
    }

    private fun setupRecyclerView() {
        adapter = FavoriteRoomsAdapter(
            rooms = emptyList(),
            onFavoriteClick = { room -> LectureRoomRepository.toggleFavorite(room.id) },
            onDetailClick = { room ->
                findNavController().navigate(
                    FavoriteFragmentDirections.actionNavigationFavoriteToLectureRoomDetailFragment(
                        roomName = room.name,
                        buildingName = room.buildingName,
                        buildingDetail = room.buildingDetail,
                        building = " ()"
                    )
                )
            },
            onReserveClick = { room ->
                findNavController().navigate(
                    FavoriteFragmentDirections.actionNavigationFavoriteToManualReservationFragment(
                        building = " ()",
                        roomName = room.name
                    )
                )
            }
        )
        binding.rvFavoriteRooms.layoutManager = LinearLayoutManager(requireContext())
        binding.rvFavoriteRooms.adapter = adapter
    }

    private fun observeFavoriteRooms() {
        LectureRoomRepository.lectureRoomsWithFavorites.observe(viewLifecycleOwner) { allItems ->
            val favoriteRooms = allItems
                .filterIsInstance<ListItem.RoomItem>()
                .filter { it.lectureRoom.isFavorite }
                .map { it.lectureRoom }

            adapter.updateRooms(favoriteRooms)

            binding.rvFavoriteRooms.visibility = if (favoriteRooms.isEmpty()) View.GONE else View.VISIBLE
            binding.tvEmpty.visibility = if (favoriteRooms.isEmpty()) View.VISIBLE else View.GONE
        }
    }

    override fun onResume() {
        super.onResume()
        val navView = requireActivity().findViewById<BottomNavigationView>(R.id.nav_view)
        navView?.visibility = View.VISIBLE
        if (navView?.selectedItemId != R.id.navigation_favorite) {
            navView?.selectedItemId = R.id.navigation_favorite
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
