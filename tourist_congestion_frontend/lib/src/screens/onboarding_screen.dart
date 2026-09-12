import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../widgets/app_chrome.dart';
import 'auth_screen.dart';

class OnboardingScreen extends StatelessWidget {
  const OnboardingScreen({super.key, required this.onStart});
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: AppColors.p9,
        body: AppContent(
          child: Stack(
            fit: StackFit.expand,
            children: [
              const Positioned.fill(child: _BackgroundGlow()),
              SafeArea(
                bottom: false,
                child: Column(children: [
                  const Spacer(flex: 4),
                  const BrandMark(size: 70),
                  const SizedBox(height: 18),
                  const Text.rich(
                    TextSpan(children: [
                      TextSpan(
                          text: '이리',
                          style: TextStyle(fontWeight: FontWeight.w800)),
                      TextSpan(
                          text: 'ON', style: TextStyle(color: AppColors.p4)),
                    ]),
                    style: TextStyle(
                        color: Colors.white, fontSize: 28, letterSpacing: .5),
                  ),
                  const SizedBox(height: 22),
                  const Text('사람 많은 땐, 이리ON\n가까운 대안을 켜드려요',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          color: AppColors.p3, fontSize: 14, height: 1.65)),
                  const Spacer(flex: 5),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.fromLTRB(24, 30, 24, 34),
                    decoration: const BoxDecoration(
                        color: AppColors.surface,
                        borderRadius:
                            BorderRadius.vertical(top: Radius.circular(32))),
                    child: SafeArea(
                      top: false,
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                        FilledButton(
                            onPressed: onStart, child: const Text('시작하기')),
                        const SizedBox(height: 10),
                        TextButton(
                            onPressed: () async {
                              if (await ensureSignedIn(context) &&
                                  context.mounted) {
                                onStart();
                              }
                            },
                            child: const Text('이미 계정이 있어요',
                                style: TextStyle(color: AppColors.textMuted))),
                      ]),
                    ),
                  ),
                ]),
              ),
            ],
          ),
        ),
      );
}

class _BackgroundGlow extends StatelessWidget {
  const _BackgroundGlow();

  @override
  Widget build(BuildContext context) => DecoratedBox(
        decoration: BoxDecoration(
          gradient: RadialGradient(
              center: const Alignment(.65, -.45),
              radius: 1.1,
              colors: [AppColors.p8.withValues(alpha: .65), AppColors.p9]),
        ),
      );
}
