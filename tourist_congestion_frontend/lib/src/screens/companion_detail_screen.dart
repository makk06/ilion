import '../services/activity_changes.dart';
import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';
import '../theme/app_theme.dart';
import 'auth_screen.dart';

class CompanionDetailScreen extends StatefulWidget {
  const CompanionDetailScreen({super.key, required this.companion});
  final Map<String, dynamic> companion;
  @override
  State<CompanionDetailScreen> createState() => _CompanionDetailScreenState();
}

class _CompanionDetailScreenState extends State<CompanionDetailScreen> {
  late Map<String, dynamic> _item;
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    _item = widget.companion;
  }

  Future<void> _action() async {
    if (_busy) return;
    if (!await ensureSignedIn(context) || !mounted) return;
    setState(() => _busy = true);
    try {
      // Refetch after signing in so membership never depends on an anonymous snapshot.
      final data = activityItems(await ApiClient.instance.get('/companions'));
      final current = data.where((r) => r['id'] == _item['id']).firstOrNull;
      if (current == null) throw const ApiException('이 모집글은 더 이상 존재하지 않아요.');
      if (current['is_mine'] == true) {
        if (mounted) setState(() => _item = current);
        return;
      }
      if (current['is_joined'] == true) {
        await ApiClient.instance.delete('/companions/${_item['id']}/join');
      } else {
        await ApiClient.instance.post('/companions/${_item['id']}/join');
      }
      activityChanged();
      final refreshed =
          activityItems(await ApiClient.instance.get('/companions'))
              .where((r) => r['id'] == _item['id'])
              .firstOrNull;
      if (mounted && refreshed != null) setState(() => _item = refreshed);
    } catch (e) {
      if (mounted) activityError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete() async {
    if (_busy) return;
    if (!await ensureSignedIn(context) || !mounted) return;
    final yes = await showDialog<bool>(
        context: context,
        builder: (c) =>
            AlertDialog(title: const Text('동행 모집을 삭제할까요?'), actions: [
              TextButton(
                  onPressed: () => Navigator.pop(c, false),
                  child: const Text('취소')),
              FilledButton(
                  onPressed: () => Navigator.pop(c, true),
                  child: const Text('삭제'))
            ]));
    if (yes != true || !mounted) return;
    setState(() => _busy = true);
    try {
      await ApiClient.instance.delete('/companions/${_item['id']}');
      activityChanged();
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) activityError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final expired = _item['date'] != null &&
        (_item['date'] as String)
                .compareTo(DateTime.now().toIso8601String().substring(0, 10)) <
            0;
    final full = (_item['member_count'] as int) >= (_item['capacity'] as int);
    final status = expired
        ? '지난 일정'
        : full
            ? '모집 마감'
            : '모집 중';
    final action = _item['is_mine'] == true
        ? OutlinedButton(
            onPressed: _busy ? null : _delete, child: const Text('모집 삭제'))
        : FilledButton(
            onPressed: _busy || expired || (full && _item['is_joined'] != true)
                ? null
                : _action,
            child: Text(_busy
                ? '처리 중…'
                : expired
                    ? '지난 일정'
                    : _item['is_joined'] == true
                        ? '신청 취소'
                        : full
                            ? '모집 마감'
                            : '동행 신청하기'));
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: const GreenAppBar(title: '동행 모집 상세'),
      bottomNavigationBar: ColoredBox(
        color: AppColors.surface,
        child: SafeArea(
            top: false,
            child: Center(
                heightFactor: 1,
                child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 560),
                    child: Padding(
                        padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
                        child: SizedBox(
                            width: double.infinity,
                            height: 48,
                            child: action))))),
      ),
      body: AppContent(
          child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 28),
        children: [
          Row(children: [
            const CircleAvatar(
                radius: 19,
                backgroundColor: AppColors.primarySoft,
                child: Icon(Icons.person_outline_rounded,
                    size: 22, color: AppColors.primary)),
            const SizedBox(width: 12),
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Text(_item['author_nickname'] ?? '',
                      style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: AppColors.text)),
                  const SizedBox(height: 3),
                  const Text('동행 모집자',
                      style:
                          TextStyle(fontSize: 12, color: AppColors.textMuted)),
                ])),
          ]),
          const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Divider(height: 1, color: AppColors.border)),
          Align(
              alignment: Alignment.centerLeft,
              child: SoftTag(status, emphasis: !expired && !full)),
          const SizedBox(height: 12),
          Text(_item['title'] ?? '',
              style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  height: 1.4,
                  letterSpacing: -.4,
                  color: AppColors.text)),
          const SizedBox(height: 24),
          Text(_item['text'] ?? '',
              style: const TextStyle(
                  fontSize: 16, height: 1.8, color: AppColors.text)),
          const Padding(
              padding: EdgeInsets.symmetric(vertical: 28),
              child: Divider(height: 1, color: AppColors.border)),
          const Text('함께할 일정',
              style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: AppColors.text)),
          const SizedBox(height: 20),
          _info(Icons.location_on_outlined, '장소', _item['place_name'] ?? ''),
          const SizedBox(height: 16),
          _info(Icons.calendar_today_outlined, '날짜', _item['date'] ?? '날짜 미정'),
          const SizedBox(height: 14),
          _info(
              Icons.schedule_outlined,
              '시간',
              _item['time'] == null
                  ? '시간 미정'
                  : (_item['time'] as String).substring(0, 5)),
          const SizedBox(height: 16),
          _info(Icons.people_outline_rounded, '참여 인원',
              '${_item['member_count']}/${_item['capacity']}명'),
        ],
      )),
    );
  }

  Widget _info(IconData icon, String label, String value) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: AppColors.primary),
          const SizedBox(width: 12),
          SizedBox(
              width: 72,
              child: Text(label,
                  style: const TextStyle(
                      fontSize: 13, color: AppColors.textMuted))),
          Expanded(
              child: Text(value,
                  style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: AppColors.text))),
        ],
      );
}
