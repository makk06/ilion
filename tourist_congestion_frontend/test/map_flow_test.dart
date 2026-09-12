import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/screens/map_screen.dart';
import 'package:tourist_congestion_frontend/src/widgets/place_card.dart';

void main() {
  testWidgets(
      'map list selection survives switching and returns selected ID on back',
      (tester) async {
    tester.view.physicalSize = const Size(1000, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    int? result;
    const places = [Place(id: 1, name: '첫 장소'), Place(id: 2, name: '두 번째 장소')];
    await tester.pumpWidget(MaterialApp(
        home: Builder(
            builder: (context) => Scaffold(
                body: TextButton(
                    onPressed: () async {
                      result = await Navigator.push<int>(
                          context,
                          MaterialPageRoute(
                              builder: (_) => const MapScreen(
                                  places: places, selectedId: 1)));
                    },
                    child: const Text('열기'))))));
    await tester.tap(find.text('열기'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    await tester.tap(find.text('리스트'));
    await tester.pump();
    await tester.tap(find.widgetWithText(PlaceCard, '두 번째 장소'));
    await tester.pump();
    expect(find.widgetWithText(PlaceCard, '두 번째 장소'), findsOneWidget);
    await tester.tap(find.text('리스트'));
    await tester.pump();
    await tester.tap(find.text('지도'));
    await tester.pump();
    expect(find.widgetWithText(PlaceCard, '두 번째 장소'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(result, 2);
    expect(find.byType(MapScreen), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
