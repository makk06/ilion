import '../models/place.dart';
import '../models/place_category.dart';
import '../models/user_preference.dart';
import '../utils/geo.dart';

/// 한 장소의 추천 결과. 점수와 함께 "왜 추천했는지"를 같이 들고 다닌다.
class Recommendation {
  const Recommendation({
    required this.place,
    required this.score,
    required this.reasons,
  });

  final Place place;

  /// 0~100.
  final int score;

  /// 카드에 칩으로 노출할 추천 근거. 중요한 순서대로 담긴다.
  final List<String> reasons;
}

/// 사용자 취향 기반 추천 점수 계산기.
///
/// 백엔드 추천 API가 아직 없어(DECISIONS.md: 추천 점수 API는 1차 범위 제외)
/// 지금은 앱에서 계산한다. 나중에 서버 점수로 바꾸더라도 화면은
/// [Recommendation] 만 보면 되도록 분리해 두었다.
class RecommendationEngine {
  const RecommendationEngine();

  // 항목별 가중치. 합이 1이 되도록 유지한다.
  static const _crowdWeight = 0.32;
  static const _categoryWeight = 0.22;
  static const _typeWeight = 0.16;
  static const _distanceWeight = 0.18;
  static const _weatherWeight = 0.12;

  /// 취향에 맞는 추천 목록을 점수 내림차순으로 돌려준다.
  ///
  /// [category] 가 주어지면 해당 대분류만 남긴다.
  /// [anchor] 가 주어지면 지도에서 고른 장소 "대신 갈 만한 근처 장소"를 찾는다.
  List<Recommendation> recommend({
    required List<Place> places,
    required UserPreference preference,
    PlaceCategory? category,
    Place? anchor,
    double anchorRadiusKm = 3.0,
  }) {
    final results = <Recommendation>[];

    for (final place in places) {
      if (place.id == anchor?.id) continue;
      if (category != null && place.mainCategory != category) continue;
      if (place.distanceKm != null &&
          place.distanceKm! > preference.maxDistanceKm) {
        continue;
      }

      double? anchorDistanceKm;
      if (anchor != null) {
        if (!anchor.hasCoordinates || !place.hasCoordinates) continue;
        anchorDistanceKm = distanceKmBetween(
          anchor.latitude!,
          anchor.longitude!,
          place.latitude!,
          place.longitude!,
        );
        if (anchorDistanceKm > anchorRadiusKm) continue;
      }

      results.add(
        _score(
          place: place,
          preference: preference,
          anchor: anchor,
          anchorDistanceKm: anchorDistanceKm,
          anchorRadiusKm: anchorRadiusKm,
        ),
      );
    }

    results.sort((a, b) => b.score.compareTo(a.score));
    return results;
  }

  Recommendation _score({
    required Place place,
    required UserPreference preference,
    Place? anchor,
    double? anchorDistanceKm,
    double anchorRadiusKm = 3.0,
  }) {
    final crowdFit = _crowdFit(place, preference);
    final categoryFit = _categoryFit(place, preference);
    final typeFit = _typeFit(place, preference);
    final distanceFit = _distanceFit(place, preference);
    final weatherFit = _weatherFit(place, preference);

    final signals = <(double?, double)>[
      (crowdFit, _crowdWeight),
      (categoryFit, _categoryWeight),
      (typeFit, _typeWeight),
      (distanceFit, _distanceWeight),
      (weatherFit, _weatherWeight),
    ];
    var sum = 0.0;
    var weight = 0.0;
    for (final signal in signals) {
      if (signal.$1 == null) continue;
      sum += signal.$1! * signal.$2;
      weight += signal.$2;
    }
    var total = weight == 0 ? 0.0 : sum / weight;

    if (anchor != null) {
      // 대안 추천에서는 "원래 장소와 얼마나 닮았고 얼마나 가까운지"를 섞는다.
      final similarity = _similarity(
        anchor: anchor,
        place: place,
        anchorDistanceKm: anchorDistanceKm ?? 0,
        anchorRadiusKm: anchorRadiusKm,
      );
      total = total * 0.6 + similarity * 0.4;
    }

    return Recommendation(
      place: place,
      score: (total * 100).round().clamp(0, 100),
      reasons: _reasons(
        place: place,
        preference: preference,
        anchor: anchor,
        anchorDistanceKm: anchorDistanceKm,
        crowdFit: crowdFit,
        categoryFit: categoryFit,
        typeFit: typeFit,
        distanceFit: distanceFit,
        weatherFit: weatherFit,
      ),
    );
  }

  /// 혼잡도 적합도.
  /// 원하는 수준보다 붐비면 크게 깎고, 반대로 너무 한산한 경우는
  /// "활기찬 곳을 좋아하는 사용자"에게만 조금 깎는다.
  double? _crowdFit(Place place, UserPreference preference) {
    if (place.crowdScore == null ||
        place.isDemo ||
        place.isReplaced ||
        place.isStale) {
      return null;
    }
    final desired = preference.crowdTolerance * 100;
    final diff = (place.crowdScore! - desired) / 100;
    if (diff > 0) return (1 - diff).clamp(0.0, 1.0);
    return (1 - diff.abs() * preference.crowdTolerance * 0.6).clamp(0.0, 1.0);
  }

