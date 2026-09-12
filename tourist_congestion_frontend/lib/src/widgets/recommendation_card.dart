import 'package:flutter/material.dart';

import '../models/place.dart';
import '../services/recommendation_engine.dart';
import '../state/app_scope.dart';
import '../theme/app_theme.dart';
import 'crowd_badge.dart';
import 'place_image.dart';

/// 추천 탭 전용 카드. 일반 장소 카드에 "추천 점수"와 "추천 이유"를 더했다.
class RecommendationCard extends StatelessWidget {
  const RecommendationCard({
    super.key,
    required this.recommendation,
    this.rank,
    this.onTap,
  });

  final Recommendation recommendation;

  /// 1부터 시작하는 순위. null이면 표시하지 않는다.
  final int? rank;

  final VoidCallback? onTap;

  Place get place => recommendation.place;

  Color get crowdColor => place.crowdColor;

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.watch(context);
    final saved = scope.savedStore.isSaved(place.id);

    return Card(
      margin: EdgeInsets.zero,
      color: AppColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(color: AppColors.border)),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Thumbnail(place: place, rank: rank),
                  const SizedBox(width: 13),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                place.name,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    fontSize: 16, fontWeight: FontWeight.w700),
                              ),
                            ),
                            IconButton(
                              tooltip: saved ? '저장 해제' : '저장',
                              onPressed: scope.savedStore.isPending(place.id)
                                  ? null
                                  : () async {
                                      try {
                                        final nowSaved = await scope.savedStore
                                            .toggle(place);
                                        if (!context.mounted) return;
                                        ScaffoldMessenger.of(context)
                                          ..hideCurrentSnackBar()
                                          ..showSnackBar(
                                            SnackBar(
                                              behavior:
                                                  SnackBarBehavior.floating,
                                              duration:
                                                  const Duration(seconds: 2),
                                              content: Text(
                                                nowSaved
                                                    ? '${place.name} 저장했어요'
                                                    : '${place.name} 저장을 해제했어요',
                                              ),
                                            ),
                                          );
                                      } catch (_) {
                                        if (!context.mounted) return;
                                        ScaffoldMessenger.of(context)
                                            .showSnackBar(
                                          const SnackBar(
                                              content: Text(
                                                  '저장하지 못했어요. 다시 시도해 주세요.')),
                                        );
                                      }
                                    },
                              icon: Icon(
                                saved
                                    ? Icons.favorite_rounded
                                    : Icons.favorite_border_rounded,
                                color: saved
                                    ? AppColors.high
                                    : AppColors.textMuted,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        _MatchScore(score: recommendation.score),
                        const SizedBox(height: 8),
                        Text(
                          [place.area, place.distance]
                              .where((value) => value.isNotEmpty)
                              .join(' · '),
                          style: const TextStyle(
                              fontSize: 12, color: AppColors.textMuted),
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 7,
                          runSpacing: 6,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            CrowdBadge(
                                label: [
                                  if (place.isDemo) '개발 샘플',
                                  if (place.isReplaced) '대체 정보',
                                  place.crowdText,
                                  if (place.isStale) '오래된 정보',
                                ].join(' · '),
                                color: crowdColor),
                            Text(
                              [
                                place.mainCategory?.label ?? place.category,
                                place.indoorOutdoor.label
                              ].where((value) => value.isNotEmpty).join(' · '),
                              style: const TextStyle(
                                  fontSize: 12, color: AppColors.textMuted),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              if (recommendation.reasons.isNotEmpty) ...[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final reason in recommendation.reasons)
                      _ReasonChip(label: reason),
                  ],
                ),
              ],
              if (place.description.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(place.description,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 12, color: AppColors.textMuted, height: 1.5)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Thumbnail extends StatelessWidget {
  const _Thumbnail({required this.place, this.rank});

  final Place place;
  final int? rank;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 84,
      height: 96,
      child: Stack(
        children: [
          Container(
            width: 84,
            height: 96,
            decoration: BoxDecoration(
              color: AppColors.primarySoft,
              borderRadius: BorderRadius.circular(16),
            ),
            child: PlaceImage(url: place.imageUrl, width: 84, height: 96),
          ),
          if (rank != null)
            Positioned(
              left: 0,
              top: 0,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.primary,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  '$rank',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _MatchScore extends StatelessWidget {
  const _MatchScore({required this.score});

  final int score;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.primarySoft,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        '추천 $score점',
        style: const TextStyle(
          color: AppColors.primary,
          fontSize: 11,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _ReasonChip extends StatelessWidget {
  const _ReasonChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(9),
        border: Border.all(color: AppColors.border),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: AppColors.text,
        ),
      ),
    );
  }
}
