import 'package:flutter/material.dart';

import '../models/place_category.dart';
import '../models/user_preference.dart';
import '../state/app_scope.dart';
import '../theme/app_theme.dart';
import 'activity_data.dart';

/// 여행 취향 설정 화면(바텀시트).
///
/// 추천 탭 헤더의 "취향 수정"과 마이페이지의 "여행 취향 설정"이
/// 같은 화면을 연다. 여기서 바꾼 값이 곧바로 추천 순서에 반영된다.
class PreferenceSheet extends StatefulWidget {
  const PreferenceSheet({super.key});

  static Future<void> show(BuildContext context) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.background,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
      ),
      builder: (_) => const PreferenceSheet(),
    );
  }

  @override
  State<PreferenceSheet> createState() => _PreferenceSheetState();
}

class _PreferenceSheetState extends State<PreferenceSheet> {
  UserPreference? _editing;
  bool _saving = false;

  UserPreference get _draft => _editing!;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _editing ??= AppScope.read(context).preferenceStore.preference;
  }

  Future<void> _apply() async {
    setState(() => _saving = true);
    try {
      await AppScope.read(context).preferenceStore.update(_draft);
      if (mounted) Navigator.of(context).pop();
    } catch (error) {
      if (mounted) activityError(context, error);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final viewInsets = MediaQuery.of(context).viewInsets.bottom;

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(bottom: viewInsets),
        child: DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.85,
          maxChildSize: 0.95,
          minChildSize: 0.5,
          builder: (context, controller) => Column(
            children: [
              const SizedBox(height: 10),
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: const Color(0xFFD5D9E4),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Expanded(
                child: ListView(
                  controller: controller,
                  padding: const EdgeInsets.fromLTRB(20, 18, 20, 12),
                  children: [
                    Text('여행 취향 설정',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 6),
                    const Text(
                      '설정한 취향에 맞춰 추천 순서가 바로 바뀌어요',
                      style: TextStyle(color: AppColors.textMuted),
                    ),
                    const SizedBox(height: 24),
                    _SectionTitle(
                      title: '혼잡도 선호',
                      description: _draft.crowdToleranceLabel,
                    ),
                    Slider(
                      value: _draft.crowdTolerance,
                      divisions: 10,
                      label: _draft.crowdToleranceLabel,
                      onChanged: (value) => setState(
                        () => _editing = _draft.copyWith(crowdTolerance: value),
                      ),
                    ),
                    const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 8),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('한적한 곳',
                              style: TextStyle(
                                  fontSize: 12, color: AppColors.textMuted)),
                          Text('활기찬 곳',
                              style: TextStyle(
                                  fontSize: 12, color: AppColors.textMuted)),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),
                    const _SectionTitle(
                      title: '실내 / 실외',
                      description: '날씨나 취향에 따라 고르세요',
                    ),
                    const SizedBox(height: 10),
                    SegmentedButton<PlaceTypePreference>(
                      segments: [
                        for (final value in PlaceTypePreference.values)
                          ButtonSegment(value: value, label: Text(value.label)),
                      ],
                      selected: {_draft.typePreference},
                      showSelectedIcon: false,
                      onSelectionChanged: (selection) => setState(
                        () => _editing =
                            _draft.copyWith(typePreference: selection.first),
                      ),
                    ),
                    const SizedBox(height: 24),
                    const _SectionTitle(
                      title: '관심 카테고리',
                      description: '고르지 않으면 전체를 비슷하게 추천해요',
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final category in PlaceCategory.values)
                          FilterChip(
                            label: Text(category.label),
                            avatar: Icon(category.icon, size: 18),
                            selected:
                                _draft.favoriteCategories.contains(category),
                            onSelected: (selected) {
                              final next = Set<PlaceCategory>.from(
                                  _draft.favoriteCategories);
                              if (selected) {
                                next.add(category);
                              } else {
                                next.remove(category);
                              }
                              setState(
                                () => _editing =
                                    _draft.copyWith(favoriteCategories: next),
                              );
                            },
                          ),
                      ],
                    ),
                    const SizedBox(height: 24),
                    _SectionTitle(
                      title: '이동 가능 거리',
                      description:
                          '${_draft.maxDistanceKm.toStringAsFixed(0)}km 이내',
                    ),
                    Slider(
                      value: _draft.maxDistanceKm,
                      min: 1,
                      max: 30,
                      divisions: 29,
                      label: '${_draft.maxDistanceKm.toStringAsFixed(0)}km',
                      onChanged: (value) => setState(
                        () => _editing = _draft.copyWith(maxDistanceKm: value),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Card(
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16)),
                      child: SwitchListTile(
                        contentPadding:
                            const EdgeInsets.symmetric(horizontal: 16),
                        value: _draft.weatherAware,
                        onChanged: (value) => setState(
                          () => _editing = _draft.copyWith(weatherAware: value),
                        ),
                        title: const Text('날씨 반영',
                            style: TextStyle(fontWeight: FontWeight.w600)),
                        subtitle: const Text(
                          '비·눈·폭염일 때 실내 장소를 먼저 추천해요',
                          style: TextStyle(
                              fontSize: 12, color: AppColors.textMuted),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed: () =>
                            setState(() => _editing = const UserPreference()),
                        icon: const Icon(Icons.refresh_rounded, size: 18),
                        label: const Text('기본값으로 되돌리기'),
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 6, 20, 14),
                child: SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _saving ? null : _apply,
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 15),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                    child: const Text('이 취향으로 추천받기',
                        style: TextStyle(
                            fontSize: 15, fontWeight: FontWeight.w700)),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title, required this.description});

  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            description,
            textAlign: TextAlign.right,
            style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
          ),
        ),
      ],
    );
  }
}
