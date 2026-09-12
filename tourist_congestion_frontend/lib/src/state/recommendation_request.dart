import 'package:flutter/foundation.dart';

import '../models/place.dart';

/// 지도 탭에서 고른 장소를 추천 탭으로 넘기기 위한 통로.
///
/// 지도 담당자는 장소 상세에서 아래 한 줄만 호출하면 된다.
/// ```dart
/// AppScope.of(context).recommendationRequest.requestAlternatives(place);
/// ```
/// 그러면 하단 탭이 추천 탭으로 바뀌고, 추천 탭이 "이 장소 근처의 비슷한
/// 대안"을 보여 준다.
class RecommendationRequest extends ChangeNotifier {
  Place? _anchor;

  /// 대안 추천의 기준이 되는 장소. null이면 일반 맞춤 추천 화면.
  Place? get anchor => _anchor;

  bool get hasAnchor => _anchor != null;

  void requestAlternatives(Place place) {
    _anchor = place;
    notifyListeners();
  }

  void clear() {
    if (_anchor == null) return;
    _anchor = null;
    notifyListeners();
  }
}
