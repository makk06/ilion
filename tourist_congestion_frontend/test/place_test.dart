import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/place_service.dart';

void main() {
  test('missing crowd remains unknown; no invented rating or predictions', () {
    final p = Place.fromJson({
      'id': 1,
      'name': '제주 관광지',
      'latitude': 33.4,
      'longitude': 126.5,
      'latest_crowd': null
    });
    expect(p.crowdLevel, isNull);
    expect(p.crowdText, '정보 없음');
    expect(p.rating, isNull);
    expect(p.observedAt, isNull);
    expect(p.hasCoordinates, isTrue);
  });
  test(
      'observation provenance freshness and development sample survive parsing',
      () {
    final p = Place.fromJson({
      'id': 2,
      'name': '공원',
      'latest_crowd': {
        'level': 'relaxed',
        'source': 'seoul',
        'area_name': '구역',
        'observed_at':
            DateTime.now().subtract(const Duration(hours: 2)).toIso8601String(),
        'is_replaced': true,
        'is_demo': true
      }
    });
    expect(p.crowdLevel, CrowdLevel.low);
    expect(p.isStale, isTrue);
    expect(p.isReplaced, isTrue);
    expect(p.isDemo, isTrue);
    expect(p.crowdArea, '구역');
  });
  test('nearby transmits coordinates filter pagination and parses distance',
      () async {
    final previous = ApiClient.instance;
    addTearDown(() => ApiClient.instance = previous);
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      expect(request.url.path, '/api/places/nearby');
      expect(request.url.queryParameters['crowd_level'], 'relaxed');
      expect(request.url.queryParameters['latitude'], '37.5');
      expect(request.url.queryParameters['page'], '2');
      return http.Response(
          jsonEncode({
            'success': true,
            'data': {
              'items': [
                {'id': 3, 'name': '공원', 'distance_km': 1.234}
              ],
              'pagination': {'page': 2, 'total_pages': 3}
            }
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
    final result = await PlaceService.instance
        .nearby(latitude: 37.5, longitude: 127, crowdLevel: 'relaxed', page: 2);
    expect(result.hasMore, isTrue);
    expect(result.items.single.distance, '직선 1.2km');
  });
}
