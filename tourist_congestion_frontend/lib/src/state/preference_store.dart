import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../models/place_category.dart';
import '../models/user_preference.dart';
import '../services/api_client.dart';
import '../services/app_session.dart';

/// Reuses account preferences; guests keep a separate device-local preference.
class PreferenceStore extends ChangeNotifier {
  PreferenceStore() {
    _session.addListener(_sync);
    _sync();
    _restoreGuest();
  }
  final AppSession _session = AppSession.instance;
  static const _storage = FlutterSecureStorage();
  static const _guestKey = 'ilion_guest_recommendation_preferences';
  UserPreference _preference = const UserPreference();
  UserPreference _guest = const UserPreference();
  bool _disposed = false;
  int _guestRevision = 0;
  UserPreference get preference => _preference;

  Future<void> _restoreGuest() async {
    final revision = _guestRevision;
    try {
      final raw = await _storage.read(key: _guestKey);
      if (_disposed || revision != _guestRevision || raw == null) return;
      _guest =
          UserPreference.fromJson(Map<String, dynamic>.from(jsonDecode(raw)));
      if (!_session.isAuthenticated) _sync();
    } catch (_) {
      // A missing or invalid local preference leaves the default selection.
    }
  }

  void _sync() {
    if (_disposed) return;
    if (!_session.isAuthenticated) {
      _preference = _guest;
    } else {
      final profile = _session.profile;
      final preferences = profile?['preferences'];
      final recommendation =
          preferences is Map ? preferences['recommendation'] : null;
      _preference = recommendation is Map
          ? UserPreference.fromJson(Map<String, dynamic>.from(recommendation))
          : const UserPreference();
      final categories = profile?['preferred_categories'];
      if (categories is List) {
        _preference = _preference.copyWith(
            favoriteCategories: PlaceCategory.values
                .where((category) => categories.contains(category.label))
                .toSet());
      }
    }
    notifyListeners();
  }

  Future<void> update(UserPreference next) async {
    if (!_session.isAuthenticated) {
      _guestRevision++;
      await _storage.write(key: _guestKey, value: jsonEncode(next.toJson()));
      _guest = next;
      if (!_disposed && !_session.isAuthenticated) _sync();
      return;
    }
    final owner = _session.profile?['id'];
    final api = ApiClient.instance;
    final data = await api.get('/me');
    if (!_session.isAuthenticated || _session.profile?['id'] != owner) return;
    final preferences = Map<String, dynamic>.from(data['preferences'] ?? {});
    final previousCategories =
        List<String>.from(data['preferred_categories'] ?? []);
    final supported = PlaceCategory.values.map((value) => value.label).toSet();
    await api.patch('/me', body: {
      'preferences': {...preferences, 'recommendation': next.toJson()},
      'preferred_categories': [
        ...previousCategories.where((value) => !supported.contains(value)),
        ...next.favoriteCategories.map((value) => value.label),
      ],
    });
    if (!_disposed &&
        _session.isAuthenticated &&
        _session.profile?['id'] == owner) {
      await _session.refreshProfile();
    }
  }

  Future<void> setCrowdTolerance(double value) =>
      update(_preference.copyWith(crowdTolerance: value));
  Future<void> setTypePreference(PlaceTypePreference value) =>
      update(_preference.copyWith(typePreference: value));
  Future<void> setMaxDistanceKm(double value) =>
      update(_preference.copyWith(maxDistanceKm: value));
  Future<void> setWeatherAware(bool value) =>
      update(_preference.copyWith(weatherAware: value));
  Future<void> toggleCategory(PlaceCategory category) {
    final next = Set<PlaceCategory>.from(_preference.favoriteCategories);
    if (!next.remove(category)) next.add(category);
    return update(_preference.copyWith(favoriteCategories: next));
  }

  Future<void> reset() => update(const UserPreference());
  @override
  void dispose() {
    _disposed = true;
    _session.removeListener(_sync);
    super.dispose();
  }
}
