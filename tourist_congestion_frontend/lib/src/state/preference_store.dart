import 'package:flutter/foundation.dart';

import '../models/place_category.dart';
import '../models/user_preference.dart';

/// 사용자 취향 보관소. 마이페이지와 추천 탭이 같은 값을 바라본다.
///
/// 지금은 메모리에만 두고, 로그인/설정 API가 붙으면
/// [load], [save] 안쪽만 서버 호출로 바꾸면 된다.
class PreferenceStore extends ChangeNotifier {
  UserPreference _preference = const UserPreference();

  UserPreference get preference => _preference;

  void update(UserPreference next) {
    if (next == _preference) return;
    _preference = next;
    notifyListeners();
  }

  void setCrowdTolerance(double value) =>
      update(_preference.copyWith(crowdTolerance: value));

  void setTypePreference(PlaceTypePreference value) =>
      update(_preference.copyWith(typePreference: value));

  void setMaxDistanceKm(double value) =>
      update(_preference.copyWith(maxDistanceKm: value));

  void setWeatherAware(bool value) =>
      update(_preference.copyWith(weatherAware: value));

  void toggleCategory(PlaceCategory category) {
    final next = Set<PlaceCategory>.from(_preference.favoriteCategories);
    if (!next.remove(category)) next.add(category);
    update(_preference.copyWith(favoriteCategories: next));
  }

  void reset() => update(const UserPreference());
}
