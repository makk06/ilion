import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../services/app_session.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';
import 'saved_screen.dart';
import 'recommend_screen.dart';

class MyReviewsScreen extends StatelessWidget {
  const MyReviewsScreen({super.key});
  @override
  Widget build(BuildContext context) => const SavedScreen(mine: true);
}

class CompanionHistoryScreen extends StatelessWidget {
  const CompanionHistoryScreen({super.key});
  @override
  Widget build(BuildContext context) => const RecommendScreen(mine: true);
}

class NotificationSettingsScreen extends StatelessWidget {
  const NotificationSettingsScreen({super.key});
  @override
  Widget build(BuildContext context) =>
      const AccountPreferences(notifications: true);
}

class AccountPreferences extends StatefulWidget {
  const AccountPreferences({super.key, this.notifications = false});
  final bool notifications;
  @override
  State<AccountPreferences> createState() => _AccountPreferencesState();
}

class _AccountPreferencesState extends State<AccountPreferences> {
  final _dataKey = GlobalKey<ActivityDataState>();
  bool _busy = false;
  Map<String, dynamic> _preferences = {};
  Set<String> _regions = {}, _styles = {};
  Map<String, dynamic> _notifications = {};
  Future<dynamic> _load() async {
    final data = await ApiClient.instance.get('/me');
    _preferences = Map<String, dynamic>.from(data['preferences'] ?? {});
    _regions = Set<String>.from(_preferences['regions'] ?? []);
    _styles = Set<String>.from(data['preferred_categories'] ?? []);
    _notifications =
        Map<String, dynamic>.from(_preferences['notifications'] ?? {});
    return data;
  }

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      await ApiClient.instance.patch('/me', body: {
        'preferred_categories': _styles.toList(),
        'preferences': {
          ..._preferences,
          'regions': _regions.toList(),
          'notifications': _notifications
        }
      });
      await AppSession.instance.refreshProfile();
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('설정을 저장했어요.')));
      }
    } catch (e) {
      if (mounted) activityError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: GreenAppBar(title: widget.notifications ? '알림 설정' : '관심 지역 및 취향'),
      body: AppContent(
          child: ActivityData(
              key: _dataKey,
              authenticated: true,
              load: _load,
              builder: (context, data, refresh) =>
                  ListView(padding: const EdgeInsets.all(20), children: [
                    if (widget.notifications) ...[
                      const Text(
                          '알림 수신 선호도를 계정에 저장합니다. 현재 푸시 알림 발송 기능은 제공되지 않아요.'),
                      for (final item in const [
                        ('crowd', '혼잡도 변화'),
                        ('companion', '동행 활동'),
                        ('review', '후기 반응'),
                        ('marketing', '혜택·이벤트')
                      ])
                        SwitchListTile(
                            title: Text(item.$2),
                            value: _notifications[item.$1] == true,
                            onChanged: _busy
                                ? null
                                : (v) => setState(
                                    () => _notifications[item.$1] = v)),
                    ] else ...[
                      const Text('관심 지역'),
                      Wrap(
                          spacing: 8,
                          children: ['제주 동부', '제주 서부', '제주 시내', '서귀포']
                              .map((s) => FilterChip(
                                  label: Text(s),
                                  selected: _regions.contains(s),
                                  onSelected: _busy
                                      ? null
                                      : (v) => setState(() => v
                                          ? _regions.add(s)
                                          : _regions.remove(s))))
                              .toList()),
                      const SizedBox(height: 20),
                      const Text('여행 취향'),
                      Wrap(
                          spacing: 8,
                          children: ['자연', '산책', '전시', '맛집', '사진', '아이와 함께']
                              .map((s) => FilterChip(
                                  label: Text(s),
                                  selected: _styles.contains(s),
                                  onSelected: _busy
                                      ? null
                                      : (v) => setState(() => v
                                          ? _styles.add(s)
                                          : _styles.remove(s))))
                              .toList())
                    ],
                    const SizedBox(height: 24),
                    FilledButton(
                        onPressed: _busy ? null : _save,
                        child: Text(_busy ? '저장 중…' : '저장하기'))
                  ]))));
}
