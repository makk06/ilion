import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../services/app_session.dart';
import '../services/place_service.dart';
import '../models/place.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';
import 'place_detail_screen.dart';
import 'profile_subscreens.dart';
import 'auth_screen.dart';

class RecentPlacesScreen extends StatelessWidget {
  const RecentPlacesScreen({super.key});
  @override
  Widget build(BuildContext context) => const _AccountPlaces(recent: true);
}

class SavedPlacesScreen extends StatelessWidget {
  const SavedPlacesScreen({super.key});
  @override
  Widget build(BuildContext context) => const _AccountPlaces();
}

class _AccountPlaces extends StatelessWidget {
  const _AccountPlaces({this.recent = false});
  final bool recent;
  Future<List<Place>> _load() async {
    final session = AppSession.instance;
    final List<int> ids;
    if (recent) {
      ids = await session.loadRecentPlaces();
    } else if (session.isAuthenticated) {
      final data = await ApiClient.instance.get('/favorites');
      ids = List<int>.from(data['place_ids'] ?? []);
    } else {
      ids = session.favoriteIds.toList();
    }
    final places = await Future.wait(ids.map((id) async {
      try {
        return await PlaceService.instance.detail(id);
      } on ApiException catch (e) {
        if (e.statusCode == 404) return null;
        rethrow;
      }
    }));
    return places.whereType<Place>().toList();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: GreenAppBar(title: recent ? '최근 본 장소' : '저장한 장소'),
      body: AppContent(
          child: ActivityData(
              load: _load,
              builder: (context, data, refresh) {
                final places = data as List<Place>;
                return ListView(
                    padding: const EdgeInsets.all(20),
                    physics: const AlwaysScrollableScrollPhysics(),
                    children: [
                      if (recent && places.isNotEmpty)
                        TextButton(
                            onPressed: () async {
                              try {
                                await AppSession.instance.clearRecent();
                                await refresh();
                              } catch (e) {
                                if (context.mounted) activityError(context, e);
                              }
                            },
                            child: const Text('최근 본 기록 지우기')),
                      if (!AppSession.instance.isAuthenticated)
                        const Padding(
                            padding: EdgeInsets.only(bottom: 16),
                            child: Text('이 기기에 저장한 장소입니다.',
                                style: TextStyle(
                                    fontSize: 12, color: Colors.grey))),
                      if (places.isEmpty)
                        Text(recent ? '최근 본 장소가 없어요.' : '저장한 장소가 없어요.'),
                      ...places.map((p) => Card(
                          child: ListTile(
                              title: Text(p.name),
                              subtitle: Text(p.description),
                              trailing: recent
                                  ? const Icon(Icons.chevron_right)
                                  : IconButton(
                                      tooltip: '저장 취소',
                                      icon: const Icon(Icons.favorite),
                                      onPressed: () async {
                                        try {
                                          await AppSession.instance
                                              .toggleFavorite(p.id);
                                          await refresh();
                                        } catch (e) {
                                          if (context.mounted) {
                                            activityError(context, e);
                                          }
                                        }
                                      }),
                              onTap: () async {
                                await Navigator.push(
                                    context,
                                    MaterialPageRoute<void>(
                                        builder: (_) =>
                                            PlaceDetailScreen(place: p)));
                                await refresh();
                              })))
                    ]);
              })));
}

class PreferenceSettingsScreen extends StatelessWidget {
  const PreferenceSettingsScreen({super.key});
  @override
  Widget build(BuildContext context) => const AccountPreferences();
}

class TravelPlansScreen extends StatefulWidget {
  const TravelPlansScreen({super.key});
  @override
  State<TravelPlansScreen> createState() => _TravelPlansScreenState();
}

