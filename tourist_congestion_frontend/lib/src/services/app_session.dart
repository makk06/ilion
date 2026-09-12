import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api_client.dart';

class AppSession extends ChangeNotifier {
  AppSession({ApiClient? api, FlutterSecureStorage? storage})
      : _api = api ?? ApiClient.instance,
        _storage = storage ?? const FlutterSecureStorage() {
    _api.refreshAccessToken = _refresh;
  }
  static AppSession instance = AppSession();
  final ApiClient _api;
  final FlutterSecureStorage _storage;
  static const _key = 'ilion_session';
  static const _guestKey = 'ilion_guest_data';
  Set<int> _guestFavorites = {};
  List<int> _guestRecent = [];
  List<Map<String, dynamic>> _guestPlans = [];
  List<int> _recentIds = [];
  List<int> get recentPlaceIds => List.unmodifiable(_recentIds);
  String? _refreshToken;
  int _generation = 0;
  Map<String, dynamic>? profile;
  Set<int> favoriteIds = <int>{};
  bool get isAuthenticated => _api.accessToken != null;

  Future<void> restore() async {
    await _restoreGuest();
    final saved = await _storage.read(key: _key);
    if (saved == null) {
      notifyListeners();
      return;
    }
    try {
      final data = jsonDecode(saved) as Map<String, dynamic>;
      _api.accessToken = data['access_token'] as String?;
      _refreshToken = data['refresh_token'] as String?;
      if (isAuthenticated) {
        favoriteIds = {};
        _recentIds = [];
      }
    } catch (_) {
      await _clear();
      return;
    }
    // Network failure does not destroy a valid stored session.
    try {
      await refreshProfile();
      await refreshFavorites();
    } on ApiException catch (e) {
      if (e.statusCode == 401) await _clear();
    }
    notifyListeners();
  }

  Future<void> login(String email, String password) async {
    await _authenticate(
        '/auth/login', {'email': email.trim(), 'password': password});
  }

  Future<void> signup(String email, String password, String nickname) async {
    await _authenticate('/auth/signup', {
      'email': email.trim(),
      'password': password,
      'nickname': nickname.trim()
    });
  }

  Future<void> _authenticate(String path, Map<String, String> body) async {
    final data =
        Map<String, dynamic>.from(await _api.post(path, body: body) as Map);
    _generation++;
    _api.accessToken = data['access_token'] as String;
    _refreshToken = data['refresh_token'] as String;
    profile = null;
    favoriteIds = {};
    _recentIds = [];
    await _persist();
    notifyListeners();
    // Credentials are already accepted. A subsequent read failure must not
    // present signup as failed and encourage duplicate account creation.
    try {
      await refreshProfile();
      await refreshFavorites();
    } on ApiException catch (e) {
      if (e.statusCode == 401) rethrow;
    }
  }

  Future<void> _persist() => _storage.write(
      key: _key,
      value: jsonEncode({
        'access_token': _api.accessToken,
        'refresh_token': _refreshToken,
      }));

  Future<bool> _refresh() async {
    if (_refreshToken == null) return false;
    final generation = _generation;
    try {
      final result = await _api
          .post('/auth/refresh', body: {'refresh_token': _refreshToken});
      if (generation != _generation) return false;
      _api.accessToken = result['access_token'] as String;
      await _persist();
      return true;
    } on ApiException catch (e) {
      if (e.statusCode == 401 && generation == _generation) await _clear();
      rethrow;
    }
  }

  Future<void> refreshProfile() async {
    if (!isAuthenticated) return;
    final generation = _generation;
    final result = Map<String, dynamic>.from(await _api.get('/me') as Map);
    if (generation != _generation || !isAuthenticated) return;
    profile = result;
    notifyListeners();
  }

  Future<void> refreshFavorites() async {
    if (!isAuthenticated) return;
    final generation = _generation;
    final data = await _api.get('/favorites');
    if (generation != _generation || !isAuthenticated) return;
    favoriteIds =
        (data['place_ids'] as List).map((id) => (id as num).toInt()).toSet();
    notifyListeners();
  }

  final Set<int> _pendingFavorites = {};
  Future<void> toggleFavorite(int id) async {
    if (!isAuthenticated) {
      if (!_pendingFavorites.add(id)) return;
      try {
        final next = {..._guestFavorites};
        next.contains(id) ? next.remove(id) : next.add(id);
        await _saveGuest(favorites: next);
        if (!isAuthenticated) favoriteIds = {..._guestFavorites};
        notifyListeners();
      } finally {
        _pendingFavorites.remove(id);
      }
      return;
    }
    if (!_pendingFavorites.add(id)) return;
    final generation = _generation;
    try {
      if (favoriteIds.contains(id)) {
        await _api.delete('/favorites/$id');
        if (generation != _generation) return;
        favoriteIds = {...favoriteIds}..remove(id);
      } else {
        await _api.post('/favorites', body: {'place_id': id});
        if (generation != _generation) return;
        favoriteIds = {...favoriteIds, id};
      }
      notifyListeners();
    } finally {
      _pendingFavorites.remove(id);
    }
  }

