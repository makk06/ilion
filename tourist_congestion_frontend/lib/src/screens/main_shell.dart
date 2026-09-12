import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'home_screen.dart';
import 'profile_screen.dart';
import 'recommend_screen.dart';
import 'saved_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _selectedIndex = 0;
  static const _screens = <Widget>[
    HomeScreen(),
    RecommendScreen(),
    SavedScreen(),
    ProfileScreen()
  ];

  @override
  Widget build(BuildContext context) => Scaffold(
        body: IndexedStack(index: _selectedIndex, children: _screens),
        bottomNavigationBar: DecoratedBox(
          decoration: const BoxDecoration(
              color: AppColors.surface,
              border: Border(top: BorderSide(color: AppColors.border))),
          child: SafeArea(
            top: false,
            child: SizedBox(
              height: 64,
              child: Row(children: [
                _NavItem(
                    icon: Icons.home_rounded,
                    label: '홈',
                    index: 0,
                    selectedIndex: _selectedIndex,
                    onTap: _select),
                _NavItem(
                    icon: Icons.people_alt_rounded,
                    label: '동행',
                    index: 1,
                    selectedIndex: _selectedIndex,
                    onTap: _select),
                _NavItem(
                    icon: Icons.star_rounded,
                    label: '후기',
                    index: 2,
                    selectedIndex: _selectedIndex,
                    onTap: _select),
                _NavItem(
                    icon: Icons.person_rounded,
                    label: '마이',
                    index: 3,
                    selectedIndex: _selectedIndex,
                    onTap: _select),
              ]),
            ),
          ),
        ),
      );

  void _select(int index) => setState(() => _selectedIndex = index);
}

class _NavItem extends StatelessWidget {
  const _NavItem(
      {required this.icon,
      required this.label,
      required this.index,
      required this.selectedIndex,
      required this.onTap});
  final IconData icon;
  final String label;
  final int index;
  final int selectedIndex;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final selected = index == selectedIndex;
    return Expanded(
      child: Semantics(
        button: true,
        selected: selected,
        label: label,
        child: InkWell(
          onTap: () => onTap(index),
          child: Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon,
                color: selected ? AppColors.primary : AppColors.textMuted,
                size: 25),
            const SizedBox(height: 3),
            ExcludeSemantics(
                child: Text(label,
                    style: TextStyle(
                        fontSize: 11,
                        color: selected ? AppColors.p7 : AppColors.textMuted)))
          ])),
        ),
      ),
    );
  }
}
