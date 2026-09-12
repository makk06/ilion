import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/foundation.dart';
import 'package:flutter_map_vector_tiles/flutter_map_vector_tiles.dart' as vt;
import 'road_centerline.dart';

/// Rewrites road geometry before decoding, leaving every other MVT layer intact.
class CenterlineTileProvider extends vt.VectorTileProvider {
  CenterlineTileProvider(this.delegate);
  final vt.VectorTileProvider delegate;
  @override
  int get maximumZoom => delegate.maximumZoom;
  @override
  int get minimumZoom => delegate.minimumZoom;
  @override
  String get cacheKey => '${delegate.cacheKey}:centerline-v1';
  @override
  bool get cacheBytesToDisk => delegate.cacheBytesToDisk;
  @override
  Future<vt.TileResponse> load(vt.TileKey tile,
      {vt.CancellationToken? cancellation}) async {
    final response = await delegate.load(tile, cancellation: cancellation);
    if (response is! vt.TileResponseData || tile.z < 12) return response;
    final bytes = await compute(_transform, (response.bytes, tile));
    return vt.TileResponseData(bytes);
  }

  @override
  void dispose() => delegate.dispose();
}

Uint8List _transform((Uint8List, vt.TileKey) input) =>
    centerlineTileBytes(input.$1, input.$2);

class _Wire {
  _Wire(this.number, this.type, this.raw, this.payload, this.value);
  final int number, type;
  final Uint8List raw, payload;
  final int? value;
}

class _Reader {
  _Reader(this.bytes);
  final Uint8List bytes;
  int offset = 0;
  int integer() {
    int result = 0, shift = 0;
    while (offset < bytes.length && shift < 70) {
      final b = bytes[offset++];
      result |= (b & 127) << shift;
      if (b < 128) return result;
      shift += 7;
    }
    throw const FormatException('Invalid protobuf varint');
  }

  List<_Wire> fields() {
    final result = <_Wire>[];
    while (offset < bytes.length) {
      final start = offset;
      final tag = integer(), number = tag >> 3, type = tag & 7;
      int? value;
      int payloadStart = offset, end;
      switch (type) {
        case 0:
          value = integer();
          end = offset;
        case 1:
          end = offset + 8;
          offset = end;
        case 2:
          final length = integer();
          payloadStart = offset;
          end = offset + length;
          offset = end;
        case 5:
          end = offset + 4;
          offset = end;
        default:
          throw const FormatException('Unsupported protobuf wire type');
      }
      if (number == 0 || end > bytes.length || end < payloadStart) {
        throw const FormatException('Invalid protobuf field');
      }
      result.add(_Wire(number, type, Uint8List.sublistView(bytes, start, end),
          Uint8List.sublistView(bytes, payloadStart, end), value));
    }
    return result;
  }
}

List<int> _varint(int value) {
  if (value < 0) throw const FormatException('Negative unsigned value');
  final result = <int>[];
  while (value > 127) {
    result.add((value & 127) | 128);
    value >>= 7;
  }
  result.add(value);
  return result;
}

Uint8List _message(int field, List<int> payload) => Uint8List.fromList(
    [..._varint((field << 3) | 2), ..._varint(payload.length), ...payload]);
List<int> _packed(Uint8List bytes) {
  final reader = _Reader(bytes), result = <int>[];
  while (reader.offset < bytes.length) {
    result.add(reader.integer());
  }
  return result;
}

Object? _value(Uint8List bytes) {
  final fields = _Reader(bytes).fields();
  if (fields.isEmpty) return null;
  final field = fields.first;
  return switch (field.number) {
    1 => utf8.decode(field.payload),
    2 => ByteData.sublistView(field.payload).getFloat32(0, Endian.little),
    3 => ByteData.sublistView(field.payload).getFloat64(0, Endian.little),
    4 || 5 => field.value,
    6 => _unzig(field.value ?? 0),
    7 => field.value == 1,
    _ => null,
  };
}

int _unzig(int value) => (value >> 1) ^ -(value & 1);
int _zig(int value) => value < 0 ? -value * 2 - 1 : value * 2;

class _Feature {
  _Feature(this.fields, this.properties, this.lines);
  final List<_Wire> fields;
  final Map<String, Object?> properties;
  final List<List<math.Point<double>>> lines;
}

