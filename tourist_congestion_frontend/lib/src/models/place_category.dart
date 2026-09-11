import 'package:flutter/material.dart';

/// 장소 대분류. TourAPI `contentTypeId` 기준으로 맞춰 두어 백엔드 응답을
/// 그대로 매핑할 수 있게 한다. (DECISIONS.md 2026-08-17 초기 적재 범위)
enum PlaceCategory {
  attraction(12, '관광지', Icons.landscape_rounded),
  culture(14, '문화시설', Icons.museum_rounded),
  festival(15, '축제·공연', Icons.celebration_rounded),
  leisure(28, '레포츠', Icons.directions_bike_rounded),
  shopping(38, '쇼핑', Icons.shopping_bag_rounded),
  food(39, '음식점', Icons.restaurant_rounded);

  const PlaceCategory(this.contentTypeId, this.label, this.icon);

  final int contentTypeId;
  final String label;
  final IconData icon;

  static PlaceCategory fromContentTypeId(int id) {
    return PlaceCategory.values.firstWhere(
      (category) => category.contentTypeId == id,
      orElse: () => PlaceCategory.attraction,
    );
  }
}

/// 실내/실외 구분. 백엔드 `Place.indoor_outdoor` 와 동일한 값 집합.
enum IndoorOutdoor {
  indoor('실내'),
  outdoor('실외'),
  unknown('실내외');

  const IndoorOutdoor(this.label);

  final String label;
}
