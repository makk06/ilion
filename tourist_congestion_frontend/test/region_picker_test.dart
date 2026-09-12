import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/widgets/region_picker.dart';

Map<String, dynamic> node(String name, String path,
        [List<Map<String, dynamic>> children = const []]) =>
    {'name': name, 'path': path, 'children': children};

void main() {
  var calls = 0;
  var failFirst = false;
  setUp(() {
    calls = 0;
    failFirst = false;
    ApiClient.instance = ApiClient(client: MockClient((request) async {
      expect(request.url.path, '/api/places/regions');
      calls++;
      if (failFirst && calls == 1) {
        return http.Response('{"success":false,"message":"Unavailable"}', 503);
      }
      return http.Response(
          jsonEncode({
            'success': true,
            'data': {
              'items': [
                node('경기도', '경기도', [
                  node('수원시', '경기도/수원시', [
                    node('영통구', '경기도/수원시/영통구'),
                  ]),
                  node('용인시', '경기도/용인시'),
                ]),
              ]
            }
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
  });

  Future<void> open(WidgetTester tester, ValueChanged<String?> result,
      {String selected = ''}) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(
        home: Builder(
            builder: (context) => Scaffold(
                body: TextButton(
                    onPressed: () async => result(
                        await showModalBottomSheet<String>(
                            context: context,
                            isScrollControlled: true,
                            builder: (_) => RegionPicker(selected: selected))),
                    child: const Text('지역 열기'))))));
    await tester.tap(find.text('지역 열기'));
    await tester.pumpAndSettle();
  }

  testWidgets('three-level selection returns the full slash-separated path',
      (tester) async {
    String? result;
    await open(tester, (value) => result = value);
    for (final region in ['경기도', '수원시', '영통구']) {
      await tester.tap(find.widgetWithText(ListTile, region));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('영통구 선택'));
    await tester.pumpAndSettle();
    expect(result, '경기도/수원시/영통구');
    expect(tester.takeException(), isNull);
  });

  testWidgets('parent breadcrumb clears selected descendants', (tester) async {
    String? result;
    await open(tester, (value) => result = value, selected: '경기도/수원시/영통구');
    await tester.tap(find.widgetWithText(TextButton, '경기도'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextButton, '수원시'), findsNothing);
    expect(find.text('영통구'), findsNothing);
    expect(find.widgetWithText(ListTile, '용인시'), findsOneWidget);
    await tester.tap(find.text('경기도 선택'));
    await tester.pumpAndSettle();
    expect(result, '경기도');
    expect(tester.takeException(), isNull);
  });

  testWidgets('closing the sheet cancels without returning a selection',
      (tester) async {
    String? result = 'unchanged';
    await open(tester, (value) => result = value);
    await tester.tap(find.widgetWithText(ListTile, '경기도'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('닫기'));
    await tester.pumpAndSettle();
    expect(result, isNull);
    expect(find.byType(RegionPicker), findsNothing);
  });

  testWidgets('failed region request retries and displays server regions',
      (tester) async {
    failFirst = true;
    await open(tester, (_) {});
    expect(find.text('다시 시도'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
        isNull);
    await tester.tap(find.text('다시 시도'));
    await tester.pumpAndSettle();
    expect(calls, 2);
    expect(find.widgetWithText(ListTile, '경기도'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
