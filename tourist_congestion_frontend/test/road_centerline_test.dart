import 'dart:math';
import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/services/road_centerline.dart';

void main() {
  test('unmerged branches follow shared endpoints and interior junctions', () {
    final a = RoadLine(id: 'a', name: 'Main', oneway: true, points: [
      const Point(0.0, 0.0),
      const Point(50.0, 0.0),
      const Point(100.0, 0.0)
    ]);
    final b = RoadLine(id: 'b', name: 'Main', oneway: true, points: [
      const Point(100.0, 6.0),
      const Point(50.0, 6.0),
      const Point(0.0, 6.0)
    ]);
    final branch = RoadLine(
        id: 'branch',
        points: [const Point(50.0, -30.0), const Point(50.0, 0.0)]);
    final extension = RoadLine(
        id: 'extension',
        points: [const Point(100.0, 6.0), const Point(130.0, 6.0)]);
    final bridge = RoadLine(id: 'bridge', bridge: true, points: branch.points);
    final result = mergeRoadCenterlines([a, b, branch, extension, bridge],
        maxDistance: 10);
    expect(result, hasLength(4));
    expect(result.singleWhere((line) => line.id == 'branch').points.last,
        const Point(50.0, 3.0));
    expect(result.singleWhere((line) => line.id == 'extension').points.first,
        const Point(100.0, 3.0));
    expect(result.singleWhere((line) => line.id == 'bridge').points.last,
        const Point(50.0, 0.0));
  });
  RoadLine line(String id, List<Point<double>> points,
          {String name = 'Main', String layer = '0', bool bridge = false}) =>
      RoadLine(
          id: id,
          points: points,
          name: name,
          roadClass: 'primary',
          layer: layer,
          bridge: bridge,
          oneway: true);
  final straight = [const Point(0.0, 0.0), const Point(100.0, 0.0)];
  final parallel = [const Point(0.0, 6.0), const Point(100.0, 6.0)];
  test('reversed carriageway becomes one midpoint with both sources', () {
    final result = mergeRoadCenterlines(
        [line('a', straight), line('b', parallel.reversed.toList())],
        maxDistance: 10);
    expect(result, hasLength(1));
    expect(result.single.sourceIds, {'a', 'b'});
    expect(result.single.points.every((point) => (point.y - 3).abs() < .001),
        isTrue);
  });
  test('curved parallel roads retain curved midpoint shape', () {
    final a = List.generate(21, (i) => Point(i * 5.0, 8 * sin(i / 20 * pi)));
    final b = a.map((p) => Point(p.x, p.y + 6)).toList();
    final result =
        mergeRoadCenterlines([line('a', a), line('b', b)], maxDistance: 10);
    expect(result, hasLength(1));
    expect(result.single.points.map((p) => p.y).reduce(max), greaterThan(10));
  });
  test('crossing diverging unrelated and grade-separated roads remain', () {
    for (final other in [
      line('b', [const Point(0.0, -4.0), const Point(100.0, 4.0)]),
      line('b', [const Point(0.0, 4.0), const Point(100.0, 30.0)]),
      line('b', parallel, name: 'Other'),
      line('b', parallel, layer: '1'),
      line('b', parallel, bridge: true),
      line('b', [const Point(80.0, 6.0), const Point(100.0, 6.0)]),
    ]) {
      expect(
          mergeRoadCenterlines([line('a', straight), other], maxDistance: 10),
          hasLength(2));
    }
  });
  test('three ambiguous parallel service lines are not consumed', () {
    final result = mergeRoadCenterlines([
      line('a', straight),
      line('b', parallel),
      line('c', [const Point(0.0, 3.0), const Point(100.0, 3.0)])
    ], maxDistance: 10);
    expect(result, hasLength(3));
  });
}
