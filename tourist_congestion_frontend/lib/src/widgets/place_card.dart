import 'package:flutter/material.dart';

import '../models/place.dart';
import '../theme/app_theme.dart';
import 'crowd_badge.dart';

class PlaceCard extends StatelessWidget {
  const PlaceCard({
    super.key,
    required this.place,
    this.showDescription = false,
    this.isSaved = false,
  });

  final Place place;
  final bool showDescription;
  final bool isSaved;

  Color get crowdColor => switch (place.crowdLevel) {
        CrowdLevel.low => AppColors.low,
        CrowdLevel.medium => AppColors.medium,
        CrowdLevel.high => AppColors.high,
      };

  @override
  Widget build(BuildContext context) {
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () {},
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 74,
                height: 74,
                decoration: BoxDecoration(
                  color: AppColors.primarySoft,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Icon(place.icon, size: 34, color: AppColors.primary),
              ),
              const SizedBox(width: 13),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            place.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                          ),
                        ),
                        Icon(
                          isSaved ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                          size: 20,
                          color: isSaved ? AppColors.high : AppColors.textMuted,
                        ),
                      ],
                    ),
                    const SizedBox(height: 5),
                    Text(
                      '${place.area} · ${place.distance}',
                      style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 7,
                      runSpacing: 6,
                      children: [
                        CrowdBadge(label: place.crowdText, color: crowdColor),
                        Text(place.category, style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                      ],
                    ),
                    if (showDescription) ...[
                      const SizedBox(height: 10),
                      Text(
                        place.description,
                        style: const TextStyle(fontSize: 12, color: AppColors.textMuted, height: 1.45),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
