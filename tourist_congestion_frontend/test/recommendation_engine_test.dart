import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/data/mock_places.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/models/place_category.dart';
import 'package:tourist_congestion_frontend/src/models/user_preference.dart';
import 'package:tourist_congestion_frontend/src/services/recommendation_engine.dart';

void main() {
  const engine = RecommendationEngine();

  Place placeById(String id) => mockPlaces.firstWhere((p) => p.id == id);

  test('한적한 곳을 선호하면 혼잡한 장소가 뒤로 밀린다', () {
    final results = engine.recommend(
      places: mockPlaces,
      preference: const UserPreference(crowdTolerance: 0.0, maxDistanceKm: 30),
    );

    final ranking = results.map((r) => r.place.id).toList();
    expect(
      ranking.indexOf('p-seoul-forest'),
      lessThan(ranking.indexOf('p-gwangjang-market')),
    );
  });

  test('관심 카테고리를 고르면 해당 대분류가 1위가 된다', () {
    final results = engine.recommend(
      places: mockPlaces,
      preference: const UserPreference(
        favoriteCategories: {PlaceCategory.culture},
        maxDistanceKm: 30,
      ),
    );

    expect(results.first.place.mainCategory, PlaceCategory.culture);
  });

  test('이동 가능 거리를 넘는 장소는 제외된다', () {
    final results = engine.recommend(
      places: mockPlaces,
      preference: const UserPreference(maxDistanceKm: 2),
    );

    expect(results.every((r) => r.place.distanceKm <= 2), isTrue);
    expect(results.any((r) => r.place.id == 'p-lotte-world-mall'), isFalse);
  });

  test('비 예보 + 실내 선호면 실내 장소가 먼저 나온다', () {
    final results = engine.recommend(
      places: mockPlaces,
      preference: const UserPreference(
        typePreference: PlaceTypePreference.indoor,
        maxDistanceKm: 30,
      ),
    );

    expect(results.first.place.indoorOutdoor, IndoorOutdoor.indoor);
  });

  test('대안 추천은 기준 장소를 빼고 반경 안에서만 고른다', () {
    final anchor = placeById('p-gyeongbokgung');
    final results = engine.recommend(
      places: mockPlaces,
      preference: const UserPreference(maxDistanceKm: 30),
      anchor: anchor,
      anchorRadiusKm: 3,
    );

    expect(results.any((r) => r.place.id == anchor.id), isFalse);
    expect(results, isNotEmpty);
    // 경복궁(혼잡)보다 한산한 대안이 우선 제시된다.
    expect(results.first.place.crowdScore, lessThan(anchor.crowdScore));
    // 반경 밖 장소는 들어오지 않는다.
    expect(results.any((r) => r.place.id == 'p-lotte-world-mall'), isFalse);
  });

  test('추천 결과에는 이유가 최대 3개까지 담긴다', () {
    final results = engine.recommend(
      places: mockPlaces,
      preference: const UserPreference(maxDistanceKm: 30),
    );

    expect(results.first.reasons, isNotEmpty);
    for (final result in results) {
      expect(result.reasons.length, lessThanOrEqualTo(3));
      expect(result.score, inInclusiveRange(0, 100));
    }
  });
}
