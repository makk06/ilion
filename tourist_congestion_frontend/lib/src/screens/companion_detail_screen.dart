import '../services/activity_changes.dart';
import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';
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
    final expired = (_item['date'] as String)
            .compareTo(DateTime.now().toIso8601String().substring(0, 10)) <
        0;
    final full = (_item['member_count'] as int) >= (_item['capacity'] as int);
    return Scaffold(
        appBar: const GreenAppBar(title: '동행 모집 상세'),
        body: AppContent(
            child: ListView(padding: const EdgeInsets.all(20), children: [
          Text(_item['title'] ?? '',
              style: Theme.of(context).textTheme.headlineSmall),
          ListTile(
              leading: const Icon(Icons.person_outline),
              title: Text(_item['author_nickname'] ?? '')),
          ListTile(
              leading: const Icon(Icons.place),
              title: Text(_item['place_name'] ?? '')),
          ListTile(
              leading: const Icon(Icons.calendar_month),
              title: Text(_item['date'] ?? '')),
          Text('${_item['member_count']}/${_item['capacity']}명'),
          const SizedBox(height: 20),
          Text(_item['text'] ?? ''),
          const SizedBox(height: 24),
          if (_item['is_mine'] == true)
            OutlinedButton(
                onPressed: _busy ? null : _delete, child: const Text('모집 삭제'))
          else
            FilledButton(
                onPressed:
                    _busy || expired || (full && _item['is_joined'] != true)
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
                                : '동행 신청하기'))
        ])));
  }
}
