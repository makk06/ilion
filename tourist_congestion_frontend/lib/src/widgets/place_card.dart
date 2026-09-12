import 'package:flutter/material.dart';
import '../models/place.dart';
import 'crowd_badge.dart';
import 'place_image.dart';

class PlaceCard extends StatelessWidget {
  const PlaceCard(
      {super.key,
      required this.place,
      this.showDescription = false,
      this.isSaved = false,
      this.onTap});
  final Place place;
  final bool showDescription, isSaved;
  final VoidCallback? onTap;
  @override
  Widget build(BuildContext context) => Card(
      child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(16),
          child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(children: [
                PlaceImage(url: place.imageUrl, width: 68, height: 74),
                const SizedBox(width: 12),
                Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      Text(place.name,
                          style: const TextStyle(fontWeight: FontWeight.bold)),
                      Text(
                          [place.area, place.distance]
                              .where((e) => e.isNotEmpty)
                              .join(' · '),
                          style: Theme.of(context).textTheme.bodySmall),
                      const SizedBox(height: 6),
                      Wrap(spacing: 8, runSpacing: 4, children: [
                        CrowdBadge(
                            label:
                                '${place.isDemo ? '개발 샘플 · ' : ''}${place.crowdText}${place.isStale ? ' · 오래된 정보' : ''}',
                            color: place.crowdColor),
                        Text(place.category)
                      ]),
                      if (showDescription && place.description.isNotEmpty)
                        Text(place.description,
                            maxLines: 3, overflow: TextOverflow.ellipsis)
                    ])),
                if (isSaved) const Icon(Icons.favorite, color: Colors.red),
                const Icon(Icons.chevron_right)
              ]))));
}
