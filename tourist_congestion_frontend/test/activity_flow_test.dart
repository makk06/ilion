import 'package:tourist_congestion_frontend/src/services/activity_changes.dart';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';
import 'package:tourist_congestion_frontend/src/screens/review_form_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/saved_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/companion_detail_screen.dart';

http.Response response(dynamic data, {int status = 200}) => http.Response(
    jsonEncode({'success': status == 200, 'data': data, 'message': '연결 실패'}),
    status,
    headers: {'content-type': 'application/json; charset=utf-8'});
void main() {
  setUp(() => AppSession.instance = AppSession());
  testWidgets(
      'review retry fetches real content and does not show invented reviews',
      (tester) async {
    var calls = 0;
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      calls++;
      if (calls == 1) return response(null, status: 503);
      return response({
        'items': [
          {
            'id': 1,
            'place_id': 3,
            'place_name': '실제 장소',
            'author_nickname': '작성자',
            'text': '서버에 저장된 후기',
            'rating': 4,
            'created_at': '2026-09-10',
            'like_count': 2,
            'is_liked': false,
            'is_mine': false
          }
        ]
      });
    }));
    AppSession.instance = AppSession();
    await tester.pumpWidget(const MaterialApp(home: SavedScreen()));
    await tester.pumpAndSettle();
    expect(find.text('다시 시도'), findsOneWidget);
    expect(find.text('안유진'), findsNothing);
    await tester.tap(find.text('다시 시도'));
    await tester.pumpAndSettle();
    expect(find.text('서버에 저장된 후기'), findsOneWidget);
    expect(calls, 2);
  });
  testWidgets(
      'review creation sends selected place and text to backend then returns',
      (tester) async {
    Map<String, dynamic>? submitted;
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      if (request.method == 'POST') {
        submitted = jsonDecode(request.body) as Map<String, dynamic>;
        return response({
          'review': {'id': 8},
          'points_awarded': 50
        });
      }
      return response({'nickname': '테스트'});
    }));
    ApiClient.instance.accessToken = 'test';
    AppSession.instance = AppSession();
    await tester.pumpWidget(MaterialApp(
        home: Builder(
            builder: (c) => Scaffold(
                body: TextButton(
                    onPressed: () => Navigator.push(
                        c,
                        MaterialPageRoute<bool>(
                            builder: (_) => const ReviewFormScreen(
                                placeId: 7, placeName: '선택 장소'))),
                    child: const Text('작성 열기'))))));
    await tester.tap(find.text('작성 열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('4점'));
    await tester.enterText(find.byType(TextField), '실제 등록 내용');
    await tester.ensureVisible(find.widgetWithText(FilledButton, '후기 등록'));
    await tester.tap(find.widgetWithText(FilledButton, '후기 등록'));
    await tester.pumpAndSettle();
    expect(submitted?['place_id'], 7);
    expect(submitted?['text'], '실제 등록 내용');
    expect(submitted?['rating'], 4);
    expect(find.text('작성 열기'), findsOneWidget);
  });
  testWidgets('failed review write remains on form and retains text',
      (tester) async {
    final ratings = <dynamic>[];
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      if (request.method == 'POST') {
        ratings.add((jsonDecode(request.body) as Map)['rating']);
      }
      return response(null, status: 500);
    }));
    ApiClient.instance.accessToken = 'test';
    AppSession.instance = AppSession();
    await tester.pumpWidget(
        const MaterialApp(home: ReviewFormScreen(placeId: 7, placeName: '장소')));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('3점'));
    await tester.enterText(find.byType(TextField), '잃으면 안 되는 내용');
    await tester.ensureVisible(find.widgetWithText(FilledButton, '후기 등록'));
    await tester.tap(find.widgetWithText(FilledButton, '후기 등록'));
    await tester.pumpAndSettle();
    expect(find.text('잃으면 안 되는 내용'), findsOneWidget);
    expect(find.byType(ReviewFormScreen), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, '후기 등록'));
    await tester.pumpAndSettle();
    expect(ratings, [3, 3]);
  });
  testWidgets('new review requires an explicit rating before making a request',
      (tester) async {
    var writes = 0;
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      if (request.method == 'POST') writes++;
      return response({});
    }));
    ApiClient.instance.accessToken = 'test';
    AppSession.instance = AppSession();
    await tester.pumpWidget(const MaterialApp(
        home: ReviewFormScreen(placeId: 7, placeName: '선택 장소')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '별점 없이 입력한 후기');
    await tester.ensureVisible(find.widgetWithText(FilledButton, '후기 등록'));
    await tester.tap(find.widgetWithText(FilledButton, '후기 등록'));
    await tester.pumpAndSettle();
    expect(writes, 0);
    expect(find.byType(ReviewFormScreen), findsOneWidget);
    expect(find.text('별점 없이 입력한 후기'), findsOneWidget);
  });
  testWidgets('review edit preserves the existing rating in PATCH payload',
      (tester) async {
    Map<String, dynamic>? patch;
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      if (request.method == 'PATCH') {
        patch = jsonDecode(request.body) as Map<String, dynamic>;
      }
      return response({});
    }));
    ApiClient.instance.accessToken = 'test';
    AppSession.instance = AppSession();
    await tester.pumpWidget(const MaterialApp(
        home: ReviewFormScreen(review: {
      'id': 9,
      'place_id': 7,
      'place_name': '선택 장소',
      'rating': 2,
      'text': '기존 후기',
    })));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '수정한 후기');
    await tester.ensureVisible(find.widgetWithText(FilledButton, '수정 완료'));
    await tester.tap(find.widgetWithText(FilledButton, '수정 완료'));
    await tester.pumpAndSettle();
    expect(patch, {'text': '수정한 후기', 'rating': 2});
  });
  testWidgets('mobile review form stays usable with keyboard open',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetViewInsets);
    Map<String, dynamic>? submitted;
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      if (request.method == 'POST') {
        submitted = jsonDecode(request.body) as Map<String, dynamic>;
      }
      return response(null, status: 500);
    }));
    ApiClient.instance.accessToken = 'test';
    AppSession.instance = AppSession();
    await tester.pumpWidget(const MaterialApp(
        home: ReviewFormScreen(placeId: 7, placeName: '선택 장소')));
    await tester.pumpAndSettle();
    tester.view.viewInsets = const FakeViewPadding(bottom: 300);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byTooltip('4점'));
    await tester.tap(find.byTooltip('4점'));
    final scrollable = find
        .descendant(
            of: find.byType(ListView), matching: find.byType(Scrollable))
        .first;
    await tester.scrollUntilVisible(find.byType(TextField), 150,
        scrollable: scrollable);
    await tester.ensureVisible(find.byType(TextField));
    await tester.enterText(find.byType(TextField), '키보드를 열고 작성한 후기');
    await tester.pumpAndSettle();
    final submit = find.widgetWithText(FilledButton, '후기 등록');
    expect(submit.hitTestable(), findsOneWidget);
    await tester.tap(submit);
    await tester.pumpAndSettle();
    expect(submitted?['rating'], 4);
    expect(submitted?['text'], '키보드를 열고 작성한 후기');
    expect(tester.takeException(), isNull);
  });
  testWidgets('companion join refreshes membership from server and can leave',
      (tester) async {
    var joined = false;
    final methods = <String>[];
    Map<String, dynamic> item() => {
          'id': 2,
          'place_id': 3,
          'place_name': '관광지',
          'author_nickname': '모집자',
          'title': '함께 여행',
          'text': '만날 장소 안내',
          'date': '2099-09-10',
          'member_count': joined ? 2 : 1,
          'capacity': 3,
          'is_joined': joined,
          'is_mine': false
        };
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      if (request.url.path.endsWith('/join')) {
        methods.add(request.method);
        joined = request.method == 'POST';
        return response(item());
      }
      return response({
        'items': [item()]
      });
    }));
    ApiClient.instance.accessToken = 'test';
    AppSession.instance = AppSession();
    await tester.pumpWidget(
        MaterialApp(home: CompanionDetailScreen(companion: item())));
    await tester.pumpAndSettle();
    await tester.tap(find.text('동행 신청하기'));
    await tester.pumpAndSettle();
    expect(find.text('2/3명'), findsOneWidget);
    await tester.tap(find.text('신청 취소'));
    await tester.pumpAndSettle();
    expect(find.text('1/3명'), findsOneWidget);
    expect(methods, ['POST', 'DELETE']);
  });
  testWidgets(
      'retained review feed refreshes after another route mutation and logout',
      (tester) async {
    var text = '원래 후기';
    ApiClient.instance = ApiClient(
        client: MockClient((request) async => response({
              'items': [
                {
                  'id': 1,
                  'place_name': '장소',
                  'author_nickname': '작성자',
                  'text': text,
                  'rating': 5,
                  'created_at': '오늘',
                  'like_count': 0,
                  'is_mine': ApiClient.instance.accessToken != null
                }
              ]
            })));
    ApiClient.instance.accessToken = 'test';
    AppSession.instance = AppSession();
    await tester.pumpWidget(const MaterialApp(home: SavedScreen()));
    await tester.pumpAndSettle();
    expect(find.text('원래 후기'), findsOneWidget);
    text = '다른 화면에서 수정됨';
    activityChanged();
    await tester.pumpAndSettle();
    expect(find.text('다른 화면에서 수정됨'), findsOneWidget);
    expect(find.text('원래 후기'), findsNothing);
    ApiClient.instance.accessToken = null;
    activityChanged();
    await tester.pumpAndSettle();
    expect(find.byType(PopupMenuButton<String>), findsNothing);
  });
}