class _TravelPlansScreenState extends State<TravelPlansScreen> {
  final _key = GlobalKey<ActivityDataState>();
  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: const GreenAppBar(title: '내 여행 일정'),
      body: AppContent(
          child: ActivityData(
              key: _key,
              load: () => AppSession.instance.loadPlans(),
              builder: (context, data, refresh) => ListView(
                      padding: const EdgeInsets.all(20),
                      physics: const AlwaysScrollableScrollPhysics(),
                      children: [
                        if (!AppSession.instance.isAuthenticated)
                          const Padding(
                              padding: EdgeInsets.only(bottom: 16),
                              child: Text('이 기기에 저장한 일정입니다.',
                                  style: TextStyle(
                                      fontSize: 12, color: Colors.grey))),
                        if (activityItems(data).isEmpty)
                          const Text('저장한 일정이 없어요.'),
                        ...activityItems(data).map((p) => Card(
                            child: Padding(
                                padding: const EdgeInsets.all(16),
                                child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(p['title'],
                                          style: Theme.of(context)
                                              .textTheme
                                              .titleLarge),
                                      Text(p['date']),
                                      ...((p['stops'] as List?) ?? []).map(
                                          (s) => ListTile(
                                              leading: Text(s['time']),
                                              title: Text(s['place']))),
                                      TextButton(
                                          onPressed: () async {
                                            final yes = await showDialog<bool>(
                                                context: context,
                                                builder: (c) => AlertDialog(
                                                        title: const Text(
                                                            '일정을 삭제할까요?'),
                                                        actions: [
                                                          TextButton(
                                                              onPressed: () =>
                                                                  Navigator.pop(
                                                                      c, false),
                                                              child: const Text(
                                                                  '취소')),
                                                          FilledButton(
                                                              onPressed: () =>
                                                                  Navigator.pop(
                                                                      c, true),
                                                              child: const Text(
                                                                  '삭제'))
                                                        ]));
                                            if (yes != true) return;
                                            try {
                                              await AppSession.instance
                                                  .deletePlan(p['id']);
                                              await refresh();
                                            } catch (e) {
                                              if (context.mounted) {
                                                activityError(context, e);
                                              }
                                            }
                                          },
                                          child: const Text('삭제'))
                                    ])))),
                        OutlinedButton.icon(
                            onPressed: () async {
                              await Navigator.push(
                                  context,
                                  MaterialPageRoute<void>(
                                      builder: (_) => const _PlanForm()));
                              if (mounted) await refresh();
                            },
                            icon: const Icon(Icons.add),
                            label: const Text('새 일정 만들기'))
                      ]))));
}

class _PlanForm extends StatefulWidget {
  const _PlanForm();
  @override
  State<_PlanForm> createState() => _PlanFormState();
}

class _PlanFormState extends State<_PlanForm> {
  final _title = TextEditingController();
  final _place = TextEditingController();
  final _stops = <Map<String, String>>[];
  DateTime? _date;
  TimeOfDay _time = const TimeOfDay(hour: 9, minute: 0);
  bool _busy = false;
  @override
  void dispose() {
    _title.dispose();
    _place.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: const GreenAppBar(title: '새 여행 일정'),
      body: AppContent(
          child: ListView(padding: const EdgeInsets.all(20), children: [
        TextField(
            controller: _title,
            maxLength: 100,
            decoration: const InputDecoration(labelText: '일정 제목')),
        ListTile(
            title: Text(_date?.toIso8601String().substring(0, 10) ?? '날짜 선택'),
            onTap: () async {
              final now = DateTime.now();
              final d = await showDatePicker(
                  context: context,
                  initialDate: _date ?? now,
                  firstDate: DateTime(now.year),
                  lastDate: DateTime(now.year + 3));
              if (d != null && mounted) setState(() => _date = d);
            }),
        ..._stops.asMap().entries.map((e) => ListTile(
            title: Text('${e.value['time']} ${e.value['place']}'),
            trailing: IconButton(
                tooltip: '장소 제거',
                onPressed: () => setState(() => _stops.removeAt(e.key)),
                icon: const Icon(Icons.close)))),
        TextField(
            controller: _place,
            maxLength: 100,
            decoration: const InputDecoration(labelText: '방문 장소')),
        TextButton(
            onPressed: () async {
              final time =
                  await showTimePicker(context: context, initialTime: _time);
              if (time != null && mounted) setState(() => _time = time);
            },
            child: Text('시간 ${_time.format(context)}')),
        OutlinedButton(
            onPressed: () {
              if (_place.text.trim().isEmpty) return;
              setState(() {
                _stops.add({
                  'time':
                      '${_time.hour.toString().padLeft(2, '0')}:${_time.minute.toString().padLeft(2, '0')}',
                  'place': _place.text.trim()
                });
                _stops.sort((a, b) => a['time']!.compareTo(b['time']!));
                _place.clear();
              });
            },
            child: const Text('장소 추가')),
        FilledButton(
            onPressed: _busy
                ? null
                : () async {
                    if (_title.text.trim().isEmpty ||
                        _date == null ||
                        _stops.isEmpty) {
                      activityError(context,
                          const ApiException('제목, 날짜, 방문 장소를 입력해 주세요.'));
                      return;
                    }
                    setState(() => _busy = true);
                    try {
                      await AppSession.instance.savePlan({
                        'title': _title.text.trim(),
                        'date': _date!.toIso8601String().substring(0, 10),
                        'stops': _stops
                      });
                      if (context.mounted) Navigator.pop(context);
                    } catch (e) {
                      if (context.mounted) activityError(context, e);
                    } finally {
                      if (mounted) setState(() => _busy = false);
                    }
                  },
            child: Text(_busy ? '저장 중…' : '일정 저장'))
      ])));
}

