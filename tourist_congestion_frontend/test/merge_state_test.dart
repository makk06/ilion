import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/models/user_preference.dart';
import 'package:tourist_congestion_frontend/src/models/place_category.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';
import 'package:tourist_congestion_frontend/src/state/preference_store.dart';
import 'package:tourist_congestion_frontend/src/state/saved_store.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });
  test('guest recommendation preferences persist without API calls', () async {
    ApiClient.instance = ApiClient(
        client: MockClient(
            (_) async => throw StateError('Unexpected API request')));
    AppSession.instance = AppSession();
    final first = PreferenceStore();
    await first.update(const UserPreference(
        maxDistanceKm: 25, favoriteCategories: {PlaceCategory.culture}));
    first.dispose();
    final restored = PreferenceStore();
    await Future<void>.delayed(Duration.zero);
    expect(restored.preference.maxDistanceKm, 25);
    expect(restored.preference.favoriteCategories, {PlaceCategory.culture});
    restored.dispose();
  });
  test(
      'account preference save preserves unrelated settings and category labels',
      () async {
    Map<String, dynamic> profile = {
      'id': 5,
      'preferred_categories': ['자연'],
      'preferences': {
        'notifications': {'review': false},
        'regions': ['서울']
      }
    };
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      expect(request.url.path, '/api/me');
      if (request.method == 'PATCH') {
        profile.addAll(jsonDecode(request.body) as Map<String, dynamic>);
      }
      return http.Response(jsonEncode({'success': true, 'data': profile}), 200,
          headers: {'content-type': 'application/json'});
    }));
    ApiClient.instance.accessToken = 'test-token';
    AppSession.instance = AppSession();
    AppSession.instance.profile = profile;
    final store = PreferenceStore();
    await store.update(const UserPreference(
        favoriteCategories: {PlaceCategory.culture}, maxDistanceKm: 20));
    expect(profile['preferences']['notifications']['review'], false);
    expect(profile['preferences']['regions'], ['서울']);
    expect(profile['preferred_categories'], containsAll(['자연', '문화시설']));
    expect(store.preference.maxDistanceKm, 20);
    store.dispose();
  });
  test('recommendation saving shares the persisted guest favorites', () async {
    ApiClient.instance = ApiClient(
        client: MockClient(
            (_) async => throw StateError('Unexpected API request')));
    AppSession.instance = AppSession();
    await AppSession.instance.restore();
    final store = SavedStore();
    expect(await store.toggle(const Place(id: 42, name: '저장할 장소')), true);
    expect(AppSession.instance.favoriteIds, contains(42));
    store.dispose();
    AppSession.instance = AppSession();
    await AppSession.instance.restore();
    expect(AppSession.instance.favoriteIds, contains(42));
  });
}
