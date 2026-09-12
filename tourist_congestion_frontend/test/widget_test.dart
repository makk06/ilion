import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/app.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';
import 'package:tourist_congestion_frontend/src/widgets/place_map.dart';

final _place = <String, dynamic>{
  'id': 1,
  'name': '테스트 관광지',
  'category': '자연',
  'address': '제주',
  'latitude': 33.4,
  'longitude': 126.9,
  'image_url': null,
  'latest_crowd': null,
  'avg_rating': null,
  'info': {'description': '실제 응답 형식의 장소 설명', 'opening_hours': '09:00~18:00'},
};

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      dynamic data;
      switch (request.url.path) {
        case '/api/places':
          data = {
            'items': request.url.queryParameters['keyword'] == '없는장소'
                ? []
                : [_place],
            'pagination': {'page': 1, 'total_pages': 1}
          };
        case '/api/places/1':
          data = _place;
        case '/api/places/nearby':
          data = {
            'items': [
              {..._place, 'id': 2, 'name': '가까운 관광지', 'distance_km': 1.2}
            ],
            'pagination': {'page': 1, 'total_pages': 1}
          };
        case '/api/reviews':
        case '/api/companions':
          data = {'items': []};
        default:
          return http.Response(
              '{"success":false,"message":"Unexpected route"}', 404);
      }
      return http.Response(jsonEncode({'success': true, 'data': data}), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
    AppSession.instance = AppSession();
  });

  Future<void> enter(WidgetTester tester) async {
    await tester.pumpWidget(const CrowdTripApp());
    await tester.pumpAndSettle();
    await tester.tap(find.text('시작하기'));
    await tester.pumpAndSettle();
  }

  testWidgets('onboarding persists and visible navigation opens all tabs',
      (tester) async {
    await enter(tester);
    await tester.tap(find.text('리스트'));
    await tester.pumpAndSettle();
    expect(find.text('테스트 관광지'), findsOneWidget);
    expect(
        (await SharedPreferences.getInstance()).getBool('onboarding_complete'),
        true);
    await tester.tap(find.bySemanticsLabel('동행'));
    await tester.pumpAndSettle();
    expect(find.text('그대도 이리온'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('후기'));
    await tester.pumpAndSettle();
    expect(find.text('여행 후기'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('마이'));
    await tester.pumpAndSettle();
    expect(find.text('마이페이지'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('home starts with inline map and top-left map list switch',
      (tester) async {
    tester.view.physicalSize = const Size(390, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await enter(tester);
    expect(find.byType(PlacesMap), findsOneWidget);
    final switchFinder = find.byType(SegmentedButton<bool>);
    final searchFinder = find.byType(TextField).first;
    expect(tester.getTopLeft(switchFinder).dy,
        lessThan(tester.getTopLeft(searchFinder).dy));
    expect(tester.getTopLeft(switchFinder).dx,
        closeTo(tester.getTopLeft(searchFinder).dx, 1));
    await tester.tap(find.text('리스트'));
    await tester.pumpAndSettle();
    expect(find.byType(PlacesMap), findsNothing);
    expect(find.text('테스트 관광지'), findsOneWidget);
    await tester.tap(find.text('지도'));
    await tester.pumpAndSettle();
    expect(find.byType(PlacesMap), findsOneWidget);
    expect(find.text('테스트 관광지'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('existing account enters actual authentication screen',
      (tester) async {
    await tester.pumpWidget(const CrowdTripApp());
    await tester.pumpAndSettle();
    await tester.tap(find.text('이미 계정이 있어요'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextFormField, '이메일'), findsOneWidget);
    expect(find.widgetWithText(TextFormField, '비밀번호'), findsOneWidget);
    expect(find.text('테스트 관광지'), findsNothing);
  });

  testWidgets(
      'detail receives place and does not fabricate congestion or rating',
      (tester) async {
    await enter(tester);
    await tester.tap(find.text('리스트'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('테스트 관광지'));
    await tester.pumpAndSettle();
    expect(find.text('정보 없음'), findsOneWidget);
    expect(find.textContaining('20분'), findsNothing);
    expect(find.textContaining('4.6'), findsNothing);
    await tester.scrollUntilVisible(find.text('이리ON, 비슷한 곳 보기'), 250);
    await tester
        .ensureVisible(find.widgetWithText(OutlinedButton, '이리ON, 비슷한 곳 보기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('이리ON, 비슷한 곳 보기'));
    await tester.pumpAndSettle();
    expect(find.text('가까운 관광지'), findsOneWidget);
    expect(find.textContaining('직선 1.2km'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('search uses API filter and displays honest empty state',
      (tester) async {
    await enter(tester);
    await tester.enterText(find.byType(TextField).first, '없는장소');
    await tester.tap(find.byTooltip('검색'));
    await tester.pumpAndSettle();
    expect(find.text('테스트 관광지'), findsNothing);
    expect(find.textContaining('조건에 맞는 장소'), findsOneWidget);
  });

  testWidgets('completed onboarding is not shown on next launch',
      (tester) async {
    SharedPreferences.setMockInitialValues({'onboarding_complete': true});
    await tester.pumpWidget(const CrowdTripApp());
    await tester.pumpAndSettle();
    expect(find.text('시작하기'), findsNothing);
    await tester.tap(find.text('리스트'));
    await tester.pumpAndSettle();
    expect(find.text('테스트 관광지'), findsOneWidget);
  });
}
