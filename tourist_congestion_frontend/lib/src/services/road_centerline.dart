import 'dart:math';

/// Geometry-only road representation in one tile's coordinate system.
class RoadLine {
  RoadLine(
      {required this.id,
      required this.points,
      this.name,
      this.ref,
      this.roadClass,
      this.layer,
      this.bridge = false,
      this.tunnel = false,
      this.oneway = false,
      Set<String>? sourceIds})
      : sourceIds = sourceIds ?? {id};
  final String id;
  final List<Point<double>> points;
  final String? name, ref, roadClass, layer;
  final bool bridge, tunnel, oneway;
  final Set<String> sourceIds;
}

double _length(List<Point<double>> points) {
  var length = 0.0;
  for (var i = 1; i < points.length; i++) {
    length += points[i].distanceTo(points[i - 1]);
  }
  return length;
}

List<Point<double>> _samples(List<Point<double>> points, int count) {
  final total = _length(points);
  var segment = 1;
  var accumulated = 0.0;
  return List.generate(count, (index) {
    final target = total * index / (count - 1);
    while (segment < points.length - 1 &&
        accumulated + points[segment].distanceTo(points[segment - 1]) <
            target) {
      accumulated += points[segment].distanceTo(points[segment - 1]);
      segment++;
    }
    final start = points[segment - 1];
    final delta = points[segment] - start;
    final fraction = delta.magnitude == 0
        ? 0.0
        : ((target - accumulated) / delta.magnitude).clamp(0.0, 1.0);
    return start + delta * fraction;
  });
}

String _identity(String? value) => (value ?? '').trim().toLowerCase();

String _vertexKey(Point<double> point, RoadLine line) =>
    '${(point.x * 1000000).round()}:${(point.y * 1000000).round()}:'
    '${line.layer ?? '0'}:${line.bridge}:${line.tunnel}';

void _rememberVertices(RoadLine source, List<Point<double>> center,
    bool reversed, Map<String, Point<double>> moved) {
  final length = _length(source.points);
  var distance = 0.0;
  for (var i = 0; i < source.points.length; i++) {
    if (i > 0) distance += source.points[i].distanceTo(source.points[i - 1]);
    var fraction = length == 0 ? 0.0 : distance / length;
    if (reversed) fraction = 1 - fraction;
    final position =
        (fraction * (center.length - 1)).clamp(0.0, center.length - 1.0);
    final index = min(position.floor(), center.length - 2);
    final target = center[index] +
        (center[index + 1] - center[index]) * (position - index);
    moved.putIfAbsent(_vertexKey(source.points[i], source), () => target);
  }
}

bool _compatible(RoadLine a, RoadLine b) {
  final sameName =
      _identity(a.name).isNotEmpty && _identity(a.name) == _identity(b.name);
  final sameRef =
      _identity(a.ref).isNotEmpty && _identity(a.ref) == _identity(b.ref);
  return a.oneway &&
      b.oneway &&
      (sameName || sameRef) &&
      _identity(a.roadClass) == _identity(b.roadClass) &&
      _identity(a.layer ?? '0') == _identity(b.layer ?? '0') &&
      a.bridge == b.bridge &&
      a.tunnel == b.tunnel;
}

