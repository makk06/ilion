import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../services/api_client.dart';
import '../services/app_session.dart';
import '../services/activity_changes.dart';
import '../screens/auth_screen.dart';
import '../screens/points_screen.dart';

class ProfilePointsCard extends StatefulWidget {
  const ProfilePointsCard({super.key});
  @override
  State<ProfilePointsCard> createState() => _ProfilePointsCardState();
}

class _ProfilePointsCardState extends State<ProfilePointsCard> {
  num? _balance;
  bool _failed = false;
  int _generation = 0;
  @override
  void initState() {
    super.initState();
    AppSession.instance.addListener(_load);
    activityChanges.addListener(_load);
    _load();
  }

  @override
  void dispose() {
    AppSession.instance.removeListener(_load);
    activityChanges.removeListener(_load);
    super.dispose();
  }

  Future<void> _load() async {
    final generation = ++_generation;
    setState(() {
      _balance = null;
      _failed = false;
    });
    if (!AppSession.instance.isAuthenticated) return;
    try {
      final data = await ApiClient.instance.get('/points');
      if (mounted && generation == _generation) {
        setState(() {
          _balance = data['balance'] as num;
        });
      }
    } catch (_) {
      if (mounted && generation == _generation)
        setState(() {
          _failed = true;
        });
    }
  }

  Future<void> _open(Widget screen) async {
    if (!await ensureSignedIn(context) || !mounted) return;
    await Navigator.push(
        context, MaterialPageRoute<void>(builder: (_) => screen));
    if (mounted) _load();
  }

  @override
  Widget build(BuildContext context) {
    final signedIn = AppSession.instance.isAuthenticated;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 20),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF2E4636),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(
              child: Text('나의 포인트 · 리워드',
                  style: TextStyle(
                      color: Color(0xFFDDE8DF),
                      fontSize: 13,
                      fontWeight: FontWeight.w600))),
          Container(
              padding: const EdgeInsets.all(8),
              decoration: const BoxDecoration(
                  color: Color(0xFF435B48), shape: BoxShape.circle),
              child: const Icon(Icons.toll_rounded,
                  color: Color(0xFFF1D985), size: 24)),
        ]),
        const SizedBox(height: 8),
        if (signedIn && _failed)
          TextButton(
              onPressed: _load,
              child: const Text('포인트 다시 불러오기',
                  style: TextStyle(color: Colors.white)))
        else
          Text(
              signedIn
                  ? (_balance == null
                      ? '불러오는 중'
                      : '${NumberFormat('#,###').format(_balance)} P')
                  : '여행의 즐거움에\n혜택을 더해요',
              style: TextStyle(
                  color: Colors.white,
                  fontSize: signedIn && _balance != null ? 32 : 24,
                  height: 1.3,
                  fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Text(
            signedIn
                ? '내 포인트와 사용 가능한 리워드를 확인해 보세요.'
                : '로그인하고 나의 포인트와 리워드를 확인하세요.',
            style: const TextStyle(
                color: Color(0xFFC6D5C9), fontSize: 12, height: 1.5)),
        const SizedBox(height: 20),
        Row(children: [
          Expanded(
              child: OutlinedButton(
                  style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white,
                      side: const BorderSide(color: Color(0xFF718875)),
                      minimumSize: const Size(0, 44)),
                  onPressed: () => _open(const PointsScreen()),
                  child: const Text('포인트 내역'))),
          const SizedBox(width: 10),
          Expanded(
              child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFFE8F0D9),
                      foregroundColor: const Color(0xFF2E4636),
                      minimumSize: const Size(0, 44)),
                  onPressed: () => _open(const RewardsScreen()),
                  child: const Text('리워드 보기'))),
        ]),
      ]),
    );
  }
}
