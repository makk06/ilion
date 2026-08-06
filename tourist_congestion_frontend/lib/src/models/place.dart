import 'package:flutter/material.dart';

enum CrowdLevel { low, medium, high }

class Place {
  const Place({
    required this.name,
    required this.area,
    required this.category,
    required this.crowdLevel,
    required this.crowdText,
    required this.distance,
    required this.icon,
    required this.description,
  });

  final String name;
  final String area;
  final String category;
  final CrowdLevel crowdLevel;
  final String crowdText;
  final String distance;
  final IconData icon;
  final String description;
}
