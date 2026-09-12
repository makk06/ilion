import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../models/crowd_estimate.dart';
import 'crowd_badge.dart';

class CrowdEvidence extends StatelessWidget {
  const CrowdEvidence({super.key, required this.estimate});
  final CrowdEstimate estimate;

  @override
  Widget build(BuildContext context) {
    String time(DateTime date) => DateFormat('M/d HH:mm')
        .format(date.toUtc().add(const Duration(hours: 9)));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('예상 혼잡도', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      CrowdBadge(
          label: estimate.label, color: estimate.level?.color ?? Colors.grey),
      const SizedBox(height: 8),
      if (estimate.isDemo) const Text('개발 샘플 · 실제 방문 판단에 사용하지 마세요.'),
      if (estimate.stale) const Text('오래된 정보 · 최신 상태와 다를 수 있습니다.'),
      if (estimate.openStatus == 'CLOSED') const Text('운영정보상 폐장 · 혼잡도와 별개입니다.'),
      if (estimate.available)
        Text('${estimate.score}/100 · 근거 품질 ${estimate.confidenceLabel}'),
      const Text('신뢰도는 데이터 근거의 품질이며, 맞을 확률을 뜻하지 않습니다.',
          style: TextStyle(fontSize: 12)),
      if (estimate.dataAsOf != null)
        Text('입력 자료 기준 ${time(estimate.dataAsOf!)} (한국시간)',
            style: const TextStyle(fontSize: 12)),
      if (estimate.scope['area_name'] != null)
        Text('참고 구역: ${estimate.scope['area_name']}'),
      Text(estimate.scope['type'] == 'area_proxy'
          ? '주변 구역을 참고한 추정입니다. 장소 내부 방문객 수와 다릅니다.'
          : '유형·시간·확인 가능한 환경 정보를 바탕으로 추정했습니다.'),
      const SizedBox(height: 12),
      for (final factor in estimate.factors.where((f) =>
          f['available'] == true &&
          !['bounds', 'smoothing'].contains(f['key'])))
        Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text('• ${factor['description']}')),
      if (estimate.forecast.isNotEmpty) ...[
        const SizedBox(height: 8),
        const Text('앞으로의 예상', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Wrap(spacing: 12, runSpacing: 8, children: [
          for (final item in estimate.forecast)
            SizedBox(
                width: 100,
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${item['hours_ahead']}시간 후'),
                      Text(
                          EstimatedCrowdLevel.parse(item['crowd_level'])
                                  ?.label ??
                              '정보 부족',
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      Text(
                          '근거 품질 ${((item['confidence'] as num? ?? 0) * 100).round()}/100',
                          style: const TextStyle(fontSize: 11)),
                    ])),
        ]),
      ],
      const SizedBox(height: 12),
      Text(
          '출처: ${estimate.sources.map((s) => switch (s['provider']) {
                'tour_api' => '한국관광공사',
                'kma' => '기상청',
                'kasi' => '한국천문연구원',
                'model_prior' => '유형·시간 초기 가정',
                'seoul_citydata' || 'seoul_population' => '서울특별시',
                _ => '${s['provider']}'
              }).toSet().join(' · ')}',
          style: const TextStyle(fontSize: 11)),
    ]);
  }
}
