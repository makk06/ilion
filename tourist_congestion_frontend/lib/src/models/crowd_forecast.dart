import 'event_context.dart';

/// An exact-hour forecast. Eligibility comes from the decision validation contract.
class CrowdForecast {
  CrowdForecast.fromJson(Map<String, dynamic> json)
    : eventContext = EventContext.parse(json['event_context']),
      issuedAt = DateTime.tryParse(json['issued_at'] as String? ?? ''),
      validAt = DateTime.tryParse(json['valid_at'] as String? ?? ''),
      value = (json['value'] as num?)?.toDouble(),
      score = (json['crowd_score'] as num?)?.toDouble(),
      provider = json['provider'] as String? ?? '',
      externalId = json['external_id']?.toString() ?? '',
      metric = json['metric'] as String? ?? '',
      unit = json['unit'] as String? ?? '',
      scope = json['scope'] as String? ?? '',
      levelCode = json['crowd_level'] as String?,
      contract = json['decision_contract_version'] as String? ?? '',
      normalization = json['normalization'] as String? ?? '',
      guidanceEligible = json['guidance_eligible'] == true,
      rankingEligible = json['ranking_eligible'] == true;

  final EventContext? eventContext;
  final DateTime? issuedAt, validAt;
  final double? value, score;
  final String provider,
      externalId,
      metric,
      unit,
      scope,
      contract,
      normalization;
  final String? levelCode;
  final bool guidanceEligible, rankingEligible;

  String get group => '$provider|$metric|$scope';
  String get groupLabel =>
      '${provider == 'seoul' ? '서울시' : 'TMAP'} · ${scope == 'area_population' ? '구역' : '장소'}의 평소 대비';
  bool get validIdentity =>
      externalId.isNotEmpty &&
      ((provider == 'seoul' &&
              metric == 'population_count' &&
              unit == 'persons' &&
              scope == 'area_population') ||
          (provider == 'tmap' &&
              metric == 'population_density' &&
              unit == 'persons_per_m2' &&
              scope == 'place_density'));

  bool usableAt(DateTime now, {bool ranking = false}) =>
      contract == 'relative-choice-v2' &&
      normalization == 'within_target_empirical_percentile' &&
      guidanceEligible &&
      (!ranking || rankingEligible) &&
      validIdentity &&
      value != null &&
      value!.isFinite &&
      value! >= 0 &&
      score != null &&
      score!.isFinite &&
      score! >= 0 &&
      score! <= 100 &&
      issuedAt != null &&
      validAt != null &&
      issuedAt!.microsecondsSinceEpoch % Duration.microsecondsPerHour == 0 &&
      validAt!.microsecondsSinceEpoch % Duration.microsecondsPerHour == 0 &&
      !issuedAt!.isAfter(now) &&
      validAt!.isAfter(now) &&
      validAt!.difference(issuedAt!).inMinutes >= 60 &&
      validAt!.difference(issuedAt!).inMinutes <= 180;

  int? get stage => score == null
      ? null
      : score! <= 20
      ? 0
      : score! <= 40
      ? 1
      : score! <= 65
      ? 2
      : score! <= 85
      ? 3
      : 4;
  String get relativeLabel => stage == null
      ? '정보 부족'
      : const [
          '평소보다 매우 한산',
          '평소보다 한산',
          '평소 수준',
          '평소보다 붐빔',
          '평소보다 매우 붐빔',
        ][stage!];
}

String forecastTimeLabel(DateTime target, DateTime now) {
  final at = target.toUtc().add(const Duration(hours: 9));
  final today = now.toUtc().add(const Duration(hours: 9));
  final prefix =
      at.year == today.year && at.month == today.month && at.day == today.day
      ? '오늘'
      : '${at.month}/${at.day}';
  return '$prefix ${at.hour.toString().padLeft(2, '0')}:${at.minute.toString().padLeft(2, '0')} 예상';
}
