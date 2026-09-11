import 'place_category.dart';

/// 실내/실외 선호.
enum PlaceTypePreference {
  any('상관없음'),
  indoor('실내 선호'),
  outdoor('실외 선호');

  const PlaceTypePreference(this.label);

  final String label;
}

/// 추천 알고리즘의 입력이 되는 사용자 취향.
/// 온보딩에서 한 번 받고, 마이페이지에서 계속 수정할 수 있다.
class UserPreference {
  const UserPreference({
    this.crowdTolerance = 0.25,
    this.typePreference = PlaceTypePreference.any,
    this.favoriteCategories = const <PlaceCategory>{},
    this.maxDistanceKm = 10,
    this.weatherAware = true,
  });

  /// 0.0 = 한적한 곳만, 1.0 = 붐벼도 괜찮음(활기찬 곳 선호).
  final double crowdTolerance;

  final PlaceTypePreference typePreference;

  /// 비어 있으면 "아직 고르지 않음"으로 보고 카테고리 가점을 중립 처리한다.
  final Set<PlaceCategory> favoriteCategories;

  /// 추천에 포함할 최대 거리(km).
  final double maxDistanceKm;

  /// 날씨를 추천에 반영할지 여부.
  final bool weatherAware;

  bool get isConfigured =>
      favoriteCategories.isNotEmpty || typePreference != PlaceTypePreference.any;

  String get crowdToleranceLabel {
    if (crowdTolerance < 0.2) return '한적한 곳만';
    if (crowdTolerance < 0.45) return '조용한 편 선호';
    if (crowdTolerance < 0.7) return '보통이면 OK';
    return '붐벼도 괜찮음';
  }

  /// 취향 요약 한 줄. 추천 탭 헤더와 마이페이지에서 함께 쓴다.
  String get summary {
    final categories = favoriteCategories.isEmpty
        ? '전체 카테고리'
        : favoriteCategories.map((c) => c.label).join(', ');
    return '$crowdToleranceLabel · ${typePreference.label} · $categories';
  }

  UserPreference copyWith({
    double? crowdTolerance,
    PlaceTypePreference? typePreference,
    Set<PlaceCategory>? favoriteCategories,
    double? maxDistanceKm,
    bool? weatherAware,
  }) {
    return UserPreference(
      crowdTolerance: crowdTolerance ?? this.crowdTolerance,
      typePreference: typePreference ?? this.typePreference,
      favoriteCategories: favoriteCategories ?? this.favoriteCategories,
      maxDistanceKm: maxDistanceKm ?? this.maxDistanceKm,
      weatherAware: weatherAware ?? this.weatherAware,
    );
  }

  /// 백엔드 사용자 취향 API가 생기면 그대로 실어 보낼 수 있는 형태.
  Map<String, dynamic> toJson() => {
        'crowd_tolerance': crowdTolerance,
        'place_type': typePreference.name,
        'favorite_categories':
            favoriteCategories.map((c) => c.contentTypeId).toList(),
        'max_distance_km': maxDistanceKm,
        'weather_aware': weatherAware,
      };

  factory UserPreference.fromJson(Map<String, dynamic> json) {
    final rawCategories = (json['favorite_categories'] as List?) ?? const [];
    return UserPreference(
      crowdTolerance: (json['crowd_tolerance'] as num?)?.toDouble() ?? 0.25,
      typePreference: PlaceTypePreference.values.firstWhere(
        (value) => value.name == json['place_type'],
        orElse: () => PlaceTypePreference.any,
      ),
      favoriteCategories: rawCategories
          .map((id) => PlaceCategory.fromContentTypeId(id as int))
          .toSet(),
      maxDistanceKm: (json['max_distance_km'] as num?)?.toDouble() ?? 10,
      weatherAware: json['weather_aware'] as bool? ?? true,
    );
  }
}
