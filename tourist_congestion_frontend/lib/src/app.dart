import 'package:flutter/material.dart';

import 'screens/main_shell.dart';
import 'theme/app_theme.dart';

class CrowdTripApp extends StatelessWidget {
  const CrowdTripApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: '이리온',
      theme: AppTheme.light,
      home: const MainShell(),
    );
  }
}
