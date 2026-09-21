import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/screens/home_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/map_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/place_location.dart';

void main() {
  test('location service rejects calls before contacting the platform',
      () async {
    expect(deviceLocationEnabled, isFalse);
    // No platform plugin is installed in this test. A platform call would throw
    // MissingPluginException instead of this policy error.
    await expectLater(
        locateUser(),
        throwsA(isA<StateError>().having(
            (error) => error.message, 'message', contains('지역을 직접 선택'))));
  });

  for (final size in [const Size(390, 844), const Size(1440, 1000)]) {
    testWidgets('home hides GPS and still accepts a manual region at $size',
        (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final requests = <Uri>[];
      ApiClient.instance = ApiClient(client: MockClient((request) async {
        requests.add(request.url);
        final data = request.url.path == '/api/places/regions'
            ? {
                'items': [
                  {'name': '서울특별시', 'path': '서울특별시', 'children': []}
                ]
              }
            : {
                'items': [],
                'pagination': {'page': 1, 'total_pages': 1}
              };
        return http.Response(jsonEncode({'success': true, 'data': data}), 200,
            headers: {'content-type': 'application/json; charset=utf-8'});
      }));
      await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
      await tester.pumpAndSettle();
      expect(find.text('내 주변 10km'), findsNothing);
      expect(find.byIcon(Icons.my_location), findsNothing);
      await tester.tap(find.widgetWithText(OutlinedButton, '전국'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ListTile, '서울특별시'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('서울특별시 선택'));
      await tester.pumpAndSettle();
      expect(
          requests.any((uri) => uri.queryParameters['region_path'] == '서울특별시'),
          isTrue);
      expect(requests.any((uri) => uri.path.endsWith('/nearby')), isFalse);
      expect(
          requests.any((uri) =>
              uri.queryParameters.containsKey('latitude') ||
              uri.queryParameters.containsKey('longitude')),
          isFalse);
      expect(tester.takeException(), isNull);
    });

    testWidgets('map hides current device location at $size', (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(const MaterialApp(home: MapScreen(places: [])));
      await tester.pumpAndSettle();
      expect(find.byTooltip('현재 위치'), findsNothing);
      expect(find.byIcon(Icons.my_location), findsNothing);
      expect(find.text('지도 탐색'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}
