import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tourist_congestion_frontend/src/screens/auth_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';

http.Response _ok(Object data) =>
    http.Response(jsonEncode({'success': true, 'data': data}), 200,
        headers: {'content-type': 'application/json; charset=utf-8'});

void main() {
  late List<Map<String, dynamic>> signupBodies;

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    signupBodies = [];
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      switch (request.url.path) {
        case '/api/auth/signup':
          signupBodies.add(jsonDecode(request.body) as Map<String, dynamic>);
          return _ok({'access_token': 'access', 'refresh_token': 'refresh'});
        case '/api/me':
          return _ok({'id': 1, 'nickname': '새여행자'});
        case '/api/auth/nickname/random':
          return _ok({'nickname': '새여행자'});
      }
      return _ok({'items': []});
    }));
    AppSession.instance = AppSession();
  });

  Future<void> tapVisible(WidgetTester tester, Finder finder) async {
    // 동의 항목이 늘어 가입 버튼이 첫 화면 밖에 있으면 목록을 내려서 찾는다.
    if (finder.evaluate().isEmpty) {
      await tester.scrollUntilVisible(finder, 200,
          scrollable: find.byType(Scrollable).first);
    }
    await tester.ensureVisible(finder);
    await tester.pumpAndSettle();
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  Future<void> openSignup(WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Builder(
            builder: (context) => TextButton(
                onPressed: () => ensureSignedIn(context),
                child: const Text('open')))));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tapVisible(tester, find.text('계정 만들기'));
    await tester.enterText(
        find.widgetWithText(TextFormField, '이메일'), 'new@example.com');
    await tester.enterText(find.byKey(const ValueKey('auth-nickname')), '새여행자');
    await tester.enterText(
        find.byKey(const ValueKey('auth-password')), 'a-strong-password-123');
  }

  testWidgets('signup is sent only after every required consent is checked',
      (tester) async {
    await openSignup(tester);

    await tapVisible(tester, find.widgetWithText(FilledButton, '회원가입'));
    expect(find.text('필수 항목에 모두 동의해 주세요.'), findsOneWidget);
    expect(signupBodies, isEmpty);

    await tapVisible(tester, find.byKey(const ValueKey('auth-consent-age')));
    await tapVisible(tester, find.byKey(const ValueKey('auth-consent-terms')));
    await tapVisible(tester, find.widgetWithText(FilledButton, '회원가입'));
    expect(signupBodies, isEmpty, reason: '개인정보 수집·이용 동의 없이는 가입하지 않는다');

    await tapVisible(
        tester, find.byKey(const ValueKey('auth-consent-privacy')));
    await tapVisible(tester, find.widgetWithText(FilledButton, '회원가입'));
    expect(signupBodies, hasLength(1));
    expect(signupBodies.single['age_over_14'], true);
    expect(signupBodies.single['agree_terms'], true);
    expect(signupBodies.single['agree_privacy'], true);
  });

  testWidgets('all-agree checks every required consent at once',
      (tester) async {
    await openSignup(tester);

    await tapVisible(tester, find.byKey(const ValueKey('auth-consent-all')));
    await tapVisible(tester, find.widgetWithText(FilledButton, '회원가입'));

    expect(signupBodies, hasLength(1));
    expect(signupBodies.single['agree_privacy'], true);
  });

  testWidgets('privacy notice shows collected items in the app and can agree',
      (tester) async {
    await openSignup(tester);

    final privacyTile = find.byKey(const ValueKey('auth-consent-privacy'));
    await tapVisible(
        tester, find.descendant(of: privacyTile, matching: find.text('보기')));
    expect(find.text('개인정보 수집·이용 동의'), findsOneWidget);
    expect(find.textContaining('이메일, 비밀번호, 닉네임'), findsOneWidget);
    expect(find.textContaining('거부하면 회원가입을 할 수 없습니다'), findsOneWidget);

    await tapVisible(
        tester, find.byKey(const ValueKey('privacy-consent-agree')));
    final tile = tester.widget<CheckboxListTile>(find.descendant(
        of: privacyTile, matching: find.byType(CheckboxListTile)));
    expect(tile.value, true);
  });
}
