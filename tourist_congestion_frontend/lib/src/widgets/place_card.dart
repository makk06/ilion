import 'package:flutter/material.dart';

import '../models/place.dart';
import '../state/app_scope.dart';
import '../theme/app_theme.dart';
import 'crowd_badge.dart';

class PlaceCard extends StatelessWidget {
  const PlaceCard({
    super.key,
    required this.place,
    this.showDescription = false,
    this.isSaved,
    this.onTap,
    this.onToggleSave,
    this.trailing,
  });

  final Place place;
  final bool showDescription;

  /// 지정하지 않으면 저장 상태를 [AppScope] 에서 읽어 온다.
  final bool? isSaved;

  final VoidCallback? onTap;

  /// 지정하지 않으면 하트를 눌렀을 때 저장 목록을 직접 토글한다.
  final VoidCallback? onToggleSave;

  /// 하트 대신 넣을 위젯. 저장 탭의 삭제 버튼처럼 다른 동작이 필요할 때 쓴다.
  final Widget? trailing;

  Color get crowdColor => switch (place.crowdLevel) {
        CrowdLevel.low => AppColors.low,
        CrowdLevel.medium => AppColors.medium,
        CrowdLevel.high => AppColors.high,
      };

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.watch(context);
    final saved = isSaved ?? scope.savedStore.isSaved(place.id);

    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 74,
                height: 74,
                decoration: BoxDecoration(
                  color: AppColors.primarySoft,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Icon(place.icon, size: 34, color: AppColors.primary),
              ),
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
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                          ),
                        ),
                        trailing ??
                            IconButton(
                              visualDensity: VisualDensity.compact,
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                              tooltip: saved ? '저장 해제' : '저장',
                              onPressed: onToggleSave ??
                                  () => scope.savedStore.toggle(place),
                              icon: Icon(
                                saved
                                    ? Icons.favorite_rounded
                                    : Icons.favorite_border_rounded,
                                size: 20,
                                color: saved ? AppColors.high : AppColors.textMuted,
                              ),
                            ),
                      ],
                    ),
                    const SizedBox(height: 5),
                    Text(
                      '${place.area} · ${place.distance}',
                      style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 7,
                      runSpacing: 6,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        CrowdBadge(label: place.crowdText, color: crowdColor),
                        Text(place.category, style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                      ],
                    ),
                    if (showDescription) ...[
                      const SizedBox(height: 10),
                      Text(
                        place.description,
                        style: const TextStyle(fontSize: 12, color: AppColors.textMuted, height: 1.45),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
