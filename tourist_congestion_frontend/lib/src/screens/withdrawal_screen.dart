import 'package:flutter/material.dart';

import '../services/app_session.dart';
import '../widgets/app_chrome.dart';

class WithdrawalScreen extends StatefulWidget {
  const WithdrawalScreen({super.key});

  @override
  State<WithdrawalScreen> createState() => _WithdrawalScreenState();
}

class _WithdrawalScreenState extends State<WithdrawalScreen> {
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    if (_password.text.isEmpty) {
      setState(() => _error = '본인 확인을 위해 현재 비밀번호를 입력해 주세요.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await AppSession.instance.withdraw(_password.text);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('탈퇴가 접수됐어요. 7일 이내 로그인 화면에서 취소할 수 있어요.')));
      Navigator.of(context).popUntil((route) => route.isFirst);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final google = AppSession.instance.profile?['provider'] == 'google';
    return PopScope(
      canPop: !_busy,
      child: Scaffold(
        appBar: const GreenAppBar(title: '회원 탈퇴'),
        body: AppContent(
            child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const Text('탈퇴 전 확인해 주세요.',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 20),
            const Text('신청 즉시 로그아웃되며, 7일 후 계정이 삭제됩니다.\n'
                '7일 이내 로그인 화면에서 본인 확인 후 탈퇴를 취소할 수 있습니다.\n\n'
                '후기·사진과 일부 활동 데이터는 계정 연결을 제거한 뒤 보존됩니다. '
                '후기나 사진에 개인정보가 있다면 탈퇴 전에 직접 삭제해 주세요.\n\n'
                '계정 삭제 후에는 같은 이메일로 30일간 재가입할 수 없습니다.'),
            const SizedBox(height: 24),
            if (google)
              const Text('Google 계정은 Google 본인 확인이 필요합니다. '
                  '이 앱의 Google 로그인 화면은 아직 지원되지 않아 여기서 탈퇴할 수 없습니다. '
                  '도움말 및 문의를 이용해 주세요.')
            else ...[
              TextField(
                controller: _password,
                enabled: !_busy,
                obscureText: true,
                autocorrect: false,
                enableSuggestions: false,
                decoration: const InputDecoration(labelText: '현재 비밀번호'),
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 20),
              if (_error != null) ...[
                Text(_error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error)),
                const SizedBox(height: 12),
              ],
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Text(_busy ? '탈퇴 접수 중…' : '본인 확인 후 탈퇴 신청'),
              ),
            ],
            TextButton(
              onPressed: _busy ? null : () => Navigator.of(context).pop(),
              child: const Text('돌아가기'),
            ),
          ],
        )),
      ),
    );
  }
}
