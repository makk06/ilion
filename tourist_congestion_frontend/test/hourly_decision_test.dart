import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/models/crowd_estimate.dart';
import 'package:tourist_congestion_frontend/src/models/crowd_forecast.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/models/user_preference.dart';
import 'package:tourist_congestion_frontend/src/services/recommendation_engine.dart';
import 'package:tourist_congestion_frontend/src/widgets/crowd_evidence.dart';

final now = DateTime.parse('2026-09-13T12:50:00+09:00');
final visit = DateTime.parse('2026-09-13T13:00:00+09:00');

Map<String, dynamic> forecast(
  double score, {
  bool ranking = true,
  bool guidance = true,
}) => {
  'issued_at': '2026-09-13T12:00:00+09:00',
  'valid_at': visit.toIso8601String(),
  'hours_ahead': 1,
  'provider': 'seoul',
  'external_id': 'A',
  'metric': 'population_count',
  'unit': 'persons',
  'scope': 'area_population',
  'value': 100,
  'crowd_score': score,
  'crowd_level': score <= 40 ? 'LOW' : 'HIGH',
  'confidence': 0,
  'decision_contract_version': 'relative-choice-v2',
  'normalization': 'within_target_empirical_percentile',
  'guidance_eligible': guidance,
  'ranking_eligible': ranking,
};

Place place(int id, int current, List<Map<String, dynamic>> forecasts) => Place(
  id: id,
  name: '장소$id',
  crowdEstimate: CrowdEstimate.fromJson({
    'status': 'available',
    'crowd_score': current,
    'crowd_level': 'NORMAL',
    'confidence': 1,
    'estimated_at': now.toIso8601String(),
    'forecast': forecasts,
  }),
);

void main() {
  test('old decision pass cannot authorize new relative guidance', () {
    final old = CrowdForecast.fromJson({
      ...forecast(20),
      'decision_contract_version': 'relative-choice-v1',
    });
    expect(old.usableAt(now), isFalse);
    expect(CrowdForecast.fromJson(forecast(85)).relativeLabel, '평소보다 붐빔');
    expect(CrowdForecast.fromJson(forecast(85.01)).relativeLabel, '평소보다 매우 붐빔');
  });
  test('non-hour timestamps are not offered as visit forecasts', () {
    final invalid = CrowdForecast.fromJson({
      ...forecast(20),
      'valid_at': '2026-09-13T13:05:00+09:00',
    });
    expect(invalid.usableAt(now), isFalse);
  });
  const engine = RecommendationEngine();
  test(
    'future choice uses exact future value even when forecast confidence is zero',
    () {
      final a = place(1, 0, [forecast(90)]);
      final b = place(2, 100, [
        {...forecast(10), 'external_id': 'B'},
      ]);
      final results = engine.recommend(
        places: [a, b],
        preference: const UserPreference(crowdTolerance: 0),
        visitAt: visit,
        now: now,
      );
      expect(results.first.place.id, 2);
      expect(results.first.crowdForRanking, 10);
      expect(results.last.crowdForRanking, 90);
    },
  );
  test(
    'no current or adjacent forecast fallback and expired choice stays unavailable',
    () {
      for (final target in [
        visit,
        visit.add(const Duration(minutes: 30)),
        now.subtract(const Duration(minutes: 1)),
      ]) {
        final r = engine
            .recommend(
              places: [place(1, 0, [])],
              preference: const UserPreference(),
              visitAt: target,
              now: now,
            )
            .single;
        expect(r.crowdForRanking, isNull);
        expect(r.reasons, contains('해당 시각 혼잡 정보 없음'));
      }
      expect(
        engine.forecastAt(
          place(1, 0, [forecast(10)]),
          visit.add(const Duration(minutes: 30)),
          now,
        ),
        isNull,
      );
    },
  );
  test('guidance-only forecasts never influence ranking', () {
    final r = engine
        .recommend(
          places: [
            place(1, 0, [forecast(10, ranking: false)]),
          ],
          preference: const UserPreference(),
          visitAt: visit,
          now: now,
        )
        .single;
    expect(r.forecast, isNotNull);
    expect(r.crowdForRanking, isNull);
    expect(r.comparisonGroup, isNull);
  });
  test('mismatched unit and old PASS payload cannot be used', () {
    expect(
      CrowdForecast.fromJson({
        ...forecast(10),
        'unit': 'persons_per_m2',
      }).usableAt(now),
      isFalse,
    );
    expect(
      CrowdForecast.fromJson({
        ...forecast(10),
        'decision_contract_version': 'old',
      }).usableAt(now),
      isFalse,
    );
    expect(
      CrowdForecast.fromJson(forecast(10, guidance: false)).usableAt(now),
      isFalse,
    );
  });
  test('same stage does not claim a lower stage', () {
    const a = Place(
      id: 1,
      name: '기준',
      crowdScore: 64,
      latitude: 37,
      longitude: 127,
    );
    const b = Place(
      id: 2,
      name: '후보',
      crowdScore: 53,
      latitude: 37,
      longitude: 127,
    );
    final r = engine
        .recommend(
          places: [a, b],
          preference: const UserPreference(),
          anchor: a,
        )
        .single;
    expect(r.reasons.any((v) => v.contains('단계가 낮아요')), isFalse);
  });
  test('absolute Korean target time and midnight label', () {
    expect(forecastTimeLabel(visit, now), '오늘 13:00 예상');
    expect(
      forecastTimeLabel(DateTime.parse('2026-09-14T00:00:00+09:00'), now),
      '9/14 00:00 예상',
    );
    expect(CrowdForecast.fromJson(forecast(40)).relativeLabel, '평소보다 한산');
    expect(CrowdForecast.fromJson(forecast(65)).relativeLabel, '평소 수준');
  });
  testWidgets(
    '12:50 shows 13:00 rather than one hour later; expired result removed',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ForecastEvidence(
              now: now,
              forecasts: [CrowdForecast.fromJson(forecast(10))],
            ),
          ),
        ),
      );
      expect(find.text('오늘 13:00 예상'), findsOneWidget);
      expect(find.text('1시간 후'), findsNothing);
      expect(find.text('평소보다 한산'), findsNothing);
      expect(find.text('평소보다 매우 한산'), findsOneWidget);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ForecastEvidence(
              now: visit,
              forecasts: [CrowdForecast.fromJson(forecast(10))],
            ),
          ),
        ),
      );
      expect(find.text('오늘 13:00 예상'), findsNothing);
      expect(find.textContaining('새 예측 정보'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
