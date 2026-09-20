import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../services/app_session.dart';
import '../theme/app_theme.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';
import 'notifications_screen.dart';
import 'withdrawal_screen.dart';
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

/// Push delivery is not wired up yet, so this screen says so instead of
/// offering switches that cannot change what anyone receives.
class NotificationSettingsScreen extends StatelessWidget {
  const NotificationSettingsScreen({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: const GreenAppBar(title: '알림 설정'),
      body: AppContent(
          child: ListView(padding: const EdgeInsets.all(20), children: [
        Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
                color: AppColors.primarySoft,
                borderRadius: BorderRadius.circular(12)),
            child: const Row(children: [
              Icon(Icons.schedule_rounded, size: 18, color: AppColors.primary),
              SizedBox(width: 10),
              Expanded(
                  child: Text('푸시 알림은 준비 중이에요.',
                      style: TextStyle(
                          fontSize: 13,
                          color: AppColors.primary,
                          fontWeight: FontWeight.w600))),
            ])),
        const SizedBox(height: 16),
        const Text(
            '알림을 보낼 수 있게 되면 여기에서 받고 싶은 알림을 고를 수 있어요.\n'
            '그때까지는 내 활동 알림에서 직접 확인해 주세요.',
            style: TextStyle(fontSize: 13, color: AppColors.textMuted)),
        const SizedBox(height: 24),
        OutlinedButton(
            onPressed: () => Navigator.push(
                context,
                MaterialPageRoute<void>(
                    builder: (_) => const NotificationsScreen())),
            child: const Text('내 활동 알림 보기')),
      ])));
}

class AccountSettingsScreen extends StatelessWidget {
  const AccountSettingsScreen({super.key});

  Future<void> _withdraw(BuildContext context) => Navigator.of(context)
      .push(MaterialPageRoute<void>(builder: (_) => const WithdrawalScreen()));

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: const GreenAppBar(title: '계정 설정'),
      body: AppContent(
          child: ListenableBuilder(
              listenable: AppSession.instance,
              builder: (context, _) {
                final email =
                    AppSession.instance.profile?['email'] as String? ?? '';
                return ListView(padding: const EdgeInsets.all(20), children: [
                  const Text('로그인 계정',
                      style:
                          TextStyle(fontSize: 12, color: AppColors.textMuted)),
                  const SizedBox(height: 6),
                  Text(email, style: const TextStyle(fontSize: 15)),
                  const SizedBox(height: 28),
                  OutlinedButton(
                      onPressed: () => Navigator.push(
                          context,
                          MaterialPageRoute<void>(
                              builder: (_) => const PasswordChangeScreen())),
                      child: const Text('비밀번호 변경')),
                  const SizedBox(height: 40),
                  Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton(
                          onPressed: () => _withdraw(context),
                          child: Text('회원 탈퇴',
                              style: TextStyle(
                                  fontSize: 12,
                                  color:
                                      Theme.of(context).colorScheme.error)))),
                ]);
              })));
}

class PasswordChangeScreen extends StatefulWidget {
  const PasswordChangeScreen({super.key});
  @override
  State<PasswordChangeScreen> createState() => _PasswordChangeScreenState();
}

class _PasswordChangeScreenState extends State<PasswordChangeScreen> {
  final _form = GlobalKey<FormState>();
  final _current = TextEditingController();
  final _next = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ApiClient.instance.post('/auth/password', body: {
        'current_password': _current.text,
        'new_password': _next.text,
      });
      // The server revoked every session, so the stored tokens are now stale.
      await AppSession.instance.forgetSession();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('비밀번호를 변경했어요. 다시 로그인해 주세요.')));
      // 계정 설정 is signed-in only, so returning there would leave an empty
      // screen with buttons that no longer work. Go back to the tabs instead.
      Navigator.of(context).popUntil((route) => route.isFirst);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: const GreenAppBar(title: '비밀번호 변경'),
      body: AppContent(
          child: Form(
              key: _form,
              autovalidateMode: AutovalidateMode.onUserInteraction,
              child: ListView(padding: const EdgeInsets.all(20), children: [
                TextFormField(
                    controller: _current,
                    enabled: !_busy,
                    obscureText: true,
                    decoration: const InputDecoration(labelText: '현재 비밀번호'),
                    validator: (v) =>
                        v == null || v.isEmpty ? '현재 비밀번호를 입력해 주세요.' : null),
                const SizedBox(height: 16),
                TextFormField(
                    controller: _next,
                    enabled: !_busy,
                    obscureText: true,
                    decoration: const InputDecoration(
                        labelText: '새 비밀번호',
                        helperText: '8자 이상, 숫자만 사용하거나 흔한 비밀번호는 피해주세요.',
                        helperMaxLines: 2),
                    validator: (v) {
                      if (v == null || v.isEmpty) return '새 비밀번호를 입력해 주세요.';
                      if (v.length < 8) return '8자 이상 입력해 주세요.';
                      if (RegExp(r'^\d+$').hasMatch(v)) {
                        return '숫자만으로는 사용할 수 없어요.';
                      }
                      if (v == _current.text) {
                        return '현재 비밀번호와 다른 비밀번호를 입력해 주세요.';
                      }
                      return null;
                    }),
                if (_error != null)
                  Padding(
                      padding: const EdgeInsets.only(top: 16),
                      child: Text(_error!,
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error))),
                const SizedBox(height: 24),
                FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: Text(_busy ? '변경 중…' : '비밀번호 변경')),
              ]))));
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
