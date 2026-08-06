import 'package:flutter/material.dart';

import '../data/mock_places.dart';
import '../theme/app_theme.dart';
import '../widgets/place_card.dart';

class SavedScreen extends StatelessWidget {
  const SavedScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
        children: [
          Text('저장한 장소', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 6),
          const Text('나중에 가고 싶은 장소를 모아보세요', style: TextStyle(color: AppColors.textMuted)),
          const SizedBox(height: 22),
          PlaceCard(place: mockPlaces.first, isSaved: true),
          const SizedBox(height: 12),
          PlaceCard(place: mockPlaces[1], isSaved: true),
        ],
      ),
    );
  }
}
