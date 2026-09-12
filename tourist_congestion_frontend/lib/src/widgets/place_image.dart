import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class PlaceImage extends StatelessWidget {
  const PlaceImage({super.key, this.url, this.width, this.height});
  final String? url;
  final double? width, height;
  @override
  Widget build(BuildContext context) {
    final fallback = Semantics(
        label: '등록된 사진 없음',
        child: ColoredBox(
            color: AppColors.primarySoft,
            child: Center(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.landscape_outlined,
                  color: AppColors.textMuted, size: 28),
              if ((height ?? 100) > 100) const Text('등록된 사진이 없습니다')
            ]))));
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
