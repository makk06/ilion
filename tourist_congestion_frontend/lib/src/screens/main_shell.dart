import 'package:flutter/material.dart';

import '../state/app_scope.dart';
import '../state/recommendation_request.dart';
import 'home_screen.dart';
import 'profile_screen.dart';
import 'recommend_screen.dart';
import 'saved_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  /// 추천 탭 인덱스. 지도/홈에서 탭을 옮길 때 참조한다.
  static const recommendTabIndex = 1;

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _selectedIndex = 0;
  RecommendationRequest? _request;

  static const _screens = <Widget>[
    HomeScreen(),
    RecommendScreen(),
    SavedScreen(),
    ProfileScreen(),
  ];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final request = AppScope.read(context).recommendationRequest;
    if (identical(request, _request)) return;
    _request?.removeListener(_onRecommendationRequested);
    _request = request..addListener(_onRecommendationRequested);
  }

  @override
  void dispose() {
    _request?.removeListener(_onRecommendationRequested);
    super.dispose();
  }

  /// 지도 탭에서 "근처 대안 추천"을 요청하면 추천 탭으로 이동한다.
  void _onRecommendationRequested() {
    if (!mounted) return;
    if (_request?.hasAnchor ?? false) {
      setState(() => _selectedIndex = MainShell.recommendTabIndex);
    }
  }

  @override
  Widget build(BuildContext context) {
    final savedCount = AppScope.watch(context).savedStore.count;

    return Scaffold(
      body: IndexedStack(index: _selectedIndex, children: _screens),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (index) {
          setState(() => _selectedIndex = index);
        },
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home_rounded),
            label: '홈',
          ),
          const NavigationDestination(
            icon: Icon(Icons.explore_outlined),
            selectedIcon: Icon(Icons.explore_rounded),
            label: '추천',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: savedCount > 0,
              label: Text('$savedCount'),
              child: const Icon(Icons.favorite_border_rounded),
            ),
            selectedIcon: Badge(
              isLabelVisible: savedCount > 0,
              label: Text('$savedCount'),
              child: const Icon(Icons.favorite_rounded),
            ),
            label: '저장',
          ),
          const NavigationDestination(
            icon: Icon(Icons.person_outline_rounded),
            selectedIcon: Icon(Icons.person_rounded),
            label: '마이',
          ),
        ],
      ),
    );
  }
}