class _Layer {
  _Layer(this.fields) {
    name = utf8.decode(fields.firstWhere((f) => f.number == 1).payload);
    extent = fields.where((f) => f.number == 5).firstOrNull?.value ?? 4096;
    final keys = fields
        .where((f) => f.number == 3)
        .map((f) => utf8.decode(f.payload))
        .toList();
    final values = fields
        .where((f) => f.number == 4)
        .map((f) => _value(f.payload))
        .toList();
    for (final wire in fields.where((f) => f.number == 2)) {
      final parts = _Reader(wire.payload).fields();
      final tags = parts
          .where((p) => p.number == 2)
          .expand((p) => p.type == 2 ? _packed(p.payload) : [p.value!])
          .toList();
      final props = <String, Object?>{};
      if (tags.length.isOdd) throw const FormatException('Odd MVT tags');
      for (int i = 0; i < tags.length; i += 2) {
        props[keys[tags[i]]] = values[tags[i + 1]];
      }
      final type = parts.where((p) => p.number == 3).firstOrNull?.value;
      final geometry = parts
          .where((p) => p.number == 4)
          .expand((p) => p.type == 2 ? _packed(p.payload) : [p.value!])
          .toList();
      features
          .add(_Feature(parts, props, type == 2 ? _decodeLines(geometry) : []));
    }
  }
  final List<_Wire> fields;
  late final String name;
  late final int extent;
  final features = <_Feature>[];
}

List<List<math.Point<double>>> _decodeLines(List<int> geometry) {
  final lines = <List<math.Point<double>>>[];
  int x = 0, y = 0, i = 0;
  while (i < geometry.length) {
    final command = geometry[i++], id = command & 7, count = command >> 3;
    if (count == 0 || (id != 1 && id != 2)) {
      throw const FormatException('Invalid line command');
    }
    for (int n = 0; n < count; n++) {
      if (i + 1 >= geometry.length) {
        throw const FormatException('Truncated geometry');
      }
      x += _unzig(geometry[i++]);
      y += _unzig(geometry[i++]);
      if (id == 1) lines.add([]);
      if (lines.isEmpty) throw const FormatException('Missing MoveTo');
      lines.last.add(math.Point(x.toDouble(), y.toDouble()));
    }
  }
  return lines;
}

List<int> _encodeLines(List<List<math.Point<double>>> lines) {
  final result = <int>[];
  int x = 0, y = 0;
  for (final line in lines.where((l) => l.length >= 2)) {
    for (int i = 0; i < line.length; i++) {
      if (i == 0) result.add(9);
      if (i == 1) result.add(((line.length - 1) << 3) | 2);
      final nx = line[i].x.round(), ny = line[i].y.round();
      result.addAll([_zig(nx - x), _zig(ny - y)]);
      x = nx;
      y = ny;
    }
  }
  return result.expand(_varint).toList();
}

double _distanceToSegment(
    math.Point<double> p, math.Point<double> a, math.Point<double> b) {
  final dx = b.x - a.x, dy = b.y - a.y;
  final length = dx * dx + dy * dy;
  if (length == 0) return p.distanceTo(a);
  final t = (((p.x - a.x) * dx + (p.y - a.y) * dy) / length).clamp(0.0, 1.0);
  return p.distanceTo(math.Point(a.x + t * dx, a.y + t * dy));
}

Map<String, Object?> _roadIdentity(
    List<math.Point<double>> line,
    Map<String, Object?> properties,
    _Layer? names,
    double scale,
    double tolerance) {
  if (properties['name'] != null ||
      properties['ref'] != null ||
      names == null ||
      line.length < 2) {
    return properties;
  }
  final direction = line.last - line.first;
  final length =
      math.sqrt(direction.x * direction.x + direction.y * direction.y);
  if (length == 0) return properties;
  _Feature? match;
  double best = double.infinity;
  for (final candidate in names.features) {
    if (candidate.properties['class'] != properties['class']) continue;
    if (candidate.properties['name'] == null &&
        candidate.properties['ref'] == null) {
      continue;
    }
    for (final original in candidate.lines) {
      final named =
          original.map((p) => math.Point(p.x * scale, p.y * scale)).toList();
      if (named.length < 2) continue;
      final namedDirection = named.last - named.first;
      final namedLength = math.sqrt(namedDirection.x * namedDirection.x +
          namedDirection.y * namedDirection.y);
      if (namedLength == 0 ||
          ((direction.x * namedDirection.x + direction.y * namedDirection.y) /
                      length /
                      namedLength)
                  .abs() <
              .85) {
        continue;
      }
      double total = 0;
      for (final fraction in [.25, .5, .75]) {
        final p = line[(fraction * (line.length - 1)).round()];
        double nearest = double.infinity;
        for (int i = 1; i < named.length; i++) {
          nearest =
              math.min(nearest, _distanceToSegment(p, named[i - 1], named[i]));
        }
        total += nearest;
      }
      final score = total / 3;
      if (score < tolerance && score < best) {
        best = score;
        match = candidate;
      }
    }
  }
  return match == null
      ? properties
      : {
          ...properties,
          if (match.properties['name'] != null)
            'name': match.properties['name'],
          if (match.properties['ref'] != null) 'ref': match.properties['ref']
        };
}

