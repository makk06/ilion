import 'package:flutter/material.dart';

class PlaceImage extends StatelessWidget {
  const PlaceImage({super.key, this.url, this.width, this.height});
  final String? url;
  final double? width, height;
  @override
  Widget build(BuildContext context) {
    final fallback = ColoredBox(
        color: const Color(0xffedf3f0),
        child: Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.image_not_supported_outlined),
          if ((height ?? 100) > 100) const Text('등록된 사진이 없습니다')
        ])));
    return ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: SizedBox(
            width: width,
            height: height,
            child: url == null
                ? fallback
                : Image.network(url!,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => fallback)));
  }
}
