import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tourist_congestion_frontend/src/screens/personalized_recommendations_screen.dart';
import 'package:tourist_congestion_frontend/src/services/api_client.dart';
import 'package:tourist_congestion_frontend/src/services/app_session.dart';
import 'package:tourist_congestion_frontend/src/state/app_scope.dart';
import 'package:tourist_congestion_frontend/src/theme/app_theme.dart';
import 'package:tourist_congestion_frontend/src/widgets/recommendation_card.dart';
import 'hourly_decision_test.dart' as fixture;

void main() {
  testWidgets(
    'exact visit selection, provider groups, missing data and expiry never select now silently',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final screenshots = Platform.environment['DECISION_SCREENSHOTS'];
      if (screenshots != null) {
        await tester.runAsync(() async {
          final icons = File(
            'C:/Users/poplo/development/flutter/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
          );
          if (await icons.exists()) {
            await (FontLoader('MaterialIcons')..addFont(
                  Future.value(ByteData.sublistView(await icons.readAsBytes())),
                ))
                .load();
          }
          final font = File('C:/Windows/Fonts/malgun.ttf');
          if (await font.exists()) {
            final loader = FontLoader('DecisionQA')
              ..addFont(
                Future.value(ByteData.sublistView(await font.readAsBytes())),
              );
            await loader.load();
          }
        });
      }
      Future<void> capture(String name) async {
        if (screenshots == null) return;
        await tester.runAsync(() async {
          final boundary = tester.renderObject<RenderRepaintBoundary>(
            find.byKey(const ValueKey('capture')),
          );
          final image = await boundary.toImage();
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          final path = File('$screenshots/$name.png');
          await path.parent.create(recursive: true);
          await path.writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
      }

      FlutterSecureStorage.setMockInitialValues({});
      AppSession.instance = AppSession();
      await AppSession.instance.restore();
      var clock = fixture.now;
      final forecasts = [
        fixture.forecast(20),
        fixture.forecast(80),
        {
          ...fixture.forecast(10),
          'provider': 'tmap',
          'metric': 'population_density',
          'unit': 'persons_per_m2',
          'scope': 'place_density',
        },
        null,
      ];
      final places = [
        for (var i = 0; i < 4; i++)
          {
            'id': i + 1,
            'name': ['경복궁 참고 구역', '북촌 참고 구역', '밀도 관측 장소', '예측 없는 장소'][i],
            'crowd_estimate': {
              'status': 'available',
              'crowd_score': 10,
              'crowd_level': 'LOW',
              'confidence': 1,
              'estimated_at': fixture.now.toIso8601String(),
              'forecast': forecasts[i] == null
                  ? []
                  : [
                      {...forecasts[i]!, 'external_id': '${i + 1}'},
                    ],
            },
          },
      ];
      ApiClient.instance = ApiClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({
              'success': true,
              'data': {
                'items': places,
                'pagination': {'page': 1, 'total_pages': 1},
              },
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          ),
        ),
      );
      await tester.pumpWidget(
        AppScope(
          child: MaterialApp(
            theme: screenshots == null
                ? AppTheme.light
                : AppTheme.light.copyWith(
                    chipTheme: AppTheme.light.chipTheme.copyWith(
                      labelStyle: AppTheme.light.chipTheme.labelStyle?.copyWith(
                        fontFamily: 'DecisionQA',
                      ),
                    ),
                    textTheme: AppTheme.light.textTheme.apply(
                      fontFamily: 'DecisionQA',
                    ),
                  ),
            home: RepaintBoundary(
              key: const ValueKey('capture'),
              child: PersonalizedRecommendationsScreen(clock: () => clock),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ChoiceChip, '오늘 13:00'));
      await tester.pumpAndSettle();
      final visible = tester
          .widgetList<RecommendationCard>(find.byType(RecommendationCard))
          .toList();
      expect(
        visible.every(
          (c) => c.recommendation.visitAt!.isAtSameMomentAs(fixture.visit),
        ),
        isTrue,
      );
      await capture('visit-selected');
      await tester.tap(find.byTooltip('추천 정렬'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('평소 대비 한산한 순').last);
      await tester.pumpAndSettle();
      expect(find.textContaining('그룹 간 실제 밀집도 순서가 아닙니다'), findsOneWidget);
      await capture('provider-groups');
      clock = fixture.visit.add(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 31));
      await tester.pumpAndSettle();
      expect(find.textContaining('방문 시각을 다시 선택'), findsOneWidget);
      expect(
        tester
            .widget<ChoiceChip>(find.widgetWithText(ChoiceChip, '지금'))
            .selected,
        isFalse,
      );
      await capture('visit-expired');
      expect(tester.takeException(), isNull);
    },
  );
}
