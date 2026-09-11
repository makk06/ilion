import 'package:flutter/material.dart';

import 'screens/main_shell.dart';
import 'state/app_scope.dart';
import 'theme/app_theme.dart';

class CrowdTripApp extends StatelessWidget {
  const CrowdTripApp({super.key});

  @override
  Widget build(BuildContext context) {
    // AppScope 는 MaterialApp 바깥에 둔다.
    // 그래야 바텀시트·다이얼로그처럼 별도 라우트에서도 전역 상태를 읽을 수 있다.
    return AppScope(
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        title: '여유로',
        theme: AppTheme.light,
        home: const MainShell(),
      ),
    );
  }
}
