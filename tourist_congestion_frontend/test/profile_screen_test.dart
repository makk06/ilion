import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/screens/auth_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/place_detail_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/profile_places_screens.dart';
import 'package:tourist_congestion_frontend/src/screens/profile_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';

void main() {
  Future<void> open(WidgetTester tester, {bool recent = false}) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    FlutterSecureStorage.setMockInitialValues({});
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      expect(request.url.path, '/api/places/7');
      return http.Response(
          jsonEncode({
            'success': true,
            'data': {'id': 7, 'name': '실제로 본 장소', 'category': '자연'}
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
    AppSession.instance = AppSession();
    await AppSession.instance.restore();
    if (recent) await AppSession.instance.recordRecent(7);
    await tester.pumpWidget(const MaterialApp(home: ProfileScreen()));
    await tester.pumpAndSettle();
  }

  testWidgets('guest profile shortcuts open saved places and plans directly',
      (tester) async {
    await open(tester);
    await tester.tap(find.text('저장 장소'));
    await tester.pumpAndSettle();
    expect(find.byType(SavedPlacesScreen), findsOneWidget);
    expect(find.byType(AuthScreen), findsNothing);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('여행 일정'));
    await tester.pumpAndSettle();
    expect(find.byType(TravelPlansScreen), findsOneWidget);
    expect(find.byType(AuthScreen), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('guest personal reviews shortcut opens authentication',
      (tester) async {
    await open(tester);
    await tester.tap(find.text('내 후기'));
    await tester.pumpAndSettle();
    expect(find.byType(AuthScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('recent strip uses local history and opens its actual place',
      (tester) async {
    await open(tester, recent: true);
    expect(find.text('실제로 본 장소'), findsOneWidget);
    expect(
        find.byWidgetPredicate((widget) =>
            widget is ListView && widget.scrollDirection == Axis.horizontal),
        findsOneWidget);
    await tester.tap(find.text('실제로 본 장소'));
    await tester.pumpAndSettle();
    expect(find.byType(PlaceDetailScreen), findsOneWidget);
    expect(
        tester
            .widget<PlaceDetailScreen>(find.byType(PlaceDetailScreen))
            .place
            .id,
        7);
    expect(find.byType(AuthScreen), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('empty guest profile has no invented recent places or counts',
      (tester) async {
    await open(tester);
    expect(find.text('관심 있는 장소를 둘러보면 여기에 모아드려요.'), findsOneWidget);
    expect(find.text('실제로 본 장소'), findsNothing);
    expect(find.text('0'), findsNothing);
    expect(find.text('0개'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
