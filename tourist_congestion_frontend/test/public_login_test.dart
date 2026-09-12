import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/screens/auth_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/recommend_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/saved_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';

void main() {
  late List<http.Request> requests;
  setUp(() {
    requests = [];
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      requests.add(request);
      final items = request.url.path.endsWith('/reviews')
          ? [
              {
                'id': 1,
                'place_id': 3,
                'place_name': '공개 장소',
                'author_nickname': '방문자',
                'text': '로그인 없이 읽는 후기',
                'rating': 4,
                'created_at': '2026-09-10',
                'like_count': 2,
                'is_liked': false,
                'is_mine': false
              }
            ]
          : [
              {
                'id': 2,
                'place_name': '공개 장소',
                'title': '공개 동행 모집',
                'date': '2099-10-10',
                'text': '함께 여행해요',
                'author_nickname': '여행자',
                'member_count': 1,
                'capacity': 3
              }
            ];
      return http.Response(
          jsonEncode({
            'success': true,
            'data': {'items': items}
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
    AppSession.instance = AppSession();
  });

  testWidgets('guest reads reviews and writing opens login without posting',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ReviewFeed()));
    await tester.pumpAndSettle();
    expect(find.byType(AuthScreen), findsNothing);
    expect(find.text('로그인 없이 읽는 후기'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, '후기 작성'));
    await tester.pumpAndSettle();
    expect(find.byType(AuthScreen), findsOneWidget);
    expect(requests.every((r) => r.method == 'GET'), isTrue);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.byType(ReviewFeed), findsOneWidget);
    expect(requests.every((r) => r.method == 'GET'), isTrue);
  });

  testWidgets('guest helpful action opens login before mutation',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ReviewFeed()));
    await tester.pumpAndSettle();
    final helpful = find.widgetWithText(OutlinedButton, '도움돼요 2');
    await tester.ensureVisible(helpful);
    await tester.tap(helpful);
    await tester.pumpAndSettle();
    expect(find.byType(AuthScreen), findsOneWidget);
    expect(requests.every((r) => r.method == 'GET'), isTrue);
  });

  testWidgets('guest reads companions and recruitment opens login',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: RecommendScreen()));
    await tester.pumpAndSettle();
    expect(find.text('공개 동행 모집'), findsOneWidget);
    expect(find.byType(AuthScreen), findsNothing);
    await tester.tap(find.byTooltip('동행 모집 작성'));
    await tester.pumpAndSettle();
    expect(find.byType(AuthScreen), findsOneWidget);
    expect(requests.every((r) => r.method == 'GET'), isTrue);
  });
}
