import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/screens/recommend_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';

void main() {
  testWidgets('date and capacity filters combine and reset on mobile',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final today = DateTime.now().toIso8601String().substring(0, 10);
    final tomorrow = DateTime.now()
        .add(const Duration(days: 1))
        .toIso8601String()
        .substring(0, 10);
    ApiClient.instance = ApiClient(
        client: MockClient((request) async => http.Response(
            jsonEncode({
              'success': true,
              'data': {
                'items': [
                  {
                    'id': 1,
                    'title': '오늘 여유',
                    'place_name': '경복궁',
                    'place_address': '서울특별시 종로구',
                    'text': '',
                    'author_nickname': '나',
                    'date': today,
                    'member_count': 1,
                    'capacity': 3
                  },
                  {
                    'id': 2,
                    'title': '오늘 마감',
                    'place_name': '수원',
                    'place_address': '경기도 수원시',
                    'text': '',
                    'author_nickname': '너',
                    'date': today,
                    'member_count': 3,
                    'capacity': 3
                  },
                  {
                    'id': 4,
                    'title': '일정 미정',
                    'place_name': '서울',
                    'text': '',
                    'author_nickname': '우리',
                    'date': null,
                    'time': null,
                    'member_count': 1,
                    'capacity': 3
                  },
                  {
                    'id': 3,
                    'title': '내일 여행',
                    'place_name': '제주',
                    'place_address': '제주특별자치도 제주시',
                    'text': '',
                    'author_nickname': '우리',
                    'date': tomorrow,
                    'member_count': 1,
                    'capacity': 3
                  }
                ]
              }
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'})));
    await tester.pumpWidget(const MaterialApp(home: RecommendScreen()));
    await tester.pumpAndSettle();
    expect(find.text('함께할 동행 4개'), findsOneWidget);
    await tester.tap(find.byTooltip('날짜 선택'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('오늘'));
    await tester.pumpAndSettle();
    expect(find.text('함께할 동행 2개'), findsOneWidget);
    await tester.tap(find.text('모집 중만'));
    await tester.pumpAndSettle();
    expect(find.text('함께할 동행 1개'), findsOneWidget);
    await tester.tap(find.text('초기화'));
    await tester.pumpAndSettle();
    expect(find.text('함께할 동행 4개'), findsOneWidget);
    await tester.tap(find.text('모집 중만'));
    await tester.pumpAndSettle();
    expect(find.text('함께할 동행 3개'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