/// Invalid/unsupported tiles are served unchanged, rather than losing map detail.
Uint8List centerlineTileBytes(Uint8List bytes, vt.TileKey tile) {
  try {
    final fields = _Reader(bytes).fields();
    _Layer? roads, names;
    _Wire? roadWire;
    for (final field in fields.where((f) => f.number == 3 && f.type == 2)) {
      final layerFields = _Reader(field.payload).fields();
      final name =
          utf8.decode(layerFields.firstWhere((f) => f.number == 1).payload);
      if (name == 'transportation') {
        roads = _Layer(layerFields);
        roadWire = field;
      }
      if (name == 'transportation_name') names = _Layer(layerFields);
    }
    if (roads == null || roadWire == null) return bytes;
    final mercator = math.pi * (1 - 2 * (tile.y + .5) / math.pow(2, tile.z));
    final latitudeRadians =
        math.atan((math.exp(mercator) - math.exp(-mercator)) / 2);
    final metersPerUnit = 40075016.686 *
        math.cos(latitudeRadians) /
        math.pow(2, tile.z) /
        roads.extent;
    final lines = <RoadLine>[];
    for (int feature = 0; feature < roads.features.length; feature++) {
      final original = roads.features[feature];
      if (original.properties['class'] == 'rail') continue;
      final ramp = original.properties['ramp'] == 1 ||
          original.properties['ramp'] == true;
      final oneway = !ramp &&
          (original.properties['oneway'] == 1 ||
              original.properties['oneway'] == -1 ||
              original.properties['oneway'] == true);
      for (int part = 0; part < original.lines.length; part++) {
        final points = original.lines[part];
        final properties = oneway
            ? _roadIdentity(
                points,
                original.properties,
                names,
                roads.extent / (names?.extent ?? roads.extent),
                10 / metersPerUnit)
            : original.properties;
        final brunnel = properties['brunnel'];
        lines.add(RoadLine(
            id: '$feature:$part',
            points: points,
            name: properties['name']?.toString(),
            ref: properties['ref']?.toString(),
            roadClass: properties['class']?.toString(),
            layer: properties['layer']?.toString() ?? '0',
            bridge: brunnel == 'bridge' || properties['bridge'] == true,
            tunnel: brunnel == 'tunnel' || properties['tunnel'] == true,
            oneway: oneway));
      }
    }
    final merged = mergeRoadCenterlines(lines, maxDistance: 32 / metersPerUnit);
    final originalById = {for (final line in lines) line.id: line};
    final changed = merged.where((line) {
      if (line.sourceIds.length > 1) return true;
      final original = originalById[line.id];
      if (original == null || original.points.length != line.points.length) {
        return true;
      }
      for (int i = 0; i < line.points.length; i++) {
        if (line.points[i] != original.points[i]) return true;
      }
      return false;
    }).toList();
    if (changed.isEmpty) return bytes;
    final replacement = <String, List<math.Point<double>>?>{};
    for (final line in changed) {
      for (final id in line.sourceIds) {
        replacement[id] = null;
      }
      replacement[line.id] = line.points;
    }
    int featureIndex = 0;
    final outputLayer = <int>[];
    for (final field in roads.fields) {
      if (field.number != 2) {
        outputLayer.addAll(field.raw);
        continue;
      }
      final index = featureIndex++, feature = roads.features[index];
      if (!replacement.keys.any((id) => id.startsWith('$index:'))) {
        outputLayer.addAll(field.raw);
        continue;
      }
      final geometry = <List<math.Point<double>>>[];
      for (int p = 0; p < feature.lines.length; p++) {
        final id = '$index:$p';
        if (!replacement.containsKey(id)) {
          geometry.add(feature.lines[p]);
        } else if (replacement[id] != null) {
          geometry.add(replacement[id]!);
        }
      }
      if (geometry.isEmpty) continue;
      final outputFeature = <int>[];
      bool geometryWritten = false;
      for (final part in feature.fields) {
        if (part.number != 4) {
          outputFeature.addAll(part.raw);
        } else if (!geometryWritten) {
          outputFeature.addAll(_message(4, _encodeLines(geometry)));
          geometryWritten = true;
        }
      }
      outputLayer.addAll(_message(2, outputFeature));
    }
    return Uint8List.fromList(fields
        .expand(
            (f) => identical(f, roadWire) ? _message(3, outputLayer) : f.raw)
        .toList());
  } catch (_) {
    return bytes;
  }
}
