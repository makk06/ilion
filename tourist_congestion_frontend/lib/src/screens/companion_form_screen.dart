import '../services/activity_changes.dart';
import '../widgets/activity_place_picker.dart';
import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';
import 'auth_screen.dart';

class CompanionFormScreen extends StatefulWidget {
  const CompanionFormScreen({super.key});
  @override
  State<CompanionFormScreen> createState() => _CompanionFormScreenState();
}

class _CompanionFormScreenState extends State<CompanionFormScreen> {
  final _title = TextEditingController(), _text = TextEditingController();
  Map<String, dynamic>? _place;
  DateTime? _date;
  int _capacity = 2;
  bool _busy = false;
  @override
  void dispose() {
    _title.dispose();
    _text.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_busy) return;
    if (_place == null ||
        _date == null ||
        _title.text.trim().isEmpty ||
        _text.text.trim().isEmpty) {
      activityError(context, const ApiException('장소, 날짜, 제목과 내용을 모두 입력해 주세요.'));
      return;
    }
    if (!await ensureSignedIn(context) || !mounted) return;
    setState(() => _busy = true);
    try {
      await ApiClient.instance.post('/companions', body: {
        'place_id': _place!['id'],
        'date': _date!.toIso8601String().substring(0, 10),
        'title': _title.text.trim(),
        'text': _text.text.trim(),
        'capacity': _capacity
      });
      activityChanged();
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) activityError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: const GreenAppBar(title: '동행 모집 작성'),
      body: AppContent(
          child: ListView(padding: const EdgeInsets.all(20), children: [
        ListTile(
            title: Text(_place?['name'] ?? '장소 선택'),
            trailing: const Icon(Icons.place),
            onTap: _busy
                ? null
                : () async {
                    final place = await selectActivityPlace(context);
                    if (place != null && mounted) {
                      setState(() => _place = place);
                    }
                  }),
        ListTile(
            title: Text(_date == null
                ? '날짜 선택'
                : _date!.toIso8601String().substring(0, 10)),
            trailing: const Icon(Icons.calendar_month),
            onTap: _busy
                ? null
                : () async {
                    final now = DateTime.now();
                    final date = await showDatePicker(
                        context: context,
                        initialDate: _date ?? now,
                        firstDate: DateTime(now.year, now.month, now.day),
                        lastDate: DateTime(now.year + 3));
                    if (date != null && mounted) setState(() => _date = date);
                  }),
        DropdownButtonFormField<int>(
            initialValue: _capacity,
            decoration: const InputDecoration(labelText: '모집 인원 (작성자 포함)'),
            items: [2, 3, 4, 5, 6]
                .map((n) => DropdownMenuItem(value: n, child: Text('$n명')))
                .toList(),
            onChanged: _busy ? null : (v) => setState(() => _capacity = v!)),
        const SizedBox(height: 16),
        TextField(
            controller: _title,
            maxLength: 100,
            enabled: !_busy,
            decoration: const InputDecoration(labelText: '모집 제목')),
        TextField(
            controller: _text,
            minLines: 5,
            maxLines: 10,
            maxLength: 3000,
            enabled: !_busy,
            decoration: const InputDecoration(labelText: '만날 시간·장소와 여행 내용')),
        FilledButton(
            onPressed: _busy ? null : _save,
            child: Text(_busy ? '등록 중…' : '등록'))
      ])));
}
