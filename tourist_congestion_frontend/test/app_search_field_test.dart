import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/widgets/app_chrome.dart';

void main() {
  testWidgets('search clears query and restores keyboard focus',
      (tester) async {
    final controller = TextEditingController(text: '서울');
    var cleared = false;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AppSearchField(
                controller: controller,
                hintText: '검색',
                onClear: () => cleared = true))));
    await tester.tap(find.byTooltip('검색어 지우기'));
    await tester.pump();
    expect(controller.text, isEmpty);
    expect(cleared, isTrue);
    expect(tester.widget<TextField>(find.byType(TextField)).focusNode!.hasFocus,
        isTrue);
    expect(find.byTooltip('검색어 지우기'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    controller.dispose();
  });
}
