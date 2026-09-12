import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/screens/place_detail_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';
import 'package:tourist_congestion_frontend/src/theme/app_theme.dart';

void main() {
  testWidgets(
      'detail tabs pin, jump beneath header and follow manual scrolling',
      (tester) async {
    tester.view.physicalSize = const Size(390, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    FlutterSecureStorage.setMockInitialValues({});
    ApiClient.instance = ApiClient(
        client: MockClient((request) async => http.Response(
            jsonEncode({
              'success': true,
              'data': request.url.path.endsWith('/places/7')
                  ? {
                      'id': 7,
                      'name': '경복궁',
                      'description': List.filled(12, '궁궐 소개입니다.').join('\n'),
                      'address': '서울 종로구'
                    }
                  : {'items': []}
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'})));
    AppSession.instance = AppSession();
    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light,
        home: const PlaceDetailScreen(place: Place(id: 7, name: '경복궁'))));
    await tester.pumpAndSettle();
    expect(find.text('카카오맵 길찾기'), findsOneWidget);
    expect(find.text('지금의 혼잡도'), findsOneWidget);
    final tabs = find.text('장소소개').first;
    final scroll = tester
        .widget<CustomScrollView>(find.byType(CustomScrollView))
        .controller!;
    expect(tester.getTopLeft(tabs).dy, greaterThan(64));
    scroll.jumpTo(500);
    await tester.pumpAndSettle();
    final introOffset = scroll.offset;
    final pinnedTop = tester.getTopLeft(find.text('후기')).dy;
    await tester.tap(find.text('이용정보').first);
    await tester.pumpAndSettle();
    expect(
        tester.getTopLeft(find.text('이용정보').last).dy, closeTo(64 + 52 + 28, 2));
    expect(tester.getTopLeft(find.text('후기')).dy, closeTo(pinnedTop, 2));
    await tester.tap(find.text('후기'));
    await tester.pumpAndSettle();
    expect(find.text('후기 작성').hitTestable(), findsOneWidget);
    await tester.tap(find.text('장소소개').first);
    await tester.pumpAndSettle();
    expect(
        tester.getTopLeft(find.text('장소소개').last).dy, closeTo(64 + 52 + 28, 2));
    scroll.jumpTo(introOffset);
    await tester.pumpAndSettle();
    expect(tester.widget<Text>(find.text('장소소개').first).style?.fontWeight,
        FontWeight.w700);
    scroll.jumpTo(0);
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(tabs).dy, greaterThan(64));
    expect(tester.takeException(), isNull);
  });
}
