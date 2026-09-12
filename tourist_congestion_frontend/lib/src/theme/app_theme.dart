import 'package:flutter/material.dart';

abstract final class AppColors {
  static const p1 = Color(0xFFEFF8F1);
  static const p2 = Color(0xFFDCEEDF);
  static const p3 = Color(0xFFC2E1C9);
  static const p4 = Color(0xFFA1CFAC);
  static const p5 = Color(0xFF7FBB8F);
  static const p6 = Color(0xFF59AB6A);
  static const p7 = Color(0xFF3D8752);
  static const p8 = Color(0xFF285F39);
  static const p9 = Color(0xFF16391F);
  static const p10 = Color(0xFF0A1C0F);

  static const primary = Color(0xFF2E4636);
  static const primarySoft = p2;
  static const background = Color(0xFFFFFFFF);
  static const surface = Colors.white;
  static const text = p10;
  static const textMuted = Color(0xFF788179);
  static const border = Color(0xFFE3E8E4);
  static const low = Color(0xFF2F80ED);
  static const medium = Color(0xFFF2994A);
  static const high = Color(0xFFEB5757);
}

abstract final class AppTheme {
  static ThemeData get light {
    final scheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: Brightness.light,
      primary: AppColors.primary,
      surface: AppColors.surface,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.background,
      fontFamilyFallback: const ['Pretendard', 'Noto Sans KR'],
      dividerColor: AppColors.border,
      textTheme: const TextTheme(
        headlineSmall: TextStyle(
            color: AppColors.text, fontSize: 22, fontWeight: FontWeight.w800),
        titleLarge: TextStyle(
            color: AppColors.text, fontSize: 18, fontWeight: FontWeight.w700),
        titleMedium: TextStyle(
            color: AppColors.text, fontSize: 16, fontWeight: FontWeight.w700),
        bodyMedium:
            TextStyle(color: AppColors.text, fontSize: 14, height: 1.45),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(48),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.p7,
          side: const BorderSide(color: AppColors.p6),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFFF3F5F3),
        isDense: true,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
        hintStyle: const TextStyle(color: AppColors.textMuted),
        border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: AppColors.border)),
        enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: AppColors.border)),
        focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: AppColors.primary, width: 1.5)),
      ),
      cardTheme: CardThemeData(
        color: AppColors.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: AppColors.border)),
      ),
    );
  }
}
