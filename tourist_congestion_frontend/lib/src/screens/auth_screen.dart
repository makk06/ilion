import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/app_session.dart';
import '../services/legal_links.dart';
import '../theme/app_theme.dart';
import '../widgets/app_chrome.dart';
import 'profile_places_screens.dart';

/// Returns to the caller's screen once signed in, so a gated action can resume
/// where it started. [reason] tells the visitor which action needs the account.
Future<bool> ensureSignedIn(BuildContext context, {String? reason}) async {
  if (AppSession.instance.isAuthenticated) return true;
  return await Navigator.of(context).push<bool>(
          MaterialPageRoute(builder: (_) => AuthScreen(reason: reason))) ??
      false;
}

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, this.reason});

  /// Shown above the form, e.g. '후기를 남기려면 로그인이 필요해요.'
  final String? reason;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _nickname = TextEditingController();
  bool _signup = false;
  bool _ageConfirmed = false;
  bool _termsAgreed = false;
  bool _privacyAgreed = false;

  bool get _allAgreed => _ageConfirmed && _termsAgreed && _privacyAgreed;
  bool _busy = false;
  bool _nicknameBusy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _nickname.dispose();
    super.dispose();
  }

  void _toggleMode() {
    // Swapping modes adds or removes a field, so stale validation state would
    // otherwise be reused by the field that takes its place.
    _form.currentState?.reset();
    setState(() {
      _signup = !_signup;
      _error = null;
    });
  }

  Future<void> _suggestNickname() async {
    setState(() => _nicknameBusy = true);
    try {
      final data = Map<String, dynamic>.from(
          await ApiClient.instance.get('/auth/nickname/random') as Map);
      final suggestion = data['nickname'] as String?;
      if (suggestion != null && mounted) {
        _nickname.text = suggestion;
        _form.currentState?.validate();
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('닉네임을 불러오지 못했어요. 직접 입력해 주세요.')));
      }
    } finally {
      if (mounted) setState(() => _nicknameBusy = false);
    }
  }

  Future<void> _forgotPassword() async {
    final goToHelp = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: const Text('비밀번호를 잊으셨나요?'),
              content: const Text('지금은 앱에서 바로 비밀번호를 재설정할 수 없어요.\n'
                  '1:1 문의로 가입한 이메일을 알려주시면 도와드릴게요.'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(c), child: const Text('닫기')),
                FilledButton(
                    onPressed: () => Navigator.pop(c, true),
                    child: const Text('문의하기')),
              ],
            ));
    if (goToHelp != true || !mounted) return;
    await Navigator.push(
        context, MaterialPageRoute<void>(builder: (_) => const HelpScreen()));
  }

  /// 수집 전에 항목·목적·보유기간·거부 권리를 앱 안에서 바로 보여준다.
  /// 서버의 처리방침 페이지가 열리지 않아도 동의 내용은 확인할 수 있어야 한다.
  Future<void> _showPrivacyConsent() async {
    final agreed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
              title: const Text('개인정보 수집·이용 동의'),
              content: const SingleChildScrollView(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                    _ConsentFact(
                        '수집 항목', '이메일, 비밀번호, 닉네임, 만 14세 이상 확인 및 동의 일시'),
                    _ConsentFact(
                        '이용 목적', '회원 식별과 로그인, 후기·동행·저장 등 회원 기능 제공, 문의 응대'),
                    _ConsentFact('보유 기간',
                        '회원 탈퇴 신청 후 7일이 지나면 파기합니다. 재가입 제한을 위해 이메일을 되돌릴 수 없게 변환한 값만 파기 후 30일간 보관합니다.'),
                    _ConsentFact('동의 거부',
                        '동의를 거부할 수 있으며, 거부하면 회원가입을 할 수 없습니다. 회원가입 없이도 장소 검색·혼잡도 확인·추천은 이용할 수 있습니다.'),
                  ])),
              actions: [
                TextButton(
                    onPressed: () => openLegalPage(context, '/privacy'),
                    child: const Text('처리방침 전문')),
                TextButton(
                    onPressed: () => Navigator.of(context).pop(false),
                    child: const Text('닫기')),
                FilledButton(
                    key: const ValueKey('privacy-consent-agree'),
                    onPressed: () => Navigator.of(context).pop(true),
                    child: const Text('동의')),
              ],
            ));
    if (agreed == true && mounted) setState(() => _privacyAgreed = true);
  }

  Future<void> _submit() async {
    if (_busy || !_form.currentState!.validate()) return;
    if (_signup && !_allAgreed) {
      setState(() => _error = '필수 항목에 모두 동의해 주세요.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (_signup) {
        await AppSession.instance.signup(
            _email.text, _password.text, _nickname.text,
            ageOver14: _ageConfirmed,
            agreeTerms: _termsAgreed,
            agreePrivacy: _privacyAgreed);
      } else {
        await AppSession.instance.login(_email.text, _password.text);
      }
      if (!mounted) return;
      final name = (AppSession.instance.profile?['nickname'] as String?) ??
          (_signup ? _nickname.text.trim() : '');
      // The messenger lives above this route, so the confirmation survives the
      // pop back to whichever screen asked for the sign-in.
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(_signup
              ? '${name.isEmpty ? '' : '$name님, '}환영해요! 가입이 완료됐어요.'
              : '${name.isEmpty ? '' : '$name님, '}로그인했어요.')));
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (e.code == 'withdrawal_pending' && mounted && !_signup) {
        await _offerWithdrawalCancellation(e);
      } else if (mounted) {
        setState(() => _error = e.toString());
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _offerWithdrawalCancellation(ApiException error) async {
    final deadline =
        DateTime.tryParse(error.data?['purge_at'] as String? ?? '')?.toLocal();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('탈퇴 예정 계정'),
        content: Text('탈퇴 신청을 취소하고 계정을 복구하시겠어요?'
            '${deadline == null ? '' : '\n삭제 예정: $deadline'}'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('탈퇴 유지')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('탈퇴 취소하고 로그인')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await AppSession.instance.cancelWithdrawal(_email.text, _password.text);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('탈퇴 신청을 취소했어요.')));
      Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  String? _validatePassword(String? value) {
    if (value == null || value.isEmpty) return '비밀번호를 입력해 주세요.';
    if (!_signup) return null;
    if (value.length < 8) return '8자 이상 입력해 주세요.';
    // Mirrors the server's validators so a weak password is caught before the
    // request, instead of coming back as a server error list.
    if (RegExp(r'^\d+$').hasMatch(value)) return '숫자만으로는 사용할 수 없어요.';
    const common = {
      '12345678',
      '123456789',
      '1234567890',
      'password',
      'qwerty123',
      'abc12345',
      '11111111',
      '00000000',
    };
    if (common.contains(value.toLowerCase())) {
      return '너무 흔한 비밀번호예요. 다른 비밀번호를 써주세요.';
    }
    return null;
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: GreenAppBar(title: _signup ? '회원가입' : '로그인'),
        body: AppContent(
            child: AutofillGroup(
                child: Form(
                    key: _form,
                    autovalidateMode: AutovalidateMode.onUserInteraction,
                    child:
                        ListView(padding: const EdgeInsets.all(24), children: [
                      if (widget.reason != null) ...[
                        Container(
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                                color: AppColors.primarySoft,
                                borderRadius: BorderRadius.circular(12)),
                            child: Row(children: [
                              const Icon(Icons.lock_outline_rounded,
                                  size: 18, color: AppColors.primary),
                              const SizedBox(width: 10),
                              Expanded(
                                  child: Text(widget.reason!,
                                      style: const TextStyle(
                                          fontSize: 13,
                                          color: AppColors.primary))),
                            ])),
                        const SizedBox(height: 20),
                      ],
                      const Text('즐겨찾기와 여행 기록을 계정에 저장하세요.'),
                      const SizedBox(height: 24),
                      TextFormField(
                          key: const ValueKey('auth-email'),
                          controller: _email,
                          enabled: !_busy,
                          keyboardType: TextInputType.emailAddress,
                          autofillHints: const [AutofillHints.email],
                          decoration: const InputDecoration(labelText: '이메일'),
                          validator: (v) => v != null &&
                                  RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
                                      .hasMatch(v.trim())
                              ? null
                              : '이메일 주소를 입력해 주세요.'),
                      const SizedBox(height: 16),
                      if (_signup) ...[
                        TextFormField(
                            key: const ValueKey('auth-nickname'),
                            controller: _nickname,
                            enabled: !_busy,
                            maxLength: 30,
                            decoration: InputDecoration(
                                labelText: '닉네임',
                                suffixIcon: IconButton(
                                    tooltip: '랜덤 닉네임 받기',
                                    onPressed: _busy || _nicknameBusy
                                        ? null
                                        : _suggestNickname,
                                    icon: _nicknameBusy
                                        ? const SizedBox(
                                            width: 18,
                                            height: 18,
                                            child: CircularProgressIndicator(
                                                strokeWidth: 2))
                                        : const Icon(Icons.casino_outlined))),
                            validator: (v) => v == null || v.trim().isEmpty
                                ? '닉네임을 입력해 주세요.'
                                : null),
                        const SizedBox(height: 16),
                      ],
                      TextFormField(
                          key: const ValueKey('auth-password'),
                          controller: _password,
                          enabled: !_busy,
                          obscureText: _obscure,
                          autofillHints: [
                            _signup
                                ? AutofillHints.newPassword
                                : AutofillHints.password
                          ],
                          decoration: InputDecoration(
                              labelText: '비밀번호',
                              helperText: _signup
                                  ? '8자 이상, 숫자만 사용하거나 흔한 비밀번호는 피해주세요.'
                                  : null,
                              helperMaxLines: 2,
                              suffixIcon: IconButton(
                                  tooltip: _obscure ? '비밀번호 표시' : '비밀번호 숨기기',
                                  onPressed: () =>
                                      setState(() => _obscure = !_obscure),
                                  icon: Icon(_obscure
                                      ? Icons.visibility
                                      : Icons.visibility_off))),
                          validator: _validatePassword,
                          onFieldSubmitted: (_) => _submit()),
                      if (!_signup)
                        Align(
                            alignment: Alignment.centerRight,
                            child: TextButton(
                                onPressed: _busy ? null : _forgotPassword,
                                child: const Text('비밀번호를 잊으셨나요?',
                                    style: TextStyle(fontSize: 12)))),
                      if (_signup) ...[
                        const SizedBox(height: 12),
                        _ConsentTile(
                            key: const ValueKey('auth-consent-all'),
                            label: '전체 동의',
                            emphasized: true,
                            value: _allAgreed,
                            onChanged: _busy
                                ? null
                                : (value) => setState(() {
                                      _ageConfirmed = value;
                                      _termsAgreed = value;
                                      _privacyAgreed = value;
                                    })),
                        const Divider(height: 8),
                        _ConsentTile(
                            key: const ValueKey('auth-consent-age'),
                            label: '[필수] 만 14세 이상입니다',
                            value: _ageConfirmed,
                            onChanged: _busy
                                ? null
                                : (value) =>
                                    setState(() => _ageConfirmed = value)),
                        _ConsentTile(
                            key: const ValueKey('auth-consent-terms'),
                            label: '[필수] 이용약관에 동의합니다',
                            value: _termsAgreed,
                            onChanged: _busy
                                ? null
                                : (value) =>
                                    setState(() => _termsAgreed = value),
                            onView: () => openLegalPage(context, '/terms')),
                        _ConsentTile(
                            key: const ValueKey('auth-consent-privacy'),
                            label: '[필수] 개인정보 수집·이용에 동의합니다',
                            value: _privacyAgreed,
                            onChanged: _busy
                                ? null
                                : (value) =>
                                    setState(() => _privacyAgreed = value),
                            onView: _showPrivacyConsent),
                      ],
                      if (_error != null)
                        Padding(
                            padding: const EdgeInsets.only(top: 16),
                            child: Text(_error!,
                                style: TextStyle(
                                    color:
                                        Theme.of(context).colorScheme.error))),
                      const SizedBox(height: 24),
                      FilledButton(
                          onPressed: _busy ? null : _submit,
                          child: Text(_busy
                              ? '처리 중…'
                              : _signup
                                  ? '회원가입'
                                  : '로그인')),
                      TextButton(
                          onPressed: _busy ? null : _toggleMode,
                          child: Text(_signup ? '이미 계정이 있어요 · 로그인' : '계정 만들기')),
                    ])))),
      );
}

class _ConsentTile extends StatelessWidget {
  const _ConsentTile(
      {super.key,
      required this.label,
      required this.value,
      required this.onChanged,
      this.onView,
      this.emphasized = false});

  final String label;
  final bool value;
  final ValueChanged<bool>? onChanged;
  final VoidCallback? onView;
  final bool emphasized;

  @override
  Widget build(BuildContext context) => CheckboxListTile(
        value: value,
        onChanged: onChanged == null
            ? null
            : (checked) => onChanged!(checked ?? false),
        controlAffinity: ListTileControlAffinity.leading,
        contentPadding: EdgeInsets.zero,
        dense: true,
        title: Text(label,
            style: TextStyle(
                fontSize: emphasized ? 14 : 13,
                fontWeight: emphasized ? FontWeight.w700 : FontWeight.w400)),
        secondary: onView == null
            ? null
            : TextButton(
                onPressed: onView,
                child: const Text('보기', style: TextStyle(fontSize: 12))),
      );
}

class _ConsentFact extends StatelessWidget {
  const _ConsentFact(this.title, this.body);

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title,
              style:
                  const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(body, style: const TextStyle(fontSize: 13, height: 1.5)),
        ]),
      );
}
