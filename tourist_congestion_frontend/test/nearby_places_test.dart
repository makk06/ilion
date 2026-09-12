import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/screens/nearby_places_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';

const _origin = Place(
    id: 1, name: '출발 장소', category: '자연', latitude: 33.4, longitude: 126.9);

http.Response _page(List<Map<String, dynamic>> items,
        {int page = 1, int totalPages = 1}) =>
    http.Response(
        jsonEncode({
          'success': true,
          'data': {
            'items': items,
            'pagination': {'page': page, 'total_pages': totalPages}
          }
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'});

void main() {
  testWidgets('empty nearby action clears both filters and fetches real places',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final queries = <Map<String, String>>[];
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      final query = request.url.queryParameters;
      queries.add(query);
      final unfiltered = (query['category'] ?? '').isEmpty &&
          (query['crowd_level'] ?? '').isEmpty;
      return _page(unfiltered
          ? [
              {
                'id': 2,
                'name': '실제 주변 장소',
                'category': '문화',
                'distance_km': 1.2
              }
            ]
          : []);
    }));
    await tester.pumpWidget(
        const MaterialApp(home: NearbyPlacesScreen(place: _origin)));
    await tester.pumpAndSettle();
    expect(queries.first['category'], '자연');
    await tester.tap(find.text('여유로운 곳'));
    await tester.pumpAndSettle();
    expect(queries.last['crowd_level'], 'relaxed');
    await tester.ensureVisible(find.text('주변 장소 전체 보기'));
    await tester.tap(find.text('주변 장소 전체 보기'));
    await tester.pumpAndSettle();
    expect(queries.last['category'] ?? '', '');
    expect(queries.last['crowd_level'] ?? '', '');
    expect(find.text('실제 주변 장소'), findsOneWidget);
    expect(find.textContaining('직선 1.2km'), findsOneWidget);
    expect(
        tester
            .widget<FilterChip>(find.widgetWithText(FilterChip, '같은 종류'))
            .selected,
        isFalse);
    expect(
        tester
            .widget<FilterChip>(find.widgetWithText(FilterChip, '여유로운 곳'))
            .selected,
        isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('empty current page retains filters while loading the next page',
      (tester) async {
    final pages = <String?>[];
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      final query = request.url.queryParameters;
      pages.add(query['page']);
      return query['page'] == '1'
          ? _page([
              {'id': 1, 'name': '출발 장소'}
            ], totalPages: 2)
          : _page([
              {'id': 2, 'name': '다음 페이지 장소'}
            ], page: 2, totalPages: 2);
    }));
    await tester.pumpWidget(
        const MaterialApp(home: NearbyPlacesScreen(place: _origin)));
    await tester.pumpAndSettle();
    expect(find.text('다음 장소도 살펴볼까요?'), findsOneWidget);
    expect(find.text('주변 장소 전체 보기'), findsNothing);
    await tester.ensureVisible(find.text('더 보기'));
    await tester.tap(find.text('더 보기'));
    await tester.pumpAndSettle();
    expect(pages, ['1', '2']);
    expect(find.text('다음 페이지 장소'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
