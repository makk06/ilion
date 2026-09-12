import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';

void main() {
  test('encodes filters and unwraps actual backend envelope', () async {
    final api = ApiClient(
        baseUrl: 'http://localhost:8000/api/',
        client: MockClient((request) async {
          expect(request.url.path, '/api/places');
          expect(request.url.queryParameters['keyword'], '서울 숲');
          return http.Response(
              jsonEncode({
                'success': true,
                'data': {'items': []}
              }),
              200);
        }));
    expect(await api.get('/places', query: {'keyword': '서울 숲'}), {'items': []});
  });

  test('refreshes rejected token and replays request with new authorization',
      () async {
    var calls = 0;
    late ApiClient api;
    api = ApiClient(client: MockClient((request) async {
      calls++;
      if (calls == 1) return http.Response('{"detail":"expired"}', 401);
      expect(request.headers['Authorization'], 'Bearer fresh');
      return http.Response('{"success":true,"data":{"place_ids":[3]}}', 200);
    }));
    api.accessToken = 'old';
    api.refreshAccessToken = () async {
      api.accessToken = 'fresh';
      return true;
    };
    expect(await api.get('/favorites'), {
      'place_ids': [3]
    });
    expect(calls, 2);
  });

  test('does not refresh invalid login credentials', () async {
    final api = ApiClient(
        client: MockClient((_) async => http.Response(
            '{"success":false,"message":"invalid credentials"}', 401)));
    api.refreshAccessToken = () async => throw StateError('must not refresh');
    await expectLater(
        api.post('/auth/login', body: {'email': 'x'}),
        throwsA(
            isA<ApiException>().having((e) => e.statusCode, 'status', 401)));
  });

  test('reports non-JSON server failures without leaking HTML', () async {
    final api = ApiClient(
        client: MockClient(
            (_) async => http.Response('<html>traceback</html>', 500)));
    await expectLater(
        api.get('/places'),
        throwsA(isA<ApiException>().having(
            (e) => e.message.contains('traceback'), 'sanitized', false)));
  });

  test('network failure does not replay a write', () async {
    var calls = 0;
    final api = ApiClient(client: MockClient((_) async {
      calls++;
      throw http.ClientException('offline');
    }));
    await expectLater(api.post('/reviews', body: {'text': 'review'}),
        throwsA(isA<ApiException>()));
    expect(calls, 1);
  });

  test('media paths resolve against server origin', () {
    final api = ApiClient(baseUrl: 'http://localhost:8000/api');
    expect(api.mediaUrl('/media/reviews/a.jpg'),
        'http://localhost:8000/media/reviews/a.jpg');
    expect(
        api.mediaUrl('https://example.com/a.jpg'), 'https://example.com/a.jpg');
  });
}
