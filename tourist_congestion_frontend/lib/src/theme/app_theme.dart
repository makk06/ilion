import 'package:flutter/material.dart';

abstract final class AppColors {
  static const primary = Color(0xFF4F6EF7);
  static const primarySoft = Color(0xFFE9EDFF);
  static const background = Color(0xFFF7F8FC);
  static const surface = Colors.white;
  static const text = Color(0xFF202432);
  static const textMuted = Color(0xFF7C8293);
  static const low = Color(0xFF35B779);
  static const medium = Color(0xFFFFB347);
  static const high = Color(0xFFF06268);
}

abstract final class AppTheme {
  static ThemeData get light {
    final scheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: Brightness.light,
      surface: AppColors.surface,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.background,
      fontFamilyFallback: const ['Pretendard', 'Noto Sans KR'],
      textTheme: const TextTheme(
        headlineSmall: TextStyle(
          color: AppColors.text,
          fontSize: 24,
          fontWeight: FontWeight.w800,
        ),
        titleMedium: TextStyle(
          color: AppColors.text,
          fontSize: 17,
          fontWeight: FontWeight.w700,
        ),
        bodyMedium: TextStyle(
          color: AppColors.text,
          fontSize: 14,
          height: 1.4,
        ),
      ),
      navigationBarTheme: const NavigationBarThemeData(
        height: 68,
        backgroundColor: AppColors.surface,
        indicatorColor: AppColors.primarySoft,
        labelTextStyle: WidgetStatePropertyAll(
          TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
      ),
      cardTheme: const CardThemeData(
        color: AppColors.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
      ),
    );
  }
}