  double? _categoryFit(Place place, UserPreference preference) {
    if (place.mainCategory == null) return null;
    if (preference.favoriteCategories.isEmpty) return 0.6;
    return preference.favoriteCategories.contains(place.mainCategory)
        ? 1.0
        : 0.25;
  }

  double? _typeFit(Place place, UserPreference preference) {
    if (place.indoorOutdoor == IndoorOutdoor.unknown) return null;
    if (preference.typePreference == PlaceTypePreference.any) return 0.75;
    if (place.indoorOutdoor == IndoorOutdoor.unknown) return null;
    final wantsIndoor = preference.typePreference == PlaceTypePreference.indoor;
    final isIndoor = place.indoorOutdoor == IndoorOutdoor.indoor;
    return wantsIndoor == isIndoor ? 1.0 : 0.2;
  }

  double? _distanceFit(Place place, UserPreference preference) {
    if (place.distanceKm == null) return null;
    if (preference.maxDistanceKm <= 0) return 0.0;
    return (1 - place.distanceKm! / preference.maxDistanceKm).clamp(0.0, 1.0);
  }

  double? _weatherFit(Place place, UserPreference preference) {
    final weather = place.weather;
    if (!preference.weatherAware ||
        weather == null ||
        place.indoorOutdoor == IndoorOutdoor.unknown) {
      return null;
    }
    if (!weather.condition.prefersIndoor) return 0.8;
    return switch (place.indoorOutdoor) {
      IndoorOutdoor.indoor => 1.0,
      IndoorOutdoor.unknown => 0.6,
      IndoorOutdoor.outdoor => 0.3,
    };
  }

  /// 대안 추천용 유사도. 같은 대분류·공통 태그·가까운 거리에 가점을 주고,
  /// 원래 장소보다 한산하면 추가 가점을 준다.
  double _similarity({
    required Place anchor,
    required Place place,
    required double anchorDistanceKm,
    required double anchorRadiusKm,
  }) {
    var score = 0.0;
    score +=
        place.mainCategory != null && place.mainCategory == anchor.mainCategory
            ? 0.35
            : 0.1;

    final sharedTags = place.tags.toSet().intersection(anchor.tags.toSet());
    score += (sharedTags.length * 0.1).clamp(0.0, 0.2);

    score += place.indoorOutdoor != IndoorOutdoor.unknown &&
            place.indoorOutdoor == anchor.indoorOutdoor
        ? 0.1
        : 0.0;

    final proximity =
        (1 - anchorDistanceKm / anchorRadiusKm).clamp(0.0, 1.0) * 0.15;
    score += proximity;

    if (anchor.crowdScore != null &&
        place.crowdScore != null &&
        !anchor.isDemo &&
        !place.isDemo &&
        !anchor.isReplaced &&
        !place.isReplaced &&
        !anchor.isStale &&
        !place.isStale) {
      final relief =
          ((anchor.crowdScore! - place.crowdScore!) / 100).clamp(0.0, 1.0);
      score += relief * 0.2;
    }

    return score.clamp(0.0, 1.0);
  }

  List<String> _reasons({
    required Place place,
    required UserPreference preference,
    Place? anchor,
    double? anchorDistanceKm,
    required double? crowdFit,
    required double? categoryFit,
    required double? typeFit,
    required double? distanceFit,
    required double? weatherFit,
  }) {
    final reasons = <String>[];

    if (anchor != null) {
      if (place.mainCategory != null &&
          place.mainCategory == anchor.mainCategory) {
        reasons.add('${anchor.name}과 같은 ${place.mainCategory!.label}');
      }
      if (crowdFit != null &&
          _crowdFit(anchor, preference) != null &&
          place.crowdScore! < anchor.crowdScore! - 10) {
        reasons.add('${anchor.name}보다 한산해요');
      }
      if (anchorDistanceKm != null && anchorDistanceKm <= 1.5) {
        reasons.add('${anchor.name}에서 ${_formatKm(anchorDistanceKm)}');
      }
    }

    if (crowdFit != null && crowdFit >= 0.8) {
      reasons.add(
        place.crowdLevel == CrowdLevel.low ? '지금 여유로워요' : '원하는 혼잡도예요',
      );
    } else if (crowdFit != null && crowdFit < 0.5) {
      reasons.add('선호하는 혼잡도보다 붐벼요');
    }

    if (categoryFit != null && categoryFit >= 1.0) {
      reasons.add('관심 카테고리 · ${place.mainCategory!.label}');
    }

    if (typeFit != null && typeFit >= 1.0) {
      reasons.add('${place.indoorOutdoor.label} 선호와 일치');
    }

    final weather = place.weather;
    if (preference.weatherAware &&
        weather != null &&
        weather.condition.prefersIndoor &&
        place.indoorOutdoor == IndoorOutdoor.indoor) {
      reasons.add('${weather.condition.label} 예보 · 실내라 안심');
    }

    if (distanceFit != null && distanceFit >= 0.8) {
      reasons.add('${place.distance}로 가까워요');
    }

    return reasons.take(3).toList();
  }

  String _formatKm(double km) =>
      km < 1 ? '${(km * 1000).round()}m' : '${km.toStringAsFixed(1)}km';
}
