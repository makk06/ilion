import '../services/activity_changes.dart';
import '../widgets/activity_place_picker.dart';
import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';
import 'auth_screen.dart';
import '../theme/app_theme.dart';

class CompanionFormScreen extends StatefulWidget {
  const CompanionFormScreen({super.key});
  @override
  State<CompanionFormScreen> createState() => _CompanionFormScreenState();
}

class _CompanionFormScreenState extends State<CompanionFormScreen> {
  final _title = TextEditingController(), _text = TextEditingController();
  Map<String, dynamic>? _place;
  DateTime? _date;
  TimeOfDay? _time;
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
        _title.text.trim().isEmpty ||
        _text.text.trim().isEmpty) {
      activityError(context, const ApiException('장소, 제목과 내용을 모두 입력해 주세요.'));
      return;
    }
    if (!await ensureSignedIn(context) || !mounted) return;
    setState(() => _busy = true);
    try {
      await ApiClient.instance.post('/companions', body: {
        'place_id': _place!['id'],
        'date': _date?.toIso8601String().substring(0, 10),
        'time': _time == null
            ? null
            : '${_time!.hour.toString().padLeft(2, '0')}:${_time!.minute.toString().padLeft(2, '0')}',
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

  Future<void> _selectPlace() async {
    final place = await selectActivityPlace(context);
    if (place != null && mounted) setState(() => _place = place);
  }

  Future<void> _selectDate() async {
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      initialDate: _date ?? now,
      firstDate: DateTime(now.year, now.month, now.day),
      lastDate: DateTime(now.year + 3),
    );
    if (date != null && mounted) setState(() => _date = date);
  }

  Future<void> _selectTime() async {
    final time = await showTimePicker(
        context: context,
        initialTime: _time ?? const TimeOfDay(hour: 12, minute: 0));
    if (time != null && mounted) setState(() => _time = time);
  }

  Widget _scheduleChoice(IconData icon, String label, String value,
          bool undecided, VoidCallback select, VoidCallback clear) =>
      Row(
        children: [
          Expanded(child: _choice(icon, label, value, select)),
          const SizedBox(width: 8),
          ChoiceChip(
              label: const Text('미정'),
              selected: undecided,
              tooltip: '$label 미정',
              onSelected: _busy
                  ? null
                  : (selected) {
                      if (selected) {
                        clear();
                      } else {
                        select();
                      }
                    }),
        ],
      );

  Widget _label(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Text(text,
            style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: AppColors.text)),
      );

  Widget _choice(
          IconData icon, String label, String value, VoidCallback onTap) =>
      ListTile(
        contentPadding: EdgeInsets.zero,
        minVerticalPadding: 14,
        leading: Icon(icon, size: 22, color: AppColors.textMuted),
        title: Text(label,
            style: const TextStyle(fontSize: 13, color: AppColors.textMuted)),
        subtitle: Padding(
            padding: const EdgeInsets.only(top: 5),
            child: Text(value,
                style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: AppColors.text))),
        trailing: const Icon(Icons.chevron_right, size: 20),
        onTap: _busy ? null : onTap,
      );

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: AppColors.surface,
        appBar: const GreenAppBar(title: '동행 모집 작성'),
        bottomNavigationBar: ColoredBox(
          color: AppColors.surface,
          child: SafeArea(
              top: false,
              child: Padding(
                padding: EdgeInsets.only(
                    bottom: MediaQuery.viewInsetsOf(context).bottom),
                child: Center(
                    heightFactor: 1,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 560),
                      child: Padding(
                          padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
                          child: SizedBox(
                              width: double.infinity,
                              height: 48,
                              child: FilledButton(
                                  onPressed: _busy ? null : _save,
                                  child: Text(_busy ? '등록 중…' : '동행 모집 등록')))),
                    )),
              )),
        ),
        body: AppContent(
            child: ListView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 28),
          children: [
            _label('제목'),
            TextField(
                controller: _title,
                maxLength: 100,
                enabled: !_busy,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                    hintText: '예: 토요일에 경복궁 함께 걸어요',
                    semanticCounterText: '제목 최대 100자')),
            const SizedBox(height: 16),
            _label('자세한 내용'),
            TextField(
                controller: _text,
                minLines: 7,
                maxLines: 14,
                maxLength: 3000,
                enabled: !_busy,
                style: const TextStyle(fontSize: 15, height: 1.65),
                decoration: const InputDecoration(
                    hintText:
                        '어떤 여행을 함께하고 싶나요?\n\n만날 시간과 구체적인 장소, 여행 코스 등을 알려주세요.',
                    semanticCounterText: '내용 최대 3000자')),
            const SizedBox(height: 12),
            const Divider(height: 1, color: AppColors.border),
            const SizedBox(height: 24),
            _label('함께할 일정'),
            _choice(Icons.place_outlined, '만날 장소', _place?['name'] ?? '장소 선택',
                _selectPlace),
            const Divider(height: 1, color: AppColors.border),
            _scheduleChoice(
                Icons.calendar_today_outlined,
                '날짜',
                _date == null
                    ? '날짜 미정'
                    : _date!.toIso8601String().substring(0, 10),
                _date == null,
                _selectDate,
                () => setState(() => _date = null)),
            const Divider(height: 1, color: AppColors.border),
            _scheduleChoice(
                Icons.schedule_outlined,
                '시간',
                _time == null ? '시간 미정' : _time!.format(context),
                _time == null,
                _selectTime,
                () => setState(() => _time = null)),
            const SizedBox(height: 8),
            const Text('날짜와 시간은 각각 미정으로 남겨둘 수 있어요.',
                style: TextStyle(fontSize: 12, color: AppColors.textMuted)),
            const SizedBox(height: 24),
            _label('모집 인원'),
            DropdownButtonFormField<int>(
              initialValue: _capacity,
              isExpanded: true,
              decoration: const InputDecoration(
                  helperText: '나를 포함한 전체 인원이에요.',
                  prefixIcon: Icon(Icons.people_outline)),
              items: [2, 3, 4, 5, 6]
                  .map((n) => DropdownMenuItem(value: n, child: Text('$n명')))
                  .toList(),
              onChanged: _busy ? null : (v) => setState(() => _capacity = v!),
            ),
          ],
        )),
      );
}
