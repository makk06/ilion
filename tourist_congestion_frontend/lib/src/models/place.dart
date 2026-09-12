import 'package:flutter/material.dart';

enum CrowdLevel { low, medium, busy, high }

class Place {
  const Place(
      {required this.id,
      required this.name,
      this.area = '',
      this.category = '',
      this.crowdLevel,
      this.description = '',
      this.latitude,
      this.longitude,
      this.imageUrl,
      this.rating,
      this.distanceKm,
      this.observedAt,
      this.crowdSource,
      this.crowdArea,
      this.crowdMessage = '',
      this.isReplaced = false,
      this.isDemo = false,
      this.openingHours,
      this.holidays,
      this.phone,
      this.admissionFee,
      this.parking,
      this.homepageUrl});
  final int id;
  final String name, area, category, description, crowdMessage;
  final CrowdLevel? crowdLevel;
  final double? latitude, longitude, rating, distanceKm;
  final String? imageUrl,
      crowdSource,
      crowdArea,
      openingHours,
      holidays,
      phone,
      admissionFee,
      parking,
      homepageUrl;
  final DateTime? observedAt;
  final bool isReplaced, isDemo;
  bool get hasCoordinates => latitude != null && longitude != null;
  bool get isStale =>
      observedAt != null &&
      DateTime.now().toUtc().difference(observedAt!.toUtc()) >
          const Duration(hours: 1);
  IconData get icon => Icons.place_outlined;
  String get distance =>
      distanceKm == null ? '' : '직선 ${distanceKm!.toStringAsFixed(1)}km';
  String get crowdText => switch (crowdLevel) {
        CrowdLevel.low => '여유',
        CrowdLevel.medium => '보통',
        CrowdLevel.busy => '약간 붐빔',
        CrowdLevel.high => '붐빔',
        null => '정보 없음'
      };
  Color get crowdColor => switch (crowdLevel) {
        CrowdLevel.low => Colors.teal,
        CrowdLevel.medium => Colors.blue,
        CrowdLevel.busy => Colors.orange,
        CrowdLevel.high => Colors.red,
        null => Colors.grey
      };
  factory Place.fromJson(Map<String, dynamic> json) {
    final crowd = json['latest_crowd'] as Map<String, dynamic>?;
    final info = json['info'] as Map<String, dynamic>?;
    double? number(dynamic value) =>
        value == null ? null : double.tryParse('$value');
    String? optional(dynamic value) =>
        value == null || '$value'.trim().isEmpty ? null : '$value';
    return Place(
        id: (json['id'] as num).toInt(),
        name: json['name'] as String,
        area: json['address'] as String? ?? '',
        category: json['category'] as String? ?? '',
        description: info?['description'] as String? ?? '',
        latitude: number(json['latitude']),
        longitude: number(json['longitude']),
        rating: number(json['avg_rating']),
        distanceKm: number(json['distance_km']),
        imageUrl: optional(json['image_url'] ?? info?['first_image_url']),
        crowdLevel: switch (crowd?['level']) {
          'relaxed' => CrowdLevel.low,
          'normal' => CrowdLevel.medium,
          'busy' => CrowdLevel.busy,
          'crowded' => CrowdLevel.high,
          _ => null
        },
        observedAt: DateTime.tryParse(crowd?['observed_at'] as String? ?? ''),
        crowdSource: optional(crowd?['source']),
        crowdArea: optional(crowd?['area_name']),
        crowdMessage: crowd?['message'] as String? ?? '',
        isReplaced: crowd?['is_replaced'] == true,
        isDemo: crowd?['is_demo'] == true,
        openingHours: optional(info?['opening_hours']),
        holidays: optional(info?['holiday_info']),
        phone: optional(info?['phone']),
        admissionFee: optional(info?['admission_fee']),
        parking: optional(info?['parking']),
        homepageUrl: optional(info?['homepage_url']));
  }
}
