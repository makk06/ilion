import 'package:flutter/material.dart';

import '../data/mock_places.dart';
import '../theme/app_theme.dart';
import '../widgets/place_card.dart';

class RecommendScreen extends StatefulWidget {
  const RecommendScreen({super.key});

  @override
  State<RecommendScreen> createState() => _RecommendScreenState();
}

class _RecommendScreenState extends State<RecommendScreen> {
  int _selected = 0;
  static const _filters = ['전체', '자연', '문화', '카페', '실내'];

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
        children: [
          Text('맞춤 추천', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 6),
          const Text('덜 붐비고 취향에 맞는 장소를 찾아드려요', style: TextStyle(color: AppColors.textMuted)),
          const SizedBox(height: 20),
          SizedBox(
            height: 42,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: _filters.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (context, index) => ChoiceChip(
                label: Text(_filters[index]),
                selected: _selected == index,
                onSelected: (_) => setState(() => _selected = index),
              ),
            ),
          ),
          const SizedBox(height: 24),
          ...mockPlaces.map(
            (place) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: PlaceCard(place: place, showDescription: true),
            ),
          ),
        ],
      ),
    );
  }
}
