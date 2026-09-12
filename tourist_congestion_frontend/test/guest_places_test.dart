import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/screens/auth_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/place_detail_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/profile_places_screens.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';

void main() {
  final requests = <String>[];
  setUp(() async {
    requests.clear();
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      requests.add('${request.method} ${request.url.path}');
      if (request.url.path == '/api/places/7') {
        return http.Response(
            jsonEncode({
              'success': true,
              'data': {'id': 7, 'name': '게스트가 본 장소', 'category': '자연'}
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'});
      }
      return http.Response(
          '{"success":false,"message":"Unexpected route"}', 404);
    }));
    AppSession.instance = AppSession();
    await AppSession.instance.restore();
  });

  testWidgets('guest detail records a recent place and saves without login',
      (tester) async {
    AppSession.instance = AppSession();
    await AppSession.instance.restore();
    await tester.pumpWidget(const MaterialApp(
        home: PlaceDetailScreen(place: Place(id: 7, name: '게스트가 본 장소'))));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('즐겨찾기 저장'));
    await tester.pumpAndSettle();
    expect(AppSession.instance.isAuthenticated, isFalse);
    expect(AppSession.instance.favoriteIds, contains(7));
    expect(find.byTooltip('즐겨찾기 해제'), findsOneWidget);
    expect(find.byType(AuthScreen), findsNothing);
    await tester.pumpWidget(const MaterialApp(home: RecentPlacesScreen()));
    await tester.pumpAndSettle();
    expect(find.text('게스트가 본 장소'), findsOneWidget);
    expect(find.byType(AuthScreen), findsNothing);
    expect(requests.every((request) => request == 'GET /api/places/7'), isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('guest saved places survive session recreation and need no login',
      (tester) async {
    AppSession.instance = AppSession();
    await AppSession.instance.restore();
    await AppSession.instance.toggleFavorite(7);
    AppSession.instance = AppSession();
    await AppSession.instance.restore();
    await tester.pumpWidget(const MaterialApp(home: SavedPlacesScreen()));
    await tester.pumpAndSettle();
    expect(find.text('게스트가 본 장소'), findsOneWidget);
    expect(find.byType(AuthScreen), findsNothing);
    expect(AppSession.instance.favoriteIds, contains(7));
    expect(tester.takeException(), isNull);
  });

  testWidgets('guest can open travel plans and start a new plan',
      (tester) async {
    AppSession.instance = AppSession();
    await AppSession.instance.restore();
    await tester.pumpWidget(const MaterialApp(home: TravelPlansScreen()));
    await tester.pumpAndSettle();
    expect(find.byType(AuthScreen), findsNothing);
    expect(find.textContaining('로그인'), findsNothing);
    expect(find.byType(TravelPlansScreen), findsOneWidget);
    await tester.tap(find.text('새 일정 만들기'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, '일정 제목'), findsOneWidget);
    expect(find.widgetWithText(TextField, '방문 장소'), findsOneWidget);
    expect(find.text('일정 저장'), findsOneWidget);
    expect(find.byType(AuthScreen), findsNothing);
    expect(requests, isEmpty);
    expect(tester.takeException(), isNull);
  });
}
