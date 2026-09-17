import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../lib/src/models/crowd_estimate.dart';
import '../lib/src/models/event_context.dart';
import '../lib/src/widgets/event_notice.dart';

void main() {
  test('exact selected hour only; legacy responses remain valid', () {
    final estimate = CrowdEstimate.fromJson({'event_contexts': [{'valid_at':'2026-09-16T13:00:00+09:00','events':[]} ]});
    expect(estimate.eventsAt(DateTime.parse('2026-09-16T04:00:00Z')), isNotNull);
    expect(estimate.eventsAt(DateTime.parse('2026-09-16T05:00:00Z')), isNull);
    expect(CrowdEstimate.fromJson({}).eventContext,isNull);
  });
  testWidgets('date-only and stale advice works without a numeric forecast', (tester) async {
    final data=EventContext.fromJson({'collection_status':'delayed','events':[{'name':'축제','message':'이날 행사 예정 · 진행 시간 미확인','source':'tour_api'}]});
    await tester.pumpWidget(MaterialApp(home:Scaffold(body:EventNoticeView(contextData:data))));
    expect(find.text('축제'),findsOneWidget);
    expect(find.textContaining('진행 시간 미확인'),findsOneWidget);
    expect(find.textContaining('확인 지연'),findsOneWidget);
    expect(tester.takeException(),isNull);
  });
}
