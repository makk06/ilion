import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));
  http.Response ok(dynamic data) =>
      http.Response(jsonEncode({'success': true, 'data': data}), 200);

  test('login restores tokens and favorites after session recreation',
      () async {
    final api = ApiClient(client: MockClient((r) async {
      return switch (r.url.path) {
        '/api/auth/login' =>
          ok({'access_token': 'access', 'refresh_token': 'refresh'}),
        '/api/me' => ok({'id': 1, 'nickname': 'tester'}),
        '/api/favorites' => ok({
            'place_ids': [7]
          }),
        _ => throw StateError('unexpected ${r.url}'),
      };
    }));
    final session = AppSession(api: api);
    await session.login('test@example.com', 'test password');
    expect(session.favoriteIds, {7});
    final restored = AppSession(api: api);
    await restored.restore();
    expect(restored.isAuthenticated, true);
    expect(restored.profile?['nickname'], 'tester');
    expect(restored.favoriteIds, {7});
  });

  test('failed favorite mutation does not report local success', () async {
    final api = ApiClient(
        client: MockClient((r) async =>
            http.Response('{"success":false,"message":"unavailable"}', 503)));
    api.accessToken = 'access';
    final session = AppSession(api: api);
    await expectLater(session.toggleFavorite(7), throwsA(isA<ApiException>()));
    expect(session.favoriteIds, isEmpty);
  });

  test('late profile response cannot restore data after logout', () async {
    final delayed = Completer<http.Response>();
    final api = ApiClient(
        client: MockClient((r) async =>
            r.url.path == '/api/me' ? await delayed.future : ok({})));
    api.accessToken = 'access';
    final session = AppSession(api: api);
    final pending = session.refreshProfile();
    await session.logout();
    delayed.complete(ok({'id': 1, 'nickname': 'old account'}));
    await pending;
    expect(session.profile, isNull);
    expect(session.isAuthenticated, false);
  });

  test('signup success survives unrelated profile read failure', () async {
    final api = ApiClient(
        client: MockClient((r) async => r.url.path == '/api/auth/signup'
            ? ok({'access_token': 'access', 'refresh_token': 'refresh'})
            : http.Response(
                '{"success":false,"message":"temporarily unavailable"}', 503)));
    final session = AppSession(api: api);
    await session.signup('test@example.com', 'test password', 'tester');
    expect(session.isAuthenticated, true);
  });
  test('guest favorites recent and plans survive restart without API calls',
      () async {
    final api = ApiClient(
        client: MockClient(
            (r) async => throw StateError('Guest must remain local')));
    final session = AppSession(api: api);
    await session.restore();
    await session.toggleFavorite(3);
    await session.recordRecent(3);
    await session.recordRecent(4);
    await session.recordRecent(3);
    final plan = await session.savePlan({
      'title': 'Trip',
      'date': '2026-09-20',
      'stops': [
        {'time': '09:00', 'place': 'Park'}
      ]
    });
    final restored = AppSession(api: api);
    await restored.restore();
    expect(restored.favoriteIds, {3});
    expect(await restored.loadRecentPlaces(), [3, 4]);
    expect((await restored.loadPlans()).single['title'], 'Trip');
    await restored.deletePlan(plan['id'] as int);
    await restored.clearRecent();
    await restored.toggleFavorite(3);
    final cleared = AppSession(api: api);
    await cleared.restore();
    expect(cleared.favoriteIds, isEmpty);
    expect(await cleared.loadRecentPlaces(), isEmpty);
    expect(await cleared.loadPlans(), isEmpty);
  });

  test('guest records remain isolated across login and logout', () async {
    final api = ApiClient(
        client: MockClient((r) async => switch (r.url.path) {
              '/api/auth/login' =>
                ok({'access_token': 'access', 'refresh_token': 'refresh'}),
              '/api/me' => ok({'id': 1}),
              '/api/favorites' => ok({
                  'place_ids': [99]
                }),
              '/api/plans' => ok({
                  'items': [
                    {'id': 99, 'title': 'Account plan'}
                  ]
                }),
              '/api/recent-places' => ok({
                  'place_ids': [99]
                }),
              '/api/auth/logout' => ok({}),
              _ => throw StateError('unexpected ${r.url}'),
            }));
    final session = AppSession(api: api);
    await session.restore();
    await session.toggleFavorite(3);
    await session.recordRecent(3);
    await session.savePlan({'title': 'Guest plan'});
    await session.login('test@example.com', 'password');
    expect(session.favoriteIds, {99});
    expect(await session.loadRecentPlaces(), [99]);
    expect((await session.loadPlans()).single['title'], 'Account plan');
    await session.logout();
    expect(session.favoriteIds, {3});
    expect(session.recentPlaceIds, [3]);
    expect((await session.loadPlans()).single['title'], 'Guest plan');
  });
  test('concurrent guest history and favorite preserve both categories',
      () async {
    final api =
        ApiClient(client: MockClient((r) async => throw StateError('No API')));
    final session = AppSession(api: api);
    await session.restore();
    await Future.wait([session.recordRecent(4), session.toggleFavorite(7)]);
    final restored = AppSession(api: api);
    await restored.restore();
    expect(restored.favoriteIds, {7});
    expect(restored.recentPlaceIds, [4]);
  });
}
