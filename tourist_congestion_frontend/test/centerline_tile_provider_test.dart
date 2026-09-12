import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_map_vector_tiles/flutter_map_vector_tiles.dart' as vt;
import 'package:tourist_congestion_frontend/src/services/centerline_tile_provider.dart';

List<int> vint(int v) {
  final out = <int>[];
  while (v > 127) {
    out.add((v & 127) | 128);
    v >>= 7;
  }
  return [...out, v];
}

List<int> field(int n, List<int> bytes) =>
    [...vint((n << 3) | 2), ...vint(bytes.length), ...bytes];
List<int> scalar(int n, int v) => [...vint(n << 3), ...vint(v)];
int zig(int v) => v < 0 ? -2 * v - 1 : v * 2;
List<int> line(int x, int y, int dy) =>
    [9, zig(x), zig(y), 10, 0, zig(dy)].expand(vint).toList();
List<int> feature(int x, int y, int dy) => [
      ...field(2, [0, 0, 1, 1, 2, 2]),
      ...scalar(3, 2),
      ...field(4, line(x, y, dy))
    ];
Uint8List fixture() => Uint8List.fromList([
      ...field(3, [
        ...field(1, utf8.encode('building')),
        ...scalar(15, 2),
        ...scalar(5, 4096)
      ]),
      ...field(3, [
        ...field(1, utf8.encode('transportation')),
        ...field(2, feature(1000, 1000, 1000)),
        ...field(2, feature(1040, 2000, -1000)),
        ...field(3, utf8.encode('class')),
        ...field(3, utf8.encode('name')),
        ...field(3, utf8.encode('oneway')),
        ...field(4, field(1, utf8.encode('primary'))),
        ...field(4, field(1, utf8.encode('같은 도로'))),
        ...field(4, scalar(5, 1)),
        ...scalar(15, 2),
        ...scalar(5, 4096)
      ]),
    ]);

class Source extends vt.VectorTileProvider {
  Source(this.response);
  final vt.TileResponse response;
  bool disposed = false;
  @override
  int get minimumZoom => 0;
  @override
  int get maximumZoom => 14;
  @override
  String get cacheKey => 'test';
  @override
  bool get cacheBytesToDisk => false;
  @override
  Future<vt.TileResponse> load(vt.TileKey tile,
          {vt.CancellationToken? cancellation}) async =>
      response;
  @override
  void dispose() => disposed = true;
}

void main() {
  test('parallel roads merge while unrelated layer bytes stay exact', () {
    final original = fixture();
    final transformed =
        centerlineTileBytes(original, const vt.TileKey(14, 13970, 6344));
    expect(transformed, isNot(orderedEquals(original)));
    final building = field(3, [
      ...field(1, utf8.encode('building')),
      ...scalar(15, 2),
      ...scalar(5, 4096)
    ]);
    expect(transformed.take(building.length), orderedEquals(building));
    // Two source lines at x=1000 and 1040 become a genuine midpoint geometry.
    final midpoint = [9, ...vint(zig(1020)), ...vint(zig(1000))];
    bool found = false;
    for (int i = 0; i <= transformed.length - midpoint.length; i++) {
      if (List.generate(
              midpoint.length, (n) => transformed[i + n] == midpoint[n])
          .every((v) => v)) {
        found = true;
      }
    }
    expect(found, isTrue);
  });
  test('invalid MVT falls back unchanged', () {
    final bytes = Uint8List.fromList([255]);
    expect(centerlineTileBytes(bytes, const vt.TileKey(14, 13970, 6344)),
        same(bytes));
  });
  test('provider uses separate cache and forwards absence/disposal', () async {
    final source = Source(const vt.TileResponseNotFound());
    final provider = CenterlineTileProvider(source);
    expect(provider.cacheKey, 'test:centerline-v1');
    expect(provider.maximumZoom, 14);
    expect(provider.cacheBytesToDisk, isFalse);
    expect(
        await provider.load(const vt.TileKey(14, 1, 1)), same(source.response));
    provider.dispose();
    expect(source.disposed, isTrue);
  });
  test('real fixture transforms if supplied for integration diagnostics', () {
    final source = File('../.integration-artifacts/roads-real.pbf');
    if (!source.existsSync()) return;
    final stopwatch = Stopwatch()..start();
    final bytes = centerlineTileBytes(
        source.readAsBytesSync(), const vt.TileKey(14, 13970, 6344));
    stopwatch.stop();
    // ignore: avoid_print
    print('Real centerline tile: ${stopwatch.elapsedMilliseconds}ms');
    File('../.integration-artifacts/roads-merged.pbf').writeAsBytesSync(bytes);
    expect(bytes, isNotEmpty);
  });
}
