import 'package:flutter_test/flutter_test.dart';
import 'package:tourist_congestion_frontend/src/services/region_filter.dart';
void main() {
 test('nested regions match exact address components and province aliases', () {
  expect(matchesRegionPath('경기 수원시 팔달구 정조로 1', '경기도/수원시/팔달구'), isTrue);
  expect(matchesRegionPath('경기도 수원시 영통구 1', '경기도/수원시/팔달구'), isFalse);
  expect(matchesRegionPath('경기도 수원시 팔달구 1', '경기도/수원시'), isTrue);
  expect(matchesRegionPath('서울 종로구 1', '서울특별시/종로구'), isTrue);
  expect(matchesRegionPath('경기도 수원시 팔달구 1', '경기도/수원'), isFalse);
  expect(matchesRegionPath('', '서울특별시'), isFalse);
  expect(matchesRegionPath('', ''), isTrue);
 });
}
