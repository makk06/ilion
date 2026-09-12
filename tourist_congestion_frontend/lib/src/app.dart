import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/main_shell.dart';
import 'screens/onboarding_screen.dart';
import 'theme/app_theme.dart';
import 'services/app_session.dart';

class CrowdTripApp extends StatelessWidget {
  const CrowdTripApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        title: '이리ON',
        theme: AppTheme.light,
        locale: const Locale('ko'),
        supportedLocales: const [Locale('ko'), Locale('en')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: const _EntryFlow(),
      );
}

class _EntryFlow extends StatefulWidget {
  const _EntryFlow();

  @override
  State<_EntryFlow> createState() => _EntryFlowState();
}

class _EntryFlowState extends State<_EntryFlow> {
  var _started = false;
  var _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    try {
      final preferences = await SharedPreferences.getInstance();
      await AppSession.instance.restore();
      if (mounted) {
        setState(() {
          _started = preferences.getBool('onboarding_complete') ?? false;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = '저장된 설정을 불러오지 못했어요. 다시 시도해 주세요.';
        });
      }
    }
  }

  Future<void> _start() async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setBool('onboarding_complete', true);
    if (mounted) setState(() => _started = true);
  }

  @override
  Widget build(BuildContext context) => AnimatedSwitcher(
        duration: const Duration(milliseconds: 350),
        child: _loading
            ? const Scaffold(body: Center(child: CircularProgressIndicator()))
            : _error != null
                ? Scaffold(
                    body: Center(
                        child:
                            Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(_error!),
                    TextButton(
                        onPressed: () {
                          setState(() {
                            _error = null;
                            _loading = true;
                          });
                          _restore();
                        },
                        child: const Text('다시 시도')),
                  ])))
                : _started
                    ? const MainShell(key: ValueKey('main'))
                    : OnboardingScreen(
                        key: const ValueKey('onboarding'), onStart: _start),
      );
}
