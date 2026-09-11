import 'package:flutter/material.dart';

import '../data/mock_places.dart';
import '../models/place.dart';
import '../models/place_category.dart';
import '../models/weather.dart';
import '../services/recommendation_engine.dart';
import '../state/app_scope.dart';
import '../theme/app_theme.dart';
import '../widgets/preference_sheet.dart';
import '../widgets/recommendation_card.dart';
import 'place_detail_screen.dart';

/// 추천 정렬 기준.
enum RecommendSort {
  match('추천순'),
  crowd('한적한 순'),
  distance('가까운 순');

  const RecommendSort(this.label);

  final String label;
}

class RecommendScreen extends StatefulWidget {
  const RecommendScreen({super.key});

  @override
  State<RecommendScreen> createState() => _RecommendScreenState();
}

class _RecommendScreenState extends State<RecommendScreen> {
  static const _engine = RecommendationEngine();

  PlaceCategory? _category;
  RecommendSort _sort = RecommendSort.match;

  List<Recommendation> _sorted(List<Recommendation> items) {
    final list = [...items];
    switch (_sort) {
      case RecommendSort.match:
        break;
      case RecommendSort.crowd:
        list.sort((a, b) => a.place.crowdScore.compareTo(b.place.crowdScore));
      case RecommendSort.distance:
        list.sort((a, b) => a.place.distanceKm.compareTo(b.place.distanceKm));
    }
    return list;
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.watch(context);
    final preference = scope.preferenceStore.preference;
    final anchor = scope.recommendationRequest.anchor;

    final results = _sorted(
      _engine.recommend(
        places: mockPlaces,
        preference: preference,
        category: _category,
        anchor: anchor,
      ),
    );

    return SafeArea(
      child: RefreshIndicator(
        onRefresh: () async => setState(() {}),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
          children: [
            if (anchor != null)
              _AnchorHeader(
                anchor: anchor,
                onClear: scope.recommendationRequest.clear,
              )
            else
              _DefaultHeader(weather: mockPlaces.first.weather),
            const SizedBox(height: 16),
            _PreferenceSummaryCard(
              summary: preference.summary,
              configured: preference.isConfigured,
              onEdit: () => PreferenceSheet.show(context),
            ),
            const SizedBox(height: 18),
            _CategoryFilter(
              selected: _category,
              onSelected: (value) => setState(() => _category = value),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Text(
                  '${results.length}곳',
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textMuted,
                  ),
                ),
                const Spacer(),
                _SortMenu(
                  value: _sort,
                  onChanged: (value) => setState(() => _sort = value),
                ),
              ],
            ),
            const SizedBox(height: 6),
            if (results.isEmpty)
              _EmptyResult(
                anchor: anchor,
                maxDistanceKm: preference.maxDistanceKm,
                onEdit: () => PreferenceSheet.show(context),
              )
            else
              ...results.asMap().entries.map(
                    (entry) => Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: RecommendationCard(
                        recommendation: entry.value,
                        rank: _sort == RecommendSort.match
                            ? entry.key + 1
                            : null,
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) =>
                                PlaceDetailScreen(place: entry.value.place),
                          ),
                        ),
                      ),
                    ),
                  ),
          ],
        ),
      ),
    );
  }
}

class _DefaultHeader extends StatelessWidget {
  const _DefaultHeader({this.weather});

  final Weather? weather;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text('맞춤 추천',
                  style: Theme.of(context).textTheme.headlineSmall),
            ),
            if (weather != null)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(weather!.condition.icon,
                        size: 16, color: AppColors.primary),
                    const SizedBox(width: 5),
                    Text(
                      weather!.summary,
                      style: const TextStyle(
                          fontSize: 12, fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
          ],
        ),
        const SizedBox(height: 6),
        const Text(
          '덜 붐비고 취향에 맞는 장소를 찾아드려요',
          style: TextStyle(color: AppColors.textMuted),
        ),
      ],
    );
  }
}