class HelpScreen extends StatelessWidget {
  const HelpScreen({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: const GreenAppBar(title: '도움말 및 문의'),
      body: AppContent(
          child: ListView(padding: const EdgeInsets.all(20), children: [
        const ExpansionTile(title: Text('혼잡도 정보는 어떻게 확인하나요?'), children: [
          Padding(
              padding: EdgeInsets.all(16),
              child:
                  Text('장소 상세에서 데이터 출처와 관측 시각을 확인하세요. 자료가 없으면 정보 없음으로 표시됩니다.'))
        ]),
        const ExpansionTile(title: Text('동행 신청을 취소하고 싶어요.'), children: [
          Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                  '동행 내역에서 모집글을 열고 신청 취소를 누르세요. 본인이 만든 모집글은 모집 삭제로 취소할 수 있어요.'))
        ]),
        OutlinedButton(
            onPressed: () async {
              if (!await ensureSignedIn(context) || !context.mounted) return;
              await Navigator.push(
                  context,
                  MaterialPageRoute<void>(
                      builder: (_) => const _InquiryScreen()));
            },
            child: const Text('1:1 문의하기'))
      ])));
}

class _InquiryScreen extends StatefulWidget {
  const _InquiryScreen();
  @override
  State<_InquiryScreen> createState() => _InquiryScreenState();
}

class _InquiryScreenState extends State<_InquiryScreen> {
  final _subject = TextEditingController(), _text = TextEditingController();
  bool _busy = false;
  @override
  void dispose() {
    _subject.dispose();
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: const GreenAppBar(title: '1:1 문의'),
      body: AppContent(
          child: ActivityData(
              authenticated: true,
              load: () => ApiClient.instance.get('/inquiries'),
              builder: (context, data, refresh) =>
                  ListView(padding: const EdgeInsets.all(20), children: [
                    const Text('문의는 계정에 접수됩니다. 답변이 등록되면 이 화면에서 확인할 수 있어요.'),
                    TextField(
                        controller: _subject,
                        maxLength: 100,
                        decoration: const InputDecoration(labelText: '제목')),
                    TextField(
                        controller: _text,
                        maxLength: 3000,
                        minLines: 4,
                        maxLines: 8,
                        decoration: const InputDecoration(labelText: '문의 내용')),
                    FilledButton(
                        onPressed: _busy
                            ? null
                            : () async {
                                if (_subject.text.trim().isEmpty ||
                                    _text.text.trim().isEmpty) {
                                  return;
                                }
                                setState(() => _busy = true);
                                try {
                                  await ApiClient.instance.post('/inquiries',
                                      body: {
                                        'subject': _subject.text.trim(),
                                        'text': _text.text.trim()
                                      });
                                  _subject.clear();
                                  _text.clear();
                                  await refresh();
                                } catch (e) {
                                  if (context.mounted) {
                                    activityError(context, e);
                                  }
                                } finally {
                                  if (mounted) setState(() => _busy = false);
                                }
                              },
                        child: Text(_busy ? '접수 중…' : '문의 접수')),
                    const SizedBox(height: 24),
                    const Text('내 문의 내역'),
                    ...activityItems(data).map((r) => ExpansionTile(
                            title: Text(r['subject']),
                            subtitle: Text(
                                '${r['status'] == 'answered' ? '답변 완료' : '접수됨'} · ${activityDate(r['created_at'])}'),
                            children: [
                              Padding(
                                  padding: const EdgeInsets.all(16),
                                  child: Text(
                                      '${r['text']}\n${r['answer'] ?? '아직 답변이 없어요.'}'))
                            ]))
                  ]))));
}
