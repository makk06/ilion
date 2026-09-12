import 'package:flutter/material.dart';

abstract final class AppColors {
  static const estimateVeryLow = Color(0xFF17624B);
  static const estimateLow = Color(0xFF26727A);
  static const estimateNormal = Color(0xFF356798);
  static const estimateHigh = Color(0xFF9A5700);
  static const estimateVeryHigh = Color(0xFFAF3038);
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
  static const primarySoft = Color(0xFFE6EEE2);
  static const background = Color(0xFFF5F7F4);
  static const surface = Colors.white;
  static const text = Color(0xFF17291F);
  static const textMuted = Color(0xFF65736A);
  static const border = Color(0xFFDEE5DE);
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
      focusColor: AppColors.primarySoft,
      hoverColor: AppColors.primarySoft.withValues(alpha: .5),
      scrollbarTheme: ScrollbarThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) =>
            states.contains(WidgetState.hovered)
                ? AppColors.primary
                : AppColors.textMuted),
        thickness: const WidgetStatePropertyAll(6),
        radius: const Radius.circular(8),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: AppColors.surface,
        selectedColor: AppColors.primarySoft,
        side: const BorderSide(color: AppColors.border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        labelStyle: const TextStyle(
            fontSize: 13, color: AppColors.text, fontWeight: FontWeight.w500),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      ),
      dividerTheme:
          const DividerThemeData(color: AppColors.border, thickness: 1),
      listTileTheme: const ListTileThemeData(
          iconColor: AppColors.textMuted,
          contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 4)),
      popupMenuTheme: PopupMenuThemeData(
          color: AppColors.surface,
          surfaceTintColor: Colors.transparent,
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
      textTheme: const TextTheme(
        headlineSmall: TextStyle(
            color: AppColors.text, fontSize: 24, fontWeight: FontWeight.w700),
        titleLarge: TextStyle(
            color: AppColors.text, fontSize: 18, fontWeight: FontWeight.w700),
        titleMedium: TextStyle(
            color: AppColors.text, fontSize: 16, fontWeight: FontWeight.w700),
        bodySmall:
            TextStyle(color: AppColors.textMuted, fontSize: 12, height: 1.5),
        bodyLarge: TextStyle(color: AppColors.text, fontSize: 16, height: 1.5),
        labelLarge: TextStyle(
            color: AppColors.text, fontSize: 14, fontWeight: FontWeight.w600),
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
          foregroundColor: AppColors.primary,
          minimumSize: const Size(0, 44),
          side: const BorderSide(color: AppColors.border),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.surface,
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
