import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/data/mock_places.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/models/place_category.dart';
import 'package:tourist_congestion_frontend/src/models/user_preference.dart';
import 'package:tourist_congestion_frontend/src/services/recommendation_engine.dart';

void main() {
  const engine = RecommendationEngine();

  Place placeById(int id) => mockPlaces.firstWhere((p) => p.id == id);

  test('한적한 곳을 선호하면 혼잡한 장소가 뒤로 밀린다', () {
    final results = engine.recommend(
      places: mockPlaces,
      preference: const UserPreference(crowdTolerance: 0.0, maxDistanceKm: 30),
    );

    final ranking = results.map((r) => r.place.id).toList();
    expect(
      ranking.indexOf(-1),
      lessThan(ranking.indexOf(-10)),
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

    expect(results.every((r) => r.place.distanceKm! <= 2), isTrue);
    expect(results.any((r) => r.place.id == -13), isFalse);
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
    final anchor = placeById(-3);
    final results = engine.recommend(
      places: mockPlaces,
      preference: const UserPreference(maxDistanceKm: 30),
      anchor: anchor,
      anchorRadiusKm: 3,
    );

    expect(results.any((r) => r.place.id == anchor.id), isFalse);
    expect(results, isNotEmpty);
    // 경복궁(혼잡)보다 한산한 대안이 우선 제시된다.
    expect(results.first.place.crowdScore, lessThan(anchor.crowdScore!));
    // 반경 밖 장소는 들어오지 않는다.
    expect(results.any((r) => r.place.id == -13), isFalse);
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
  test('missing API facts do not become fabricated recommendation reasons', () {
    final place = Place.fromJson({'id': 42, 'name': 'Unknown place'});
    expect(place.crowdScore, isNull);
    expect(place.mainCategory, isNull);
    expect(place.latitude, isNull);
    final result = engine
        .recommend(places: [place], preference: const UserPreference()).single;
    expect(result.score, 0);
    expect(result.reasons, isEmpty);
  });

  test('sample and stale crowds cannot claim current quietness', () {
    final places = [
      const Place(id: 1, name: 'Sample', crowdScore: 0, isDemo: true),
      Place(
          id: 2,
          name: 'Stale',
          crowdScore: 0,
          observedAt: DateTime.now().subtract(const Duration(hours: 2))),
    ];
    final results =
        engine.recommend(places: places, preference: const UserPreference());
    expect(results.every((r) => r.score == 0 && r.reasons.isEmpty), isTrue);
  });

  test('nearby alternatives require coordinates for both places', () {
    final results = engine.recommend(
      places: const [Place(id: 1, name: 'Missing coordinates')],
      preference: const UserPreference(),
      anchor:
          const Place(id: 2, name: 'Anchor', latitude: 37.5, longitude: 127),
    );
    expect(results, isEmpty);
  });
}
