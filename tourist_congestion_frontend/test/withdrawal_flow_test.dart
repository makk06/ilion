import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/screens/auth_screen.dart';
import 'package:tourist_congestion_frontend/src/screens/withdrawal_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';

http.Response ok([Object data = const {}]) =>
    http.Response(jsonEncode({'success': true, 'data': data}), 200);

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  Future<void> open(WidgetTester tester, Widget screen, MockClient client,
      {bool signedIn = true}) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    ApiClient.instance = ApiClient(client: client);
    if (signedIn) ApiClient.instance.accessToken = 'access';
    AppSession.instance = AppSession();
    AppSession.instance.profile = {
      'email': 'test@example.com',
      'provider': 'email'
    };
    await tester.pumpWidget(MaterialApp(
        home: Builder(
      builder: (context) => Scaffold(
          body: TextButton(
        onPressed: () => Navigator.push(
            context, MaterialPageRoute<void>(builder: (_) => screen)),
        child: const Text('열기'),
      )),
    )));
    await tester.tap(find.text('열기'));
    await tester.pumpAndSettle();
  }

  Future<void> submitWithdrawal(WidgetTester tester) async {
    await tester.enterText(find.byType(TextField), 'correct-password');
    final submit = find.text('본인 확인 후 탈퇴 신청');
    await tester.ensureVisible(submit);
    await tester.tap(submit);
    await tester.pump();
  }

  testWidgets('backing out never submits withdrawal', (tester) async {
    var calls = 0;
    await open(tester, const WithdrawalScreen(), MockClient((r) async {
      calls++;
      return ok();
    }));
    expect(find.textContaining('계정 최종 파기 시 삭제됩니다'), findsOneWidget);
    expect(find.textContaining('후기·사진과 일부 활동 데이터는'), findsNothing);
    await tester.ensureVisible(find.text('돌아가기'));
    await tester.tap(find.text('돌아가기'));
    await tester.pumpAndSettle();
    expect(calls, 0);
    expect(AppSession.instance.isAuthenticated, true);
  });

  testWidgets('confirmed withdrawal uses credential POST and clears session',
      (tester) async {
    await open(tester, const WithdrawalScreen(), MockClient((r) async {
      expect(r.method, 'POST');
      expect(r.url.path, '/api/me/withdraw');
      expect(jsonDecode(r.body)['password'], 'correct-password');
      return ok({'purge_at': '2026-10-01T12:00:00Z'});
    }));
    await submitWithdrawal(tester);
    await tester.pumpAndSettle();
    expect(AppSession.instance.isAuthenticated, false);
    expect(AppSession.instance.profile, isNull);
    expect(find.byType(WithdrawalScreen), findsNothing);
    expect(find.textContaining('탈퇴가 접수됐어요'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('server failure preserves session and allows retry',
      (tester) async {
    await open(
        tester,
        const WithdrawalScreen(),
        MockClient((r) async => http.Response(
            '{"success":false,"message":"verification failed"}', 400)));
    await submitWithdrawal(tester);
    await tester.pumpAndSettle();
    expect(AppSession.instance.isAuthenticated, true);
    expect(find.text('verification failed'), findsOneWidget);
    expect(find.text('본인 확인 후 탈퇴 신청'), findsOneWidget);
  });

  testWidgets('in flight submission cannot be duplicated', (tester) async {
    final pending = Completer<http.Response>();
    var calls = 0;
    await open(tester, const WithdrawalScreen(), MockClient((r) {
      calls++;
      return pending.future;
    }));
    await submitWithdrawal(tester);
    await tester.tap(find.text('탈퇴 접수 중…'));
    await tester.pump();
    expect(calls, 1);
    pending.complete(ok());
    await tester.pumpAndSettle();
  });

  for (final restore in [false, true]) {
    testWidgets('pending login restores only with explicit consent: $restore',
        (tester) async {
      var cancelled = 0;
      await open(tester, const AuthScreen(), MockClient((r) async {
        if (r.url.path == '/api/auth/login') {
          return http.Response(
              jsonEncode({
                'success': false,
                'message': 'pending',
                'data': {
                  'code': 'withdrawal_pending',
                  'purge_at': '2026-10-01T12:00:00Z'
                },
              }),
              403);
        }
        if (r.url.path == '/api/me/withdraw/cancel') {
          cancelled++;
          expect(jsonDecode(r.body)['password'], 'correct-password');
          return ok(
              {'access_token': 'new-access', 'refresh_token': 'new-refresh'});
        }
        if (r.url.path == '/api/me') return ok({'nickname': 'restored'});
        if (r.url.path == '/api/favorites') return ok({'place_ids': []});
        throw StateError('Unexpected route ${r.url.path}');
      }), signedIn: false);
      await tester.enterText(
          find.byType(TextFormField).at(0), 'test@example.com');
      await tester.enterText(
          find.byType(TextFormField).at(1), 'correct-password');
      final submit = find.widgetWithText(FilledButton, '로그인');
      await tester.ensureVisible(submit);
      await tester.tap(submit);
      await tester.pumpAndSettle();
      expect(find.text('탈퇴 예정 계정'), findsOneWidget);
      await tester.tap(find.text(restore ? '탈퇴 취소하고 로그인' : '탈퇴 유지'));
      await tester.pumpAndSettle();
      expect(cancelled, restore ? 1 : 0);
      expect(AppSession.instance.isAuthenticated, restore);
      expect(tester.takeException(), isNull);
    });
  }

  for (final path in ['/me/withdraw', '/auth/password']) {
    test('expired access refreshes for protected operation $path', () async {
      var calls = 0;
      var refreshes = 0;
      final api = ApiClient(client: MockClient((r) async {
        calls++;
        if (calls == 1) return http.Response('{"detail":"expired"}', 401);
        expect(r.headers['Authorization'], 'Bearer fresh');
        return ok();
      }));
      api.accessToken = 'expired';
      api.refreshAccessToken = () async {
        refreshes++;
        api.accessToken = 'fresh';
        return true;
      };
      await api.post(path, body: {'password': 'correct'});
      expect(calls, 2);
      expect(refreshes, 1);
    });
  }

  testWidgets('desktop withdrawal remains readable and submits',
      (tester) async {
    await open(tester, const WithdrawalScreen(), MockClient((r) async => ok()));
    tester.view.physicalSize = const Size(1440, 1000);
    await tester.pumpAndSettle();
    expect(find.textContaining('7일 후 계정 파기 대상이 됩니다'), findsOneWidget);
    expect(find.textContaining('계정 최종 파기 시 삭제됩니다'), findsOneWidget);
    await submitWithdrawal(tester);
    await tester.pumpAndSettle();
    expect(AppSession.instance.isAuthenticated, false);
    expect(tester.takeException(), isNull);
  });

  testWidgets('recovery failure is shown without creating a session',
      (tester) async {
    await open(tester, const AuthScreen(), MockClient((r) async {
      if (r.url.path == '/api/auth/login') {
        return http.Response(
            jsonEncode({
              'success': false,
              'message': 'pending',
              'data': {
                'code': 'withdrawal_pending',
                'purge_at': '2026-10-01T12:00:00Z'
              },
            }),
            403);
      }
      expect(r.url.path, '/api/me/withdraw/cancel');
      return http.Response(
          '{"success":false,"message":"recovery deadline passed"}', 409);
    }), signedIn: false);
    await tester.enterText(
        find.byType(TextFormField).at(0), 'test@example.com');
    await tester.enterText(
        find.byType(TextFormField).at(1), 'correct-password');
    final submit = find.widgetWithText(FilledButton, '로그인');
    await tester.ensureVisible(submit);
    await tester.tap(submit);
    await tester.pumpAndSettle();
    await tester.tap(find.text('탈퇴 취소하고 로그인'));
    await tester.pumpAndSettle();
    expect(find.text('recovery deadline passed'), findsOneWidget);
    expect(AppSession.instance.isAuthenticated, false);
  });
}
