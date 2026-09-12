import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../services/app_session.dart';
import '../theme/app_theme.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';
import '../widgets/profile_recent_places.dart';
import '../widgets/profile_points_card.dart';
import 'auth_screen.dart';
import 'personalized_recommendations_screen.dart';
import 'profile_places_screens.dart';
import 'profile_subscreens.dart';
import 'notifications_screen.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  Future<void> _open(BuildContext context, Widget screen,
      {bool auth = false}) async {
    if (auth && !await ensureSignedIn(context)) return;
    if (!context.mounted) return;
    await Navigator.push(
        context, MaterialPageRoute<void>(builder: (_) => screen));
  }

  Future<void> _nickname(BuildContext context) async {
    final controller = TextEditingController(
        text: AppSession.instance.profile?['nickname'] ?? '');
    final name = await showDialog<String>(
        context: context,
        builder: (c) => AlertDialog(
                title: const Text('닉네임 변경'),
                content: TextField(controller: controller, maxLength: 30),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(c),
                      child: const Text('취소')),
                  FilledButton(
                      onPressed: () => Navigator.pop(c, controller.text.trim()),
                      child: const Text('저장'))
                ]));
    WidgetsBinding.instance.addPostFrameCallback((_) => controller.dispose());
    if (name == null || name.isEmpty || !context.mounted) {
      return;
    }
    try {
      await ApiClient.instance.patch('/me', body: {'nickname': name});
      await AppSession.instance.refreshProfile();
    } catch (e) {
      if (context.mounted) {
        activityError(context, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: AppColors.background,
        body: SafeArea(
            child: AppContent(
                child: ListenableBuilder(
          listenable: AppSession.instance,
          builder: (context, _) {
            final session = AppSession.instance;
            return ListView(children: [
              Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 12, 8),
                  child: Row(children: [
                    const Expanded(
                        child: Text('마이페이지',
                            style: TextStyle(
                                fontSize: 16, fontWeight: FontWeight.w700))),
                    IconButton(
                        tooltip: '알림 설정',
                        onPressed: () => _open(
                            context, const NotificationSettingsScreen(),
                            auth: true),
                        icon: const Icon(Icons.settings_outlined, size: 22)),
                    IconButton(
                        tooltip: '내 활동 알림',
                        onPressed: () => _open(
                            context, const NotificationsScreen(), auth: true),
                        icon: const Icon(Icons.notifications_none_rounded,
                            size: 22)),
                  ])),
              Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: () => session.isAuthenticated
                        ? _nickname(context)
                        : ensureSignedIn(context),
                    child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Row(children: [
                          const CircleAvatar(
                              radius: 24,
                              backgroundColor: Color(0xFFF0F3F0),
                              child: Icon(Icons.person_rounded,
                                  color: Color(0xFF92A495), size: 28)),
                          const SizedBox(width: 12),
                          Expanded(
                              child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                Text(
                                    session.profile?['nickname'] ??
                                        '여행자님, 반가워요',
                                    style: const TextStyle(
                                        fontSize: 17,
                                        fontWeight: FontWeight.w700)),
                                const SizedBox(height: 4),
                                Text(
                                    session.isAuthenticated
                                        ? '닉네임 변경'
                                        : '로그인 / 회원가입',
                                    style: const TextStyle(
                                        fontSize: 12,
                                        color: AppColors.textMuted)),
                              ])),
                          const Icon(Icons.chevron_right_rounded,
                              color: AppColors.textMuted, size: 20),
                        ])),
                  )),
              const ProfilePointsCard(),
              const SizedBox(height: 12),
              Container(
                  margin: const EdgeInsets.symmetric(horizontal: 20),
                  padding:
                      const EdgeInsets.symmetric(vertical: 20, horizontal: 8),
                  decoration: BoxDecoration(
                      color: AppColors.surface,
                      border: Border.all(color: AppColors.border),
                      borderRadius: BorderRadius.circular(16)),
                  child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _shortcut(context, Icons.favorite_rounded, '저장 장소',
                            const Color(0xFFE58C9E), const SavedPlacesScreen()),
                        _shortcut(context, Icons.edit_note_rounded, '내 후기',
                            const Color(0xFF80A4C9), const MyReviewsScreen(),
                            auth: true),
                        _shortcut(
                            context,
                            Icons.people_alt_rounded,
                            '동행 내역',
                            const Color(0xFFA291C9),
                            const CompanionHistoryScreen(),
                            auth: true),
                        _shortcut(context, Icons.event_note_rounded, '여행 일정',
                            const Color(0xFF79A791), const TravelPlansScreen()),
                      ])),
              const SizedBox(height: 24),
              const _SectionBreak(),
              const ProfileRecentPlaces(),
              const _SectionBreak(),
              _heading('나의 여행'),
              _menu(context, Icons.explore_outlined, '맞춤 장소 추천',
                  const PersonalizedRecommendationsScreen()),
              _menu(context, Icons.tune_rounded, '관심 지역 및 여행 취향',
                  const PreferenceSettingsScreen(),
                  auth: true),
              const SizedBox(height: 12),
              const _SectionBreak(),
              _heading('설정 및 도움말'),
              _menu(context, Icons.notifications_none_rounded, '알림 설정',
                  const NotificationSettingsScreen(),
                  auth: true),
              _menu(context, Icons.headset_mic_outlined, '도움말 및 문의',
                  const HelpScreen()),
              if (session.isAuthenticated)
                Padding(
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                    child: Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton(
                            onPressed: () async {
                              try {
                                await session.logout();
                              } catch (e) {
                                if (context.mounted) activityError(context, e);
                              }
                            },
                            child: const Text('로그아웃',
                                style: TextStyle(
                                    fontSize: 12,
                                    color: AppColors.textMuted))))),
              const SizedBox(height: 24),
            ]);
          },
        ))),
      );

  Widget _heading(String title) => Padding(
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 8),
      child: Text(title,
          style: const TextStyle(fontSize: 12, color: AppColors.textMuted)));

  Widget _shortcut(BuildContext context, IconData icon, String title,
          Color color, Widget screen,
          {bool auth = false}) =>
      Expanded(
          child: InkWell(
        onTap: () => _open(context, screen, auth: auth),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Column(children: [
              Icon(icon, color: color, size: 26),
              const SizedBox(height: 10),
              Text(title,
                  textAlign: TextAlign.center,
                  style:
                      const TextStyle(fontSize: 11, color: Color(0xFF566058))),
            ])),
      ));

  Widget _menu(BuildContext context, IconData icon, String title, Widget screen,
          {bool auth = false}) =>
      ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 2),
        leading: Icon(icon, size: 21, color: AppColors.textMuted),
        title: Text(title, style: const TextStyle(fontSize: 14)),
        trailing: const Icon(Icons.chevron_right_rounded,
            size: 19, color: AppColors.textMuted),
        onTap: () => _open(context, screen, auth: auth),
      );
}

class _SectionBreak extends StatelessWidget {
  const _SectionBreak();
  @override
  Widget build(BuildContext context) =>
      const Divider(height: 8, thickness: 8, color: Color(0xFFF4F6F4));
}
