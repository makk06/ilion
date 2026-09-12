import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/screens/companion_detail_screen.dart';
import 'package:tourist_congestion_frontend/src/theme/app_theme.dart';

void main() {
  testWidgets('undecided date and time allow joining', (tester) async {
    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light,
        home: const CompanionDetailScreen(companion: {
          'id': 1,
          'title': '일정은 함께 정해요',
          'text': '동행 모집',
          'author_nickname': '모집자',
          'place_name': '서울',
          'date': null,
          'time': null,
          'member_count': 1,
          'capacity': 3,
        })));
    await tester.pumpAndSettle();
    expect(find.text('날짜 미정'), findsOneWidget);
    expect(find.text('시간 미정'), findsOneWidget);
    expect(
        tester
            .widget<FilledButton>(find.widgetWithText(FilledButton, '동행 신청하기'))
            .onPressed,
        isNotNull);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
      'long recruitment content wraps and action stays reachable on narrow screen',
      (tester) async {
    tester.view.physicalSize = const Size(360, 780);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light,
        builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context)
                .copyWith(textScaler: const TextScaler.linear(1.3)),
            child: child!),
        home: CompanionDetailScreen(companion: {
          'id': 1,
          'title': '경복궁에서 천천히 걸으며 사진 찍을 동행을 찾습니다',
          'author_nickname': '여행하는사람',
          'place_name': '서울특별시 종로구 경복궁 광화문 앞',
          'date': '2099-09-16',
          'member_count': 1,
          'capacity': 4,
          'text': List.filled(20, '천천히 산책하면서 함께 이야기 나누어요.').join('\n'),
        })));
    await tester.pump();
    expect(tester.takeException(), isNull);
    final button = find.widgetWithText(FilledButton, '동행 신청하기');
    expect(tester.getBottomRight(button).dy, lessThanOrEqualTo(780));
    await tester.drag(find.byType(ListView), const Offset(0, -500));
    await tester.pumpAndSettle();
    expect(button.hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
