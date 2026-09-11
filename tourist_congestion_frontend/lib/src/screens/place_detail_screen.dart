import 'package:flutter/material.dart';

import '../models/place.dart';
import '../state/app_scope.dart';
import '../theme/app_theme.dart';
import '../widgets/crowd_badge.dart';

/// 장소 상세 화면.
/// 장소명 · 주소 · 거리 · 혼잡도 · 분류 · 날씨를 한 화면에서 보여 주고,
/// 하단의 "근처 대안 추천 보기"로 추천 탭으로 넘어간다.
///
/// 지도 탭에서도 그대로 재사용할 수 있다.
class PlaceDetailScreen extends StatelessWidget {
  const PlaceDetailScreen({super.key, required this.place});

  final Place place;

  Color get crowdColor => switch (place.crowdLevel) {
        CrowdLevel.low => AppColors.low,
        CrowdLevel.medium => AppColors.medium,
        CrowdLevel.high => AppColors.high,
      };

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.watch(context);
    final saved = scope.savedStore.isSaved(place.id);
    final weather = place.weather;

    return Scaffold(
      appBar: AppBar(
        title: Text(place.name),
        backgroundColor: AppColors.background,
        actions: [
          IconButton(
            tooltip: saved ? '저장 해제' : '저장',
            onPressed: () => scope.savedStore.toggle(place),
            icon: Icon(
              saved ? Icons.favorite_rounded : Icons.favorite_border_rounded,
              color: saved ? AppColors.high : AppColors.textMuted,
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: AppColors.primarySoft,
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Icon(place.icon, size: 32, color: AppColors.primary),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(place.name,
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 6),
                    Text(
                      place.address,
                      style: const TextStyle(
                          fontSize: 13, color: AppColors.textMuted, height: 1.4),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Card(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      CrowdBadge(label: place.crowdText, color: crowdColor),
                      const SizedBox(width: 8),
                      Text(
                        '혼잡도 ${place.crowdScore}/100',
                        style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: AppColors.textMuted),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: LinearProgressIndicator(
                      value: place.crowdScore / 100,
                      minHeight: 8,
                      backgroundColor: AppColors.background,
                      valueColor: AlwaysStoppedAnimation(crowdColor),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    place.description,
                    style: const TextStyle(
                        fontSize: 13, color: AppColors.textMuted, height: 1.5),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: _InfoTile(
                  icon: Icons.near_me_rounded,
                  label: '거리',
                  value: place.distance,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _InfoTile(
                  icon: place.mainCategory.icon,
                  label: '분류',
                  value: place.mainCategory.label,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _InfoTile(
                  icon: Icons.meeting_room_rounded,
                  label: '실내외',
                  value: place.indoorOutdoor.label,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _InfoTile(
                  icon: weather?.condition.icon ?? Icons.cloud_off_rounded,
                  label: '날씨',
                  value: weather?.summary ?? '정보 없음',
                ),
              ),
            ],
          ),
          if (place.tags.isNotEmpty) ...[
            const SizedBox(height: 18),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final tag in place.tags)
                  Chip(
                    label: Text('#$tag'),
                    labelStyle: const TextStyle(fontSize: 12),
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
          ],
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () {
                scope.recommendationRequest.requestAlternatives(place);
                Navigator.of(context).popUntil((route) => route.isFirst);
              },
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14)),
              ),
              icon: const Icon(Icons.explore_rounded, size: 20),
              label: const Text(
                '근처 대안 추천 보기',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _InfoTile extends StatelessWidget {
  const _InfoTile({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20, color: AppColors.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label,
                    style: const TextStyle(
                        fontSize: 11, color: AppColors.textMuted)),
                const SizedBox(height: 2),
                Text(
                  value,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w700),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