/// 지도 탭에서 특정 장소를 고르고 넘어왔을 때의 헤더.
class _AnchorHeader extends StatelessWidget {
  const _AnchorHeader({required this.anchor, required this.onClear});

  final Place anchor;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '${anchor.name} 대신 어때요?',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ),
            IconButton(
              tooltip: '전체 추천 보기',
              onPressed: onClear,
              icon: const Icon(Icons.close_rounded),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          '${anchor.name}은(는) 지금 ${anchor.crowdText}(${anchor.crowdScore}). '
          '3km 안에서 비슷한 분위기의 대안을 골랐어요.',
          style: const TextStyle(color: AppColors.textMuted, height: 1.45),
        ),
      ],
    );
  }
}

class _PreferenceSummaryCard extends StatelessWidget {
  const _PreferenceSummaryCard({
    required this.summary,
    required this.configured,
    required this.onEdit,
  });

  final String summary;
  final bool configured;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onEdit,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
          child: Row(
            children: [
              const Icon(Icons.tune_rounded, color: AppColors.primary),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      configured ? '내 취향' : '취향을 설정하면 더 정확해져요',
                      style: const TextStyle(
                          fontSize: 13, fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      summary,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 12, color: AppColors.textMuted),
                    ),
                  ],
                ),
              ),
              TextButton(onPressed: onEdit, child: const Text('수정')),
            ],
          ),
        ),
      ),
    );
  }
}

class _CategoryFilter extends StatelessWidget {
  const _CategoryFilter({required this.selected, required this.onSelected});

  final PlaceCategory? selected;
  final ValueChanged<PlaceCategory?> onSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 42,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: PlaceCategory.values.length + 1,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          if (index == 0) {
            return ChoiceChip(
              label: const Text('전체'),
              selected: selected == null,
              onSelected: (_) => onSelected(null),
            );
          }
          final category = PlaceCategory.values[index - 1];
          return ChoiceChip(
            label: Text(category.label),
            avatar: Icon(
              category.icon,
              size: 17,
              color: selected == category
                  ? AppColors.primary
                  : AppColors.textMuted,
            ),
            selected: selected == category,
            onSelected: (isSelected) =>
                onSelected(isSelected ? category : null),
          );
        },
      ),
    );
  }
}

class _SortMenu extends StatelessWidget {
  const _SortMenu({required this.value, required this.onChanged});

  final RecommendSort value;
  final ValueChanged<RecommendSort> onChanged;

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<RecommendSort>(
      initialValue: value,
      onSelected: onChanged,
      position: PopupMenuPosition.under,
      itemBuilder: (context) => [
        for (final sort in RecommendSort.values)
          PopupMenuItem(value: sort, child: Text(sort.label)),
      ],
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            value.label,
            style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: AppColors.text),
          ),
          const Icon(Icons.keyboard_arrow_down_rounded, size: 18),
        ],
      ),
    );
  }
}

class _EmptyResult extends StatelessWidget {
  const _EmptyResult({
    required this.anchor,
    required this.maxDistanceKm,
    required this.onEdit,
  });

  final Place? anchor;
  final double maxDistanceKm;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 36),
      child: Column(
        children: [
          const Icon(Icons.explore_off_rounded,
              size: 44, color: AppColors.textMuted),
          const SizedBox(height: 12),
          Text(
            anchor != null
                ? '${anchor!.name} 근처에는 비슷한 대안이 없어요'
                : '조건에 맞는 장소가 아직 없어요',
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 6),
          Text(
            '이동 거리(${maxDistanceKm.toStringAsFixed(0)}km)나 카테고리를 넓혀 보세요',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
          ),
          const SizedBox(height: 14),
          OutlinedButton.icon(
            onPressed: onEdit,
            icon: const Icon(Icons.tune_rounded, size: 18),
            label: const Text('취향 조건 수정'),
          ),
        ],
      ),
    );
  }
}
