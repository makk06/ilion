import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_map_vector_tiles/flutter_map_vector_tiles.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('simple map style compiles every layer and omits distracting features',
      () async {
    final style =
        jsonDecode(await rootBundle.loadString('assets/maps/simple.json'))
            as Map<String, dynamic>;
    final layers = (style['layers'] as List).cast<Map<String, dynamic>>();
    final theme = const ThemeReader().read(style);
    // ThemeReader tolerates invalid layers by skipping them; check none vanished.
    expect(theme.layers.length, layers.length);
    expect(theme.layers, isNotEmpty);
    final sourceLayers = theme.referencedSourceLayers.values.expand((v) => v);
    expect(sourceLayers, isNot(contains('poi')));
    expect(sourceLayers, contains('building'));
    expect(
        theme.layers
            .whereType<FillThemeLayer>()
            .any((layer) => layer.sourceLayer == 'building'),
        isTrue);
    expect(
        theme.layers
            .whereType<LineThemeLayer>()
            .any((layer) => layer.sourceLayer == 'building'),
        isTrue);
    expect(sourceLayers, contains('transportation_name'));
    final labels = layers.where((layer) => layer['type'] == 'symbol');
    expect(labels, isNotEmpty);
    expect(labels.every((layer) =>
        ['place', 'transportation_name'].contains(layer['source-layer'])), isTrue);

    final water = theme.layers.whereType<FillThemeLayer>().firstWhere(
          (layer) => layer.sourceLayer == 'water',
        );
    final green = theme.layers.whereType<FillThemeLayer>().firstWhere(
          (layer) =>
              ['landcover', 'landuse', 'park'].contains(layer.sourceLayer),
        );
    const context = EvalContext(zoom: 13);
    expect(water.color.eval(context), isNot(green.color.eval(context)));
    expect(water.color.eval(context), isNot(theme.backgroundColor(13)));
    expect(green.color.eval(context), isNot(theme.backgroundColor(13)));
  });
}
