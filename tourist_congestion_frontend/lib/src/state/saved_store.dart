import 'package:flutter/foundation.dart';

import '../models/place.dart';

/// 저장한 장소 보관소.
/// 저장 탭뿐 아니라 홈·지도·추천의 하트 버튼이 모두 이 값을 공유한다.
class SavedStore extends ChangeNotifier {
  final Map<String, Place> _places = <String, Place>{};
  final Map<String, DateTime> _savedAt = <String, DateTime>{};

  /// 최근에 저장한 순서.
  List<Place> get places {
    final list = _places.values.toList();
    list.sort((a, b) => _savedAt[b.id]!.compareTo(_savedAt[a.id]!));
    return list;
  }

  int get count => _places.length;

  bool isSaved(String placeId) => _places.containsKey(placeId);

  DateTime? savedAt(String placeId) => _savedAt[placeId];

  /// 저장/해제를 뒤집고, 저장된 상태면 true를 돌려준다.
  bool toggle(Place place) {
    if (isSaved(place.id)) {
      remove(place.id);
      return false;
    }
    add(place);
    return true;
  }

  void add(Place place, {DateTime? at}) {
    _places[place.id] = place;
    _savedAt[place.id] = at ?? DateTime.now();
    notifyListeners();
  }

  void remove(String placeId) {
    if (_places.remove(placeId) == null) return;
    _savedAt.remove(placeId);
    notifyListeners();
  }

  void clear() {
    if (_places.isEmpty) return;
    _places.clear();
    _savedAt.clear();
    notifyListeners();
  }
}
