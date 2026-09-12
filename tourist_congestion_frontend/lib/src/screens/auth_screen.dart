import 'package:flutter/material.dart';

import '../services/app_session.dart';
import '../widgets/app_chrome.dart';

Future<bool> ensureSignedIn(BuildContext context) async {
  if (AppSession.instance.isAuthenticated) return true;
  return await Navigator.of(context)
          .push<bool>(MaterialPageRoute(builder: (_) => const AuthScreen())) ??
      false;
}

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});
  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _nickname = TextEditingController();
  bool _signup = false;
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _nickname.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (_signup) {
        await AppSession.instance
            .signup(_email.text, _password.text, _nickname.text);
      } else {
        await AppSession.instance.login(_email.text, _password.text);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: GreenAppBar(title: _signup ? '회원가입' : '로그인'),
        body: AppContent(
            child: AutofillGroup(
                child: Form(
                    key: _form,
                    child:
                        ListView(padding: const EdgeInsets.all(24), children: [
                      const Text('즐겨찾기와 여행 기록을 계정에 저장하세요.'),
                      const SizedBox(height: 24),
                      TextFormField(
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
                            controller: _nickname,
                            enabled: !_busy,
                            maxLength: 30,
                            decoration: const InputDecoration(labelText: '닉네임'),
                            validator: (v) => v == null || v.trim().isEmpty
                                ? '닉네임을 입력해 주세요.'
                                : null),
                        const SizedBox(height: 16),
                      ],
                      TextFormField(
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
                          validator: (v) => v == null || v.isEmpty
                              ? '비밀번호를 입력해 주세요.'
                              : _signup && v.length < 8
                                  ? '8자 이상 입력해 주세요.'
                                  : null,
                          onFieldSubmitted: (_) => _submit()),
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
                          onPressed: _busy
                              ? null
                              : () => setState(() {
                                    _signup = !_signup;
                                    _error = null;
                                  }),
                          child: Text(_signup ? '이미 계정이 있어요 · 로그인' : '계정 만들기')),
                    ])))),
      );
}
