import 'package:flutter/material.dart';

enum WeatherCondition {
  clear('맑음', Icons.wb_sunny_rounded, false),
  cloudy('흐림', Icons.cloud_rounded, false),
  rain('비', Icons.umbrella_rounded, true),
  snow('눈', Icons.ac_unit_rounded, true),
  hot('폭염', Icons.thermostat_rounded, true);

  const WeatherCondition(this.label, this.icon, this.prefersIndoor);

  final String label;
  final IconData icon;

  /// 실외 활동이 불편해 실내 장소를 우선할 상황인지.
  final bool prefersIndoor;
}

class Weather {
  const Weather({required this.condition, required this.temperatureC});

  final WeatherCondition condition;
  final int temperatureC;

  String get summary => '${condition.label} $temperatureC°';
}
