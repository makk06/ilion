import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/screens/saved_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';

void main() {
  void feed(List<Map<String, dynamic>> items) {
    AppSession.instance = AppSession();
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      return http.Response(
          jsonEncode({
            'success': true,
            'data': {'items': items}
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
  }

  testWidgets('photo filtering and rating sort affect the real review list',
      (tester) async {
    tester.view.physicalSize = const Size(600, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    feed([
      {
        'id': 1,
        'place_name': '장소',
        'author_nickname': '하나',
        'text': '사진 없는 최근 후기',
        'rating': 3,
        'created_at': '2026-09-10T12:00:00Z',
        'like_count': 0,
      },
      {
        'id': 2,
        'place_name': '장소',
        'author_nickname': '둘',
        'text': '사진 있는 좋은 후기',
        'rating': 5,
        'created_at': '2026-09-09T12:00:00Z',
        'like_count': 3,
        'photo_url': 'https://example.test/review.jpg',
      },
    ]);
    await tester.pumpWidget(const MaterialApp(home: SavedScreen()));
    await tester.pumpAndSettle();
    expect(find.text('4.0'), findsOneWidget);
    expect(tester.getTopLeft(find.text('사진 없는 최근 후기')).dy,
        lessThan(tester.getTopLeft(find.text('사진 있는 좋은 후기')).dy));
    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('높은 평점순').last);
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(find.text('사진 있는 좋은 후기')).dy,
        lessThan(tester.getTopLeft(find.text('사진 없는 최근 후기')).dy));
    await tester.tap(find.text('사진 후기만'));
    await tester.pumpAndSettle();
    expect(find.text('사진 있는 좋은 후기'), findsOneWidget);
    expect(find.text('사진 없는 최근 후기'), findsNothing);
    await tester.tap(find.text('사진 후기만'));
    await tester.pumpAndSettle();
    expect(find.text('사진 없는 최근 후기'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('empty feed does not fabricate an average rating',
      (tester) async {
    feed([]);
    await tester.pumpWidget(const MaterialApp(home: SavedScreen()));
    await tester.pumpAndSettle();
    expect(find.text('0.0'), findsNothing);
    expect(find.text('5.0'), findsNothing);
    expect(find.text('4.0'), findsNothing);
    expect(find.textContaining('후기가 없'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
