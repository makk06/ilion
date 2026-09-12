import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

class AppContent extends StatelessWidget {
  const AppContent({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Center(
        child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560), child: child),
      );
}

class BrandMark extends StatelessWidget {
  const BrandMark(
      {super.key, this.size = 48, this.backgroundColor = AppColors.p6});
  final double size;
  final Color backgroundColor;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
            color: backgroundColor,
            borderRadius: BorderRadius.circular(size * .25)),
        child: Icon(Icons.location_on_rounded,
            color: Colors.white, size: size * .62),
      );
}

class GreenAppBar extends StatelessWidget implements PreferredSizeWidget {
  const GreenAppBar(
      {super.key, required this.title, this.leading, this.actions = const []});
  final String title;
  final Widget? leading;
  final List<Widget> actions;

  @override
  Size get preferredSize => const Size.fromHeight(64);

  @override
  Widget build(BuildContext context) => AppBar(
        toolbarHeight: 64,
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        scrolledUnderElevation: 0,
        foregroundColor: AppColors.text,
        elevation: 0,
        automaticallyImplyLeading: leading == null,
        leading: leading,
        titleSpacing: leading == null ? 20 : 0,
        title: Text(title,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        actions: actions,
      );
}

class SoftTag extends StatelessWidget {
  const SoftTag(this.label, {super.key, this.emphasis = false, this.color});
  final String label;
  final bool emphasis;
  final Color? color;

  @override
  Widget build(BuildContext context) => DecoratedBox(
        decoration: BoxDecoration(
            color: color?.withValues(alpha: .14) ??
                (emphasis ? AppColors.p3 : AppColors.p1),
            borderRadius: BorderRadius.circular(999)),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          child: Text(label,
              style: TextStyle(
                  color: color ?? (emphasis ? AppColors.p8 : AppColors.p7),
                  fontSize: 12,
                  fontWeight: FontWeight.w600)),
        ),
      );
}

class ThumbnailBlock extends StatelessWidget {
  const ThumbnailBlock(
      {super.key, this.width = 64, this.height = 64, this.dark = false});
  final double width;
  final double height;
  final bool dark;

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: SizedBox(
            width: width,
            height: height,
            child: CustomPaint(painter: _ThumbnailPainter(dark: dark))),
      );
}

class _ThumbnailPainter extends CustomPainter {
  const _ThumbnailPainter({required this.dark});
  final bool dark;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawColor(AppColors.p3, BlendMode.src);
    final path = Path()
      ..moveTo(0, 0)
      ..lineTo(size.width, 0)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(path, Paint()..color = dark ? AppColors.p8 : AppColors.p6);
  }

  @override
  bool shouldRepaint(covariant _ThumbnailPainter oldDelegate) =>
      oldDelegate.dark != dark;
}
