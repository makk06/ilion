import 'package:flutter/material.dart';

import '../models/place.dart';
import '../models/place_category.dart';
import '../state/app_scope.dart';
import '../theme/app_theme.dart';
import '../widgets/place_card.dart';
import 'place_detail_screen.dart';

/// 저장 목록 정렬 기준.
enum SavedSort {
  recent('최근 저장순'),
  crowd('한적한 순'),
  distance('가까운 순'),
  name('이름순');

  const SavedSort(this.label);

  final String label;
}

class SavedScreen extends StatefulWidget {
  const SavedScreen({super.key});

  @override
  State<SavedScreen> createState() => _SavedScreenState();
}

class _SavedScreenState extends State<SavedScreen> {
  SavedSort _sort = SavedSort.recent;
  PlaceCategory? _category;

  List<Place> _apply(List<Place> places) {
    final list = _category == null
        ? [...places]
        : places.where((p) => p.mainCategory == _category).toList();

    switch (_sort) {
      case SavedSort.recent:
        break; // SavedStore 가 이미 최근 저장순으로 준다.
      case SavedSort.crowd:
        list.sort((a, b) => a.crowdScore.compareTo(b.crowdScore));
      case SavedSort.distance:
        list.sort((a, b) => a.distanceKm.compareTo(b.distanceKm));
      case SavedSort.name:
        list.sort((a, b) => a.name.compareTo(b.name));
    }
    return list;
  }

  void _remove(Place place) {
    final store = AppScope.read(context).savedStore;
    final savedAt = store.savedAt(place.id);
    store.remove(place.id);

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          behavior: SnackBarBehavior.floating,
          content: Text('${place.name} 저장을 해제했어요'),
          action: SnackBarAction(
            label: '되돌리기',
            onPressed: () => store.add(place, at: savedAt),
          ),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.watch(context);
    final saved = scope.savedStore.places;
    final visible = _apply(saved);

    // 저장한 목록에 실제로 들어 있는 카테고리만 칩으로 보여 준다.
    final availableCategories = <PlaceCategory>{
      for (final place in saved) place.mainCategory,
    }.toList()
      ..sort((a, b) => a.index.compareTo(b.index));

    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
        children: [
          Text('저장한 장소', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 6),
          Text(
            saved.isEmpty
                ? '나중에 가고 싶은 장소를 모아보세요'
                : '${saved.length}곳을 저장했어요',
            style: const TextStyle(color: AppColors.textMuted),
          ),
          if (saved.isEmpty)
            const _SavedEmptyState()
          else ...[
            const SizedBox(height: 18),
            if (availableCategories.length > 1)
              _CategoryFilter(
                categories: availableCategories,
                selected: _category,
                onSelected: (value) => setState(() => _category = value),
              ),
            const SizedBox(height: 12),
            Row(
              children: [
                Text(
                  '${visible.length}곳',
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textMuted,
                  ),
                ),
                const Spacer(),
                PopupMenuButton<SavedSort>(
                  initialValue: _sort,
                  position: PopupMenuPosition.under,
                  onSelected: (value) => setState(() => _sort = value),
                  itemBuilder: (context) => [
                    for (final sort in SavedSort.values)
                      PopupMenuItem(value: sort, child: Text(sort.label)),
                  ],
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        _sort.label,
                        style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            color: AppColors.text),
                      ),
                      const Icon(Icons.keyboard_arrow_down_rounded, size: 18),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            if (visible.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 36),
                child: Center(
                  child: Text(
                    '이 카테고리로 저장한 장소가 없어요',
                    style: TextStyle(color: AppColors.textMuted),
                  ),
                ),
              )
            else
              ...visible.map(
                (place) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Dismissible(
                    key: ValueKey(place.id),
                    direction: DismissDirection.endToStart,
                    background: const _DismissBackground(),
                    onDismissed: (_) => _remove(place),
                    child: PlaceCard(
                      place: place,
                      isSaved: true,
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => PlaceDetailScreen(place: place),
                        ),
                      ),
                      onToggleSave: () => _remove(place),
                    ),
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _CategoryFilter extends StatelessWidget {
  const _CategoryFilter({
    required this.categories,
    required this.selected,
    required this.onSelected,
  });

  final List<PlaceCategory> categories;
  final PlaceCategory? selected;
  final ValueChanged<PlaceCategory?> onSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 42,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: categories.length + 1,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          if (index == 0) {
            return ChoiceChip(
              label: const Text('전체'),
              selected: selected == null,
              onSelected: (_) => onSelected(null),
            );
          }
          final category = categories[index - 1];
          return ChoiceChip(
            label: Text(category.label),
            selected: selected == category,
            onSelected: (isSelected) =>
                onSelected(isSelected ? category : null),
          );
        },
      ),
    );
  }
}

class _DismissBackground extends StatelessWidget {
  const _DismissBackground();

  @override
  Widget build(BuildContext context) {
    return Container(
      alignment: Alignment.centerRight,
      padding: const EdgeInsets.only(right: 22),
      decoration: BoxDecoration(
        color: AppColors.high.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.delete_outline_rounded, color: AppColors.high),
          SizedBox(width: 6),
          Text(
            '저장 해제',
            style: TextStyle(
                color: AppColors.high, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}

class _SavedEmptyState extends StatelessWidget {
  const _SavedEmptyState();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 70),
      child: Column(
        children: [
          Container(
            width: 84,
            height: 84,
            decoration: const BoxDecoration(
              color: AppColors.primarySoft,
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.favorite_border_rounded,
                size: 40, color: AppColors.primary),
          ),
          const SizedBox(height: 18),
          const Text(
            '아직 저장한 장소가 없어요',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          const Text(
            '추천 탭이나 지도에서 하트를 누르면\n여기에 모여요',
            textAlign: TextAlign.center,
            style: TextStyle(
                fontSize: 13, color: AppColors.textMuted, height: 1.5),
          ),
        ],
      ),
    );
  }
}
