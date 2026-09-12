import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/models/place.dart';
import 'package:tourist_congestion_frontend/src/widgets/place_map.dart';

void main() {
  testWidgets('zoom buttons and mouse wheel change the actual map camera',
      (tester) async {
    final controller = MapController();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SizedBox(
          height: 320,
          child: PlacesMap(
            controller: controller,
            places: const [
              Place(id: 1, name: '제주 장소', latitude: 33.4, longitude: 126.9),
            ],
            selectedId: 1,
            onSelected: (_) {},
          ),
        ),
      ),
    ));
    await tester.pump();
    final tileLayer = tester.widget<TileLayer>(find.byType(TileLayer));
    expect(tileLayer.tileDimension, 128);
    expect(tileLayer.zoomOffset, 1);
    expect(tileLayer.maxNativeZoom, 18);
    expect(tileLayer.maxZoom, 18);
    final initialZoom = controller.camera.zoom;
    await tester.tap(find.byTooltip('지도 확대'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(controller.camera.zoom, greaterThan(initialZoom));
    expect(controller.camera.zoom, lessThan(initialZoom + 1));
    await tester.pump(const Duration(milliseconds: 140));
    expect(controller.camera.zoom, closeTo(initialZoom + 1, 0.001));
    await tester.tap(find.byTooltip('지도 축소'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 240));
    expect(controller.camera.zoom, closeTo(initialZoom, 0.001));

    await tester.sendEventToBinding(PointerScrollEvent(
      position:
          tester.getTopLeft(find.byType(FlutterMap)) + const Offset(100, 100),
      scrollDelta: const Offset(0, -100),
      kind: PointerDeviceKind.mouse,
    ));
    await tester.pumpAndSettle();
    expect(controller.camera.zoom, greaterThan(initialZoom));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });
}
