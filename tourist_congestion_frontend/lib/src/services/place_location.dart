import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/place.dart';

// Release policy: manual region/place selection only. Keep the implementation
// for later review; do not enable via a build/environment override.
const deviceLocationEnabled = false;

Future<Position> locateUser() async {
  // Guard before *any* platform call, even if a future caller bypasses the UI.
  if (!deviceLocationEnabled) {
    throw StateError('현재 위치 기능은 제공하지 않습니다. 지역을 직접 선택해 주세요.');
  }
  if (!await Geolocator.isLocationServiceEnabled()) {
    throw Exception('기기의 위치 서비스를 켜주세요. 지역 검색으로도 탐색할 수 있어요.');
  }
  var permission = await Geolocator.checkPermission();
  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
  }
  if (permission == LocationPermission.denied ||
      permission == LocationPermission.deniedForever) {
    throw Exception('위치 권한이 없습니다. 지역 검색을 이용해주세요.');
  }
  return Geolocator.getCurrentPosition(
      locationSettings:
          const LocationSettings(timeLimit: Duration(seconds: 15)));
}

Future<void> openPlaceDirections(BuildContext context, Place place) async {
  final uri = Uri.https('map.kakao.com',
      '/link/to/${place.name},${place.latitude},${place.longitude}');
  try {
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      throw Exception('지도 앱을 열 수 없습니다.');
    }
  } catch (error) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('길찾기를 열지 못했습니다: $error')));
    }
  }
}
