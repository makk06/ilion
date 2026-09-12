import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/app.dart';

void main() {
  testWidgets('앱이 홈 탭으로 시작하고 하단 탭이 모두 보인다', (tester) async {
    await tester.pumpWidget(const CrowdTripApp());
    await tester.pumpAndSettle();

    expect(find.text('홈'), findsOneWidget);
    expect(find.text('추천'), findsOneWidget);
    expect(find.text('저장'), findsOneWidget);
    expect(find.text('마이'), findsOneWidget);
    expect(find.text('어디로 떠나볼까요?'), findsOneWidget);
  });

  testWidgets('추천 탭에서 저장하면 저장 탭 목록과 뱃지에 반영된다', (tester) async {
    await tester.pumpWidget(const CrowdTripApp());
    await tester.pumpAndSettle();

    // 저장 탭: 처음에는 비어 있다.
    await tester.tap(find.text('저장'));
    await tester.pumpAndSettle();
    expect(find.text('아직 저장한 장소가 없어요'), findsOneWidget);

    // 추천 탭에서 첫 번째 추천 카드를 저장한다.
    await tester.tap(find.text('추천'));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.favorite_border_rounded).first);
    await tester.pumpAndSettle();

    // 저장 탭에 목록이 생기고 탭 뱃지가 1이 된다.
    await tester.tap(find.text('저장'));
    await tester.pumpAndSettle();
    expect(find.text('아직 저장한 장소가 없어요'), findsNothing);
    expect(find.text('1곳을 저장했어요'), findsOneWidget);
  });

  testWidgets('저장 탭에서 저장을 해제하면 되돌리기로 복구할 수 있다', (tester) async {
    await tester.pumpWidget(const CrowdTripApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('추천'));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.favorite_border_rounded).first);
    await tester.pumpAndSettle();

    await tester.tap(find.text('저장'));
    await tester.pumpAndSettle();
    expect(find.text('1곳을 저장했어요'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.favorite_rounded).first);
    await tester.pumpAndSettle();
    expect(find.text('아직 저장한 장소가 없어요'), findsOneWidget);

    await tester.tap(find.text('되돌리기'));
    await tester.pumpAndSettle();
    expect(find.text('1곳을 저장했어요'), findsOneWidget);
  });

  testWidgets('마이페이지에서 바꾼 취향이 추천 탭 요약에 반영된다', (tester) async {
    await tester.pumpWidget(const CrowdTripApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('마이'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('여행 취향 설정'));
    await tester.pumpAndSettle();

    expect(find.text('여행 취향 설정'), findsWidgets);
    await tester.tap(find.text('실내 선호'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('이 취향으로 추천받기'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('추천'));
    await tester.pumpAndSettle();
    expect(find.textContaining('실내 선호'), findsWidgets);
  });
}