  Future<void> logout() async {
    if (isAuthenticated) await _api.post('/auth/logout');
    await _clear();
  }

  Future<void> _clear() async {
    _generation++;
    _api.accessToken = null;
    _refreshToken = null;
    profile = null;
    favoriteIds = {..._guestFavorites};
    _recentIds = [..._guestRecent];
    await _storage.delete(key: _key);
    notifyListeners();
  }

  Future<void> _restoreGuest() async {
    final saved = await _storage.read(key: _guestKey);
    if (saved != null) {
      try {
        final data = jsonDecode(saved) as Map<String, dynamic>;
        _guestFavorites = (data['favorites'] as List? ?? [])
            .whereType<num>()
            .map((e) => e.toInt())
            .toSet();
        _guestRecent = (data['recent'] as List? ?? [])
            .whereType<num>()
            .map((e) => e.toInt())
            .take(50)
            .toList();
        _guestPlans = (data['plans'] as List? ?? [])
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList();
      } catch (_) {
        _guestFavorites = {};
        _guestRecent = [];
        _guestPlans = [];
      }
    }
    if (!isAuthenticated) {
      favoriteIds = {..._guestFavorites};
      _recentIds = [..._guestRecent];
    }
  }

  Future<void> _guestWrite = Future.value();
  Future<void> _saveGuest(
      {Set<int>? favorites,
      List<int>? recent,
      List<Map<String, dynamic>>? plans}) {
    final write = _guestWrite.then((_) async {
      final nextFavorites = favorites ?? _guestFavorites;
      final nextRecent = recent ?? _guestRecent;
      final nextPlans = plans ?? _guestPlans;
      await _storage.write(
          key: _guestKey,
          value: jsonEncode({
            'favorites': nextFavorites.toList(),
            'recent': nextRecent,
            'plans': nextPlans
          }));
      _guestFavorites = nextFavorites;
      _guestRecent = nextRecent;
      _guestPlans = nextPlans;
    });
    _guestWrite =
        write.then<void>((_) {}, onError: (Object _, StackTrace __) {});
    return write;
  }

  Future<List<int>> loadRecentPlaces() async {
    final generation = _generation;
    if (!isAuthenticated) return [..._guestRecent];
    final data = await _api.get('/recent-places');
    if (generation != _generation) return [..._recentIds];
    _recentIds =
        (data['place_ids'] as List).map((e) => (e as num).toInt()).toList();
    return [..._recentIds];
  }

  Future<void> recordRecent(int id) async {
    final generation = _generation;
    if (isAuthenticated) {
      await _api.post('/recent-places', body: {'place_id': id});
      if (generation != _generation) return;
      _recentIds =
          [id, ..._recentIds.where((value) => value != id)].take(50).toList();
    } else {
      await _saveGuest(
          recent: [id, ..._guestRecent.where((value) => value != id)]
              .take(50)
              .toList());
      if (generation != _generation) return;
      _recentIds = [..._guestRecent];
    }
    notifyListeners();
  }

  Future<void> clearRecent() async {
    final generation = _generation;
    if (isAuthenticated) {
      await _api.delete('/recent-places');
    } else {
      await _saveGuest(recent: []);
    }
    if (generation != _generation) return;
    _recentIds = [];
    notifyListeners();
  }

  Future<List<Map<String, dynamic>>> loadPlans() async {
    if (isAuthenticated) {
      final generation = _generation;
      final data = await _api.get('/plans');
      if (generation != _generation) return [];
      return (data['items'] as List)
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
    }
    return (jsonDecode(jsonEncode(_guestPlans)) as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  Future<Map<String, dynamic>> savePlan(Map<String, dynamic> plan) async {
    if (isAuthenticated)
      return Map<String, dynamic>.from(
          await _api.post('/plans', body: plan) as Map);
    final nextId = _guestPlans.fold<int>(
            0,
            (value, item) =>
                (item['id'] as int) < value ? item['id'] as int : value) -
        1;
    final saved = Map<String, dynamic>.from(jsonDecode(jsonEncode(plan)) as Map)
      ..addAll({
        'id': nextId,
        'created_at': DateTime.now().toUtc().toIso8601String()
      });
    await _saveGuest(plans: [..._guestPlans, saved]);
    notifyListeners();
    return Map<String, dynamic>.from(saved);
  }

  Future<void> deletePlan(Object id) async {
    if (isAuthenticated) {
      await _api.delete('/plans/$id');
    } else {
      await _saveGuest(
          plans: _guestPlans
              .where((item) => item['id'].toString() != id.toString())
              .toList());
    }
    notifyListeners();
  }
}
