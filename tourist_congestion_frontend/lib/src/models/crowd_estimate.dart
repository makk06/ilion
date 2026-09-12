import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

enum EstimatedCrowdLevel {
  veryLow('VERY_LOW', '매우 여유', AppColors.estimateVeryLow),
  low('LOW', '여유', AppColors.estimateLow),
  normal('NORMAL', '보통', AppColors.estimateNormal),
  high('HIGH', '혼잡', AppColors.estimateHigh),
  veryHigh('VERY_HIGH', '매우 혼잡', AppColors.estimateVeryHigh);

  const EstimatedCrowdLevel(this.code, this.label, this.color);
  final String code, label;
  final Color color;
  static EstimatedCrowdLevel? parse(dynamic code) =>
      values.where((v) => v.code == code).firstOrNull;
}

class CrowdEstimate {
  CrowdEstimate.fromJson(Map<String, dynamic> json)
      : status = json['status'] as String? ?? 'unavailable',
        score = (json['crowd_score'] as num?)?.round(),
        level = EstimatedCrowdLevel.parse(json['crowd_level']),
        confidence =
            ((json['confidence'] as num?)?.toDouble() ?? 0).clamp(0, 1),
        tier = json['tier'] as String? ?? 'C',
        kind = json['estimate_kind'] as String? ?? 'prior_based',
        isStale = json['is_stale'] == true,
        isDemo = json['is_demo'] == true,
        openStatus = json['open_status'] as String?,
        estimatedAt = DateTime.tryParse(json['estimated_at'] as String? ?? ''),
        dataAsOf = DateTime.tryParse(json['data_as_of'] as String? ?? ''),
        scope = Map<String, dynamic>.from(json['spatial_scope'] as Map? ?? {}),
        factors = _maps(json['factors']),
        sources = _maps(json['sources']),
        forecast = _maps(json['forecast']);

  final String status, tier, kind;
  final String? openStatus;
  final int? score;
  final EstimatedCrowdLevel? level;
  final double confidence;
  final bool isStale, isDemo;
  final DateTime? estimatedAt, dataAsOf;
  final Map<String, dynamic> scope;
  final List<Map<String, dynamic>> factors, sources, forecast;
  bool get available => status == 'available' && score != null && level != null;
  bool get lowConfidence => tier == 'C' || confidence < .4;
  bool get expiredLocally =>
      estimatedAt != null &&
      DateTime.now().toUtc().difference(estimatedAt!.toUtc()) >
          const Duration(minutes: 15);
  bool get stale => isStale || expiredLocally;
  String get label => available
      ? '예상 ${level!.label}${lowConfidence ? ' · 낮은 신뢰도' : ''}'
      : '정보 부족';
  String get confidenceLabel => lowConfidence
      ? '낮음'
      : confidence < .7
          ? '보통'
          : '높음';
  static List<Map<String, dynamic>> _maps(dynamic value) => value is List
      ? value.whereType<Map>().map((v) => Map<String, dynamic>.from(v)).toList()
      : [];
}
