import 'package:flutter/material.dart';

import 'place_category.dart';
import 'weather.dart';

enum CrowdLevel {
  low('여유'),
  medium('보통'),
  high('혼잡');

  const CrowdLevel(this.label);

  final String label;

  /// 0~100 혼잡도 점수를 단계로 변환한다. 백엔드 `CrowdData` 연동 시에도
  /// 앱에서는 이 기준 하나만 쓰도록 한곳에 모아 둔다.
  static CrowdLevel fromScore(int score) {
    if (score < 34) return CrowdLevel.low;
    if (score < 67) return CrowdLevel.medium;
    return CrowdLevel.high;
  }
}

class Place {
  const Place({
    required this.id,
    required this.name,
    required this.area,
    required this.address,
    required this.category,
    required this.mainCategory,
    required this.crowdScore,
    required this.distanceKm,
    required this.indoorOutdoor,
    required this.latitude,
    required this.longitude,
    required this.description,
    this.weather,
    this.tags = const <String>[],
    this.rating,
    this.iconOverride,
  });

  final String id;
  final String name;

  /// 짧은 행정구역 표기. 예: `서울 성동구`
  final String area;

  /// 전체 주소. 검색 결과와 상세 화면에 표기한다.
  final String address;

  /// 화면 표기용 소분류. 예: `자연 · 공원`
  final String category;

  /// 필터·추천 계산에 쓰는 대분류.
  final PlaceCategory mainCategory;

  /// 0~100 실시간 혼잡도.
  final int crowdScore;

  /// 현재 위치 기준 거리(km).
  final double distanceKm;

  final IndoorOutdoor indoorOutdoor;
  final double latitude;
  final double longitude;
  final String description;
  final Weather? weather;
  final List<String> tags;
  final double? rating;
  final IconData? iconOverride;

  CrowdLevel get crowdLevel => CrowdLevel.fromScore(crowdScore);

  String get crowdText => crowdLevel.label;

  IconData get icon => iconOverride ?? mainCategory.icon;

  String get distance => distanceKm < 1
      ? '${(distanceKm * 1000).round()}m'
      : '${distanceKm.toStringAsFixed(1)}km';
}
