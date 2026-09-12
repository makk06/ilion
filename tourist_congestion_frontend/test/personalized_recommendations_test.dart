import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/screens/personalized_recommendations_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/place_detail_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';
import 'package:tourist_congestion_frontend/src/state/app_scope.dart';
import 'package:tourist_congestion_frontend/src/widgets/recommendation_card.dart';

void main() {
  testWidgets(
      'recommendations use API pages, category filtering and real detail route',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    FlutterSecureStorage.setMockInitialValues({});
    AppSession.instance = AppSession();
    await AppSession.instance.restore();
    final pages = <String>[];
    final place = {
      'id': 2,
      'name': 'API 문화관',
      'category': '문화시설',
      'address': '서울특별시 종로구'
    };
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      dynamic data;
      if (request.url.path.endsWith('/places/2')) {
        data = place;
      } else {
        expect(request.url.path, endsWith('/places'));
        final page = request.url.queryParameters['page']!;
        pages.add(page);
        data = {
          'items': page == '1'
              ? [
                  {'id': 1, 'name': 'API 관광지', 'category': '관광지'}
                ]
              : [place],
          'pagination': {'page': int.parse(page), 'total_pages': 2}
        };
      }
      return http.Response(jsonEncode({'success': true, 'data': data}), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
    await tester.pumpWidget(const AppScope(
        child: MaterialApp(home: PersonalizedRecommendationsScreen())));
    await tester.pumpAndSettle();
    expect(find.text('API 관광지'), findsOneWidget);
    await tester.tap(find.widgetWithText(ChoiceChip, '문화시설'));
    await tester.pumpAndSettle();
    expect(find.byType(RecommendationCard), findsNothing);
    await tester.tap(find.text('장소 더 불러오기'));
    await tester.pumpAndSettle();
    expect(pages, ['1', '2']);
    expect(find.text('API 문화관'), findsOneWidget);
    expect(find.text('장소 더 불러오기'), findsNothing);
    await tester.tap(find.text('API 문화관'));
    await tester.pumpAndSettle();
    expect(find.byType(PlaceDetailScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
