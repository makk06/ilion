import 'dart:async';
import 'event_notice.dart';
import '../models/crowd_forecast.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../models/crowd_estimate.dart';
import 'crowd_badge.dart';

class CrowdEvidence extends StatelessWidget {
  const CrowdEvidence({super.key, required this.estimate});
  final CrowdEstimate estimate;

  @override
  Widget build(BuildContext context) {
    String time(DateTime date) => DateFormat(
      'M/d HH:mm',
    ).format(date.toUtc().add(const Duration(hours: 9)));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('예상 혼잡도', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        CrowdBadge(
          label: estimate.label,
          color: estimate.level?.color ?? Colors.grey,
        ),
        const SizedBox(height: 8),
        EventNoticeView(contextData: estimate.eventContext),
        if (estimate.isDemo) const Text('개발 샘플 · 실제 방문 판단에 사용하지 마세요.'),
        if (estimate.stale) const Text('오래된 정보 · 최신 상태와 다를 수 있습니다.'),
        if (estimate.openStatus == 'CLOSED')
          const Text('운영정보상 폐장 · 혼잡도와 별개입니다.'),
        if (estimate.available)
          Text('${estimate.score}/100 · 근거 품질 ${estimate.confidenceLabel}'),
        const Text(
          '신뢰도는 데이터 근거의 품질이며, 맞을 확률을 뜻하지 않습니다.',
          style: TextStyle(fontSize: 12),
        ),
        if (estimate.dataAsOf != null)
          Text(
            '입력 자료 기준 ${time(estimate.dataAsOf!)} (한국시간)',
            style: const TextStyle(fontSize: 12),
          ),
        if (estimate.scope['area_name'] != null)
          Text('참고 구역: ${estimate.scope['area_name']}'),
        Text(
          estimate.scope['type'] == 'area_proxy'
              ? '주변 구역을 참고한 추정입니다. 장소 내부 방문객 수와 다릅니다.'
              : '유형·시간·확인 가능한 환경 정보를 바탕으로 추정했습니다.',
        ),
        const SizedBox(height: 12),
        for (final factor in estimate.factors.where(
          (f) =>
              f['available'] == true &&
              !['bounds', 'smoothing'].contains(f['key']),
        ))
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text('• ${factor['description']}'),
          ),
        if (estimate.forecast.isNotEmpty)
          ForecastEvidence(forecasts: estimate.hourlyForecasts),
        const SizedBox(height: 12),
        Text(
          '출처: ${estimate.sources.map((s) => switch (s['provider']) {
            'tour_api' => '한국관광공사',
            'kma' => '기상청',
            'kasi' => '한국천문연구원',
            'model_prior' => '유형·시간 초기 가정',
            'seoul_citydata' || 'seoul_population' => '서울특별시',
            _ => '${s['provider']}',
          }).toSet().join(' · ')}',
          style: const TextStyle(fontSize: 11),
        ),
      ],
    );
  }
}

class ForecastEvidence extends StatefulWidget {
  const ForecastEvidence({super.key, required this.forecasts, this.now});
  final List<CrowdForecast> forecasts;
  final DateTime? now;
  @override
  State<ForecastEvidence> createState() => _ForecastEvidenceState();
}

class _ForecastEvidenceState extends State<ForecastEvidence>
    with WidgetsBindingObserver {
  Timer? _timer;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (widget.now == null) {
      _timer = Timer.periodic(const Duration(seconds: 30), (_) {
        if (mounted) setState(() {});
      });
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && mounted) setState(() {});
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final now = widget.now ?? DateTime.now();
    final values = widget.forecasts
        .where((f) => f.validAt != null && f.validAt!.isAfter(now))
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 8),
        const Text('앞으로의 예상', style: TextStyle(fontWeight: FontWeight.w700)),
        const Text(
          '각 구역·장소의 평소 대비 기준입니다. 장소 내부 방문객 수나 수용률을 뜻하지 않습니다.',
          style: TextStyle(fontSize: 12),
        ),
        if (values.isEmpty) const Text('새 예측 정보가 필요해요. 새로고침해 주세요.'),
        Wrap(
          spacing: 12,
          runSpacing: 8,
          children: [
            for (final f in values)
              SizedBox(
                width: 145,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(forecastTimeLabel(f.validAt!, now)),
                    EventNoticeView(contextData: f.eventContext),
                    if (f.contract.isNotEmpty)
                      Text(f.groupLabel, style: const TextStyle(fontSize: 11)),
                    Text(
                      f.usableAt(now)
                          ? f.relativeLabel
                          : f.contract.isEmpty
                          ? EstimatedCrowdLevel.parse(f.levelCode)?.label ??
                                '정보 부족'
                          : f.value == null
                          ? '정보 부족'
                          : '예측 검증 대기',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    if (!f.usableAt(now))
                      const Text('근거 품질 미평가', style: TextStyle(fontSize: 11)),
                    if (f.usableAt(now) && f.metric == 'population_density')
                      Text(
                        '${f.value!.toStringAsFixed(4)}명/㎡',
                        style: const TextStyle(fontSize: 11),
                      ),
                  ],
                ),
              ),
          ],
        ),
      ],
    );
  }
}