List<Point<double>>? _pair(RoadLine a, RoadLine b, double threshold) {
  if (!_compatible(a, b) || a.points.length < 2 || b.points.length < 2)
    return null;
  final aLength = _length(a.points), bLength = _length(b.points);
  // A small overlapping fragment must not replace an entire longer road.
  if (min(aLength, bLength) < threshold * 3 ||
      min(aLength, bLength) / max(aLength, bLength) < .85) return null;
  final direct = a.points.first.distanceTo(b.points.first) +
      a.points.last.distanceTo(b.points.last);
  final reverse = a.points.first.distanceTo(b.points.last) +
      a.points.last.distanceTo(b.points.first);
  final bPoints = reverse < direct ? b.points.reversed.toList() : b.points;
  final count =
      (max(aLength, bLength) / max(threshold / 2, .1)).ceil().clamp(12, 128);
  final left = _samples(a.points, count), right = _samples(bPoints, count);
  var sign = 0;
  var separationSum = 0.0;
  for (var i = 0; i < count; i++) {
    final offset = right[i] - left[i];
    if (offset.magnitude > threshold) return null;
    separationSum += offset.magnitude;
    if (i == count - 1) continue;
    final da = left[i + 1] - left[i], db = right[i + 1] - right[i];
    if (da.magnitude == 0 || db.magnitude == 0) continue;
    final dot = (da.x * db.x + da.y * db.y) / (da.magnitude * db.magnitude);
    if (dot < .94) return null;
    // Crossing lines change the side of separation, unlike carriageways.
    final cross = da.x * offset.y - da.y * offset.x;
    if (cross.abs() > da.magnitude * threshold * .02) {
      final current = cross > 0 ? 1 : -1;
      if (sign != 0 && sign != current) return null;
      sign = current;
    }
  }
  if (separationSum / count < threshold * .03 || sign == 0) return null;
  return List.generate(count, (i) => (left[i] + right[i]) * .5);
}

/// Conservatively replaces complete matched carriageway pairs with their
/// sampled midpoint geometry. Unmatched and ambiguous lines remain intact.
List<RoadLine> mergeRoadCenterlines(List<RoadLine> lines,
    {required double maxDistance}) {
  if (!maxDistance.isFinite || maxDistance <= 0) return List.of(lines);
  final used = <int>{};
  final result = <RoadLine>[];
  final movedVertices = <String, Point<double>>{};
  final mergedIds = <String>{};
  for (var i = 0; i < lines.length; i++) {
    if (used.contains(i)) continue;
    final candidates = <int, List<Point<double>>>{};
    for (var j = i + 1; j < lines.length; j++) {
      if (!used.contains(j)) {
        final geometry = _pair(lines[i], lines[j], maxDistance);
        if (geometry != null) candidates[j] = geometry;
      }
    }
    if (candidates.length != 1) {
      result.add(lines[i]);
      continue;
    }
    final partner = candidates.keys.single;
    // Don't greedily consume one branch in a group of parallel service roads.
    final competing = List.generate(lines.length, (v) => v).any((k) =>
        k != i &&
        k != partner &&
        !used.contains(k) &&
        _pair(lines[partner], lines[k], maxDistance) != null);
    if (competing) {
      result.add(lines[i]);
      continue;
    }
    used.add(partner);
    final a = lines[i], b = lines[partner];
    final center = candidates[partner]!;
    final direct = a.points.first.distanceTo(b.points.first) +
        a.points.last.distanceTo(b.points.last);
    final reverse = a.points.first.distanceTo(b.points.last) +
        a.points.last.distanceTo(b.points.first);
    _rememberVertices(a, center, false, movedVertices);
    _rememberVertices(b, center, reverse < direct, movedVertices);
    mergedIds.add(a.id);
    result.add(RoadLine(
        id: a.id,
        points: candidates[partner]!,
        name: a.name,
        ref: a.ref,
        roadClass: a.roadClass,
        layer: a.layer,
        bridge: a.bridge,
        tunnel: a.tunnel,
        oneway: false,
        sourceIds: {...a.sourceIds, ...b.sourceIds}));
  }
  // Branches retain topology: only vertices which actually shared an original
  // carriageway coordinate at the same grade move to that carriageway's center.
  return result.map((line) {
    if (mergedIds.contains(line.id)) return line;
    var changed = false;
    final points = line.points.map((point) {
      final target = movedVertices[_vertexKey(point, line)];
      if (target == null) return point;
      changed = changed || target != point;
      return target;
    }).toList();
    if (!changed) return line;
    return RoadLine(
        id: line.id,
        points: points,
        name: line.name,
        ref: line.ref,
        roadClass: line.roadClass,
        layer: line.layer,
        bridge: line.bridge,
        tunnel: line.tunnel,
        oneway: line.oneway,
        sourceIds: line.sourceIds);
  }).toList();
}
