import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/models/crowd_estimate.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/models/user_preference.dart';
import 'package:tourist_congestion_frontend/src/services/recommendation_engine.dart';
import 'package:tourist_congestion_frontend/src/widgets/crowd_evidence.dart';
import 'package:tourist_congestion_frontend/src/widgets/place_card.dart';

Map<String, dynamic> payload({
  double confidence = .2,
  bool demo = false,
  bool stale = false,
  String? open,
}) => {
  'status': 'available',
  'crowd_score': 10,
  'crowd_level': 'VERY_LOW',
  'tier': confidence < .4 ? 'C' : 'A',
  'confidence': confidence,
  'estimate_kind': 'prior_based',
  'is_demo': demo,
  'is_stale': stale,
  'open_status': open,
  'estimated_at': DateTime.now().toUtc().toIso8601String(),
  'spatial_scope': {'type': 'area_proxy', 'area_name': '주변 영역'},
  'forecast': [
    for (final h in [1, 2, 3])
      {
        'hours_ahead': h,
        'crowd_score': 20,
        'crowd_level': 'VERY_LOW',
        'confidence': .15,
      },
  ],
};

Map<String, dynamic> validatedDensity(int h) {
  final current = DateTime.now().toUtc();
  final t = DateTime.utc(
    current.year,
    current.month,
    current.day,
    current.hour,
  );
  return {
    'issued_at': t.toIso8601String(),
    'valid_at': t.add(Duration(hours: h)).toIso8601String(),
    'provider': 'tmap',
    'external_id': 'X',
    'metric': 'population_density',
    'unit': 'persons_per_m2',
    'scope': 'place_density',
    'crowd_score': 50,
    'guidance_eligible': true,
    'ranking_eligible': false,
    'normalization': 'within_target_empirical_percentile',
    'decision_contract_version': 'relative-choice-v2',
  };
}

void main() {
  testWidgets('area mean forecasts disclose scope and unavailable values', (
    tester,
  ) async {
    final data = payload();
    data['forecast'] = [
      {
        'valid_at': DateTime.now()
            .add(const Duration(hours: 1))
            .toUtc()
            .toIso8601String(),
        'hours_ahead': 1,
        'scope': 'area_population',
        'crowd_score': null,
        'crowd_level': null,
        'confidence_status': 'not_calibrated',
      },
    ];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: CrowdEvidence(estimate: CrowdEstimate.fromJson(data)),
          ),
        ),
      ),
    );
    expect(find.text('근거 품질 미평가'), findsOneWidget);
    expect(find.text('정보 부족'), findsOneWidget);
    expect(find.textContaining('장소 내부 방문객 수나 수용률을 뜻하지 않습니다'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('density forecast preserves units and missing values', (
    tester,
  ) async {
    final data = payload();
    data['forecast'] = [
      {
        ...validatedDensity(1),
        'hours_ahead': 1,
        'scope': 'place_density',
        'metric': 'population_density',
        'value': 0.0123,
        'crowd_level': 'NORMAL',
        'confidence_status': 'not_calibrated',
      },
      {
        ...validatedDensity(2),
        'hours_ahead': 2,
        'scope': 'place_density',
        'metric': 'population_density',
        'value': null,
        'crowd_level': null,
        'confidence_status': 'not_calibrated',
      },
    ];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: CrowdEvidence(estimate: CrowdEstimate.fromJson(data)),
          ),
        ),
      ),
    );
    expect(find.text('0.0123명/㎡'), findsOneWidget);
    expect(find.text('정보 부족'), findsOneWidget);
    expect(find.textContaining('TMAP · 장소의 평소 대비'), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });

  test('five levels remain separate from provider four levels', () {
    expect(EstimatedCrowdLevel.values.map((e) => e.label), [
      '매우 여유',
      '여유',
      '보통',
      '혼잡',
      '매우 혼잡',
    ]);
    final p = Place.fromJson({
      'id': 1,
      'name': '해변',
      'latest_crowd': {'score': 90, 'level': 'crowded'},
      'crowd_estimate': payload(),
    });
    expect(p.crowdScore, 10);
    expect(p.crowdText, contains('예상 매우 여유'));
    expect(p.crowdText, contains('낮은 신뢰도'));
    final old = Place.fromJson({
      'id': 2,
      'name': '구버전',
      'latest_crowd': {
        'score': 75,
        'level': 'busy',
        'source': 'seoul_realtime',
      },
    });
    expect(old.crowdLevel, CrowdLevel.busy);
    expect(old.crowdEstimate, isNull);
  });

  test(
    'recommendation shrinks weak crowd evidence and excludes demo closed stale',
    () {
      Place p(int id, Map<String, dynamic> json) => Place(
        id: id,
        name: 'test',
        crowdEstimate: CrowdEstimate.fromJson(json),
      );
      const engine = RecommendationEngine();
      final results = engine.recommend(
        places: [p(1, payload(confidence: .9)), p(2, payload())],
        preference: const UserPreference(crowdTolerance: 0),
      );
      expect(results.first.place.id, 1);
      for (final data in [
        payload(demo: true),
        payload(stale: true),
        payload(open: 'CLOSED'),
        {'status': 'unavailable'},
      ]) {
        expect(p(3, data).canUseCrowd, isFalse);
      }
      expect(p(3, payload(demo: true)).isDemo, isTrue);
    },
  );

  testWidgets('narrow card and evidence show weak quality without overflow', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 780);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final estimate = CrowdEstimate.fromJson(payload(demo: true, stale: true));
    final place = Place(
      id: 1,
      name: '아주 긴 이름의 관광지 혼잡도 확인',
      crowdEstimate: estimate,
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: Column(
              children: [
                PlaceCard(place: place, onTap: () {}),
                CrowdEvidence(estimate: estimate),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('낮은 신뢰도'), findsWidgets);
    expect(find.textContaining('주변 영역'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
