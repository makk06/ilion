import 'dart:async';
import '../models/crowd_forecast.dart';
import 'package:flutter/material.dart';

import '../models/place.dart';
import '../theme/app_theme.dart';
import '../models/place_category.dart';
import '../services/place_service.dart';
import '../services/recommendation_engine.dart';
import '../state/app_scope.dart';
import '../widgets/app_chrome.dart';
import '../widgets/preference_sheet.dart';
import '../widgets/recommendation_card.dart';
import 'place_detail_screen.dart';

class PersonalizedRecommendationsScreen extends StatefulWidget {
  const PersonalizedRecommendationsScreen({super.key, this.clock});
  final DateTime Function()? clock;

  @override
  State<PersonalizedRecommendationsScreen> createState() =>
      _PersonalizedRecommendationsScreenState();
}

enum _Sort { recommendation, crowd, distance }

class _PersonalizedRecommendationsScreenState
    extends State<PersonalizedRecommendationsScreen>
    with WidgetsBindingObserver {
  final _places = <Place>[];
  DateTime? _visitAt;
  DateTime _clock = DateTime.now();
  Timer? _timer;
  PlaceCategory? _category;
  _Sort _sort = _Sort.recommendation;
  int _page = 0;
  bool _hasMore = true, _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _clock = widget.clock?.call() ?? DateTime.now();
    WidgetsBinding.instance.addObserver(this);
    _timer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _refreshClock(),
    );
    _load();
  }

  void _refreshClock() {
    if (!mounted) return;
    final previous = _clock;
    setState(() => _clock = widget.clock?.call() ?? DateTime.now());
    if (_clock.hour != previous.hour || _clock.day != previous.day) {
      _load(refresh: true);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refreshClock();
      _load(refresh: true);
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _load({bool refresh = false}) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await PlaceService.instance.list(
        page: refresh ? 1 : _page + 1,
      );
      if (!mounted) return;
      setState(() {
        if (refresh) _places.clear();
        final ids = _places.map((p) => p.id).toSet();
        _places.addAll(result.items.where((p) => ids.add(p.id)));
        _page = result.page;
        _hasMore = result.hasMore;
      });
    } catch (_) {
      if (mounted) setState(() => _error = '장소를 불러오지 못했어요. 다시 시도해 주세요.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  int _compareNullable(num? a, num? b) =>
      a == null ? (b == null ? 0 : 1) : (b == null ? -1 : a.compareTo(b));

  int _compareNullableGroup(String? a, String? b) => a == null
      ? (b == null ? 0 : 1)
      : b == null
      ? -1
      : a.compareTo(b);

  num? _crowd(Place p) =>
      !p.canUseCrowd || p.crowdConfidence < .4 ? null : p.crowdScore;

  @override
  Widget build(BuildContext context) {
    final preference = AppScope.watch(context).preferenceStore.preference;
    final results = const RecommendationEngine().recommend(
      places: _places,
      preference: preference,
      category: _category,
      visitAt: _visitAt,
      now: _clock,
    );
    if (_sort != _Sort.recommendation) {
      results.sort((a, b) {
        if (_sort == _Sort.crowd && _visitAt != null) {
          final group = _compareNullableGroup(
            a.comparisonGroup,
            b.comparisonGroup,
          );
          if (group != 0) return group;
          return _compareNullable(a.crowdForRanking, b.crowdForRanking);
        }
        final order = _sort == _Sort.crowd
            ? _compareNullable(_crowd(a.place), _crowd(b.place))
            : _compareNullable(a.place.distanceKm, b.place.distanceKm);
        return order == 0 ? b.score.compareTo(a.score) : order;
      });
    }
    final times = <DateTime>{
      for (final p in _places)
        for (final f in p.crowdEstimate?.hourlyForecasts ?? <CrowdForecast>[])
          if (f.usableAt(_clock)) f.validAt!.toUtc(),
    }.toList()..sort();
    final unavailable =
        _visitAt != null && !times.any((t) => t.isAtSameMomentAs(_visitAt!));
    return Scaffold(
      appBar: const GreenAppBar(title: '맞춤 장소 추천'),
      body: AppContent(
        child: RefreshIndicator(
          onRefresh: () => _load(refresh: true),
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      '내 취향에 맞는 다음 여행',
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        height: 1.3,
                      ),
                    ),
                  ),
                  TextButton.icon(
                    onPressed: () => PreferenceSheet.show(context),
                    icon: const Icon(Icons.tune, size: 18),
                    label: const Text('취향 수정'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              const Text(
                '불러온 장소에서 취향에 맞춰 추천해요.\n거리·날씨는 실제 정보가 있을 때만 반영해요.',
                style: TextStyle(
                  fontSize: 12,
                  color: AppColors.textMuted,
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                '방문 시각',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
              Wrap(
                spacing: 8,
                children: [
                  ChoiceChip(
                    label: const Text('지금'),
                    selected: _visitAt == null,
                    onSelected: (_) => setState(() => _visitAt = null),
                  ),
                  for (final t in times)
                    ChoiceChip(
                      label: Text(
                        forecastTimeLabel(t, _clock).replaceAll(' 예상', ''),
                      ),
                      selected: _visitAt?.isAtSameMomentAs(t) == true,
                      onSelected: (_) => setState(() => _visitAt = t),
                    ),
                ],
              ),
              if (times.isEmpty)
                const Text(
                  '검증된 미래 예측이 아직 없어요.',
                  style: TextStyle(fontSize: 12),
                ),
              if (unavailable)
                Text(
                  '${forecastTimeLabel(_visitAt!, _clock)} 정보가 만료되었거나 없어졌어요. 방문 시각을 다시 선택해 주세요.',
                ),
              const SizedBox(height: 20),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    ChoiceChip(
                      label: const Text('전체'),
                      selected: _category == null,
                      onSelected: (_) => setState(() => _category = null),
                    ),
                    for (final category in PlaceCategory.values)
                      Padding(
                        padding: const EdgeInsets.only(left: 8),
                        child: ChoiceChip(
                          label: Text(category.label),
                          selected: _category == category,
                          onSelected: (_) =>
                              setState(() => _category = category),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              const Divider(height: 1),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '추천 ${results.length}곳',
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  PopupMenuButton<_Sort>(
                    tooltip: '추천 정렬',
                    initialValue: _sort,
                    onSelected: (value) => setState(() => _sort = value),
                    itemBuilder: (_) => [
                      const PopupMenuItem(
                        value: _Sort.recommendation,
                        child: Text('추천순'),
                      ),
                      PopupMenuItem(
                        value: _Sort.crowd,
                        child: Text(_visitAt == null ? '여유로운순' : '평소 대비 한산한 순'),
                      ),
                      const PopupMenuItem(
                        value: _Sort.distance,
                        child: Text('가까운순'),
                      ),
                    ],
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(switch (_sort) {
                            _Sort.recommendation => '추천순',
                            _Sort.crowd =>
                              _visitAt == null ? '여유로운순' : '평소 대비 한산한 순',
                            _Sort.distance => '가까운순',
                          }),
                          const Icon(Icons.expand_more, size: 18),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              if (_sort != _Sort.recommendation)
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: Text(
                    '비교할 정보가 없는 장소는 뒤에 표시해요.',
                    style: TextStyle(fontSize: 12, color: AppColors.textMuted),
                  ),
                ),
              if (_visitAt != null && _sort == _Sort.crowd)
                const Text(
                  '같은 공급자·지표 그룹 안에서 비교해요. 그룹 간 실제 밀집도 순서가 아닙니다.',
                  style: TextStyle(fontSize: 12),
                ),
              for (final entry in results.indexed) ...[
                if (_visitAt != null &&
                    _sort == _Sort.crowd &&
                    (entry.$1 == 0 ||
                        results[entry.$1 - 1].comparisonGroup !=
                            entry.$2.comparisonGroup))
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Text(
                      entry.$2.comparisonGroup == null
                          ? '비교 정보 없음'
                          : entry.$2.forecast!.groupLabel,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: RecommendationCard(
                    recommendation: entry.$2,
                    rank: _sort == _Sort.recommendation ? entry.$1 + 1 : null,
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) =>
                            PlaceDetailScreen(place: entry.$2.place),
                      ),
                    ),
                  ),
                ),
              ],
              if (!_loading && results.isEmpty && _error == null)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 32),
                  child: Text(
                    _hasMore
                        ? '불러온 장소 중 조건에 맞는 곳이 없어요.\n다음 장소를 더 불러와 보세요.'
                        : '조건에 맞는 장소가 없어요. 취향이나 분류를 바꿔 보세요.',
                    textAlign: TextAlign.center,
                  ),
                ),
              if (_error != null) ...[
                Text(_error!, textAlign: TextAlign.center),
                TextButton(
                  onPressed: () => _load(),
                  child: const Text('다시 시도'),
                ),
              ] else if (_loading)
                const Center(
                  child: Padding(
                    padding: EdgeInsets.all(20),
                    child: CircularProgressIndicator(),
                  ),
                )
              else if (_hasMore)
                OutlinedButton(
                  onPressed: () => _load(),
                  child: const Text('장소 더 불러오기'),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
