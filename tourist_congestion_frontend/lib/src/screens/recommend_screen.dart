import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../widgets/app_chrome.dart';
import '../widgets/activity_data.dart';
import '../widgets/region_picker.dart';
import '../services/region_filter.dart';
import 'auth_screen.dart';
import 'companion_detail_screen.dart';
import 'companion_form_screen.dart';

class RecommendScreen extends StatefulWidget {
  const RecommendScreen({super.key, this.mine = false});
  final bool mine;
  @override
  State<RecommendScreen> createState() => _RecommendScreenState();
}

class _RecommendScreenState extends State<RecommendScreen> {
  final _dataKey = GlobalKey<ActivityDataState>();
  final _search = TextEditingController();
  String _query = '';
  String _region = '';
  String _when = 'all';
  bool _openOnly = false;
  bool _soonest = true;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  DateTime? _date;
  bool _past = false;
  Future<void> _open(Map<String, dynamic> item) async {
    await Navigator.push(
        context,
        MaterialPageRoute<void>(
            builder: (_) => CompanionDetailScreen(companion: item)));
    if (mounted) await _dataKey.currentState?.refresh();
  }

  Widget _filterPill(String label, {bool active = false, bool arrow = true}) =>
      Container(
          height: 36,
          padding: const EdgeInsets.symmetric(horizontal: 13),
          decoration: BoxDecoration(
              color: active ? const Color(0xFF2E4636) : Colors.white,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                  color: active
                      ? const Color(0xFF2E4636)
                      : const Color(0xFFDFE5E0))),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Text(label,
                style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                    color: active ? Colors.white : const Color(0xFF424B45))),
            if (arrow) ...[
              const SizedBox(width: 4),
              Icon(Icons.keyboard_arrow_down,
                  size: 16,
                  color: active ? Colors.white : const Color(0xFF79817B))
            ],
          ]));

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: GreenAppBar(title: widget.mine ? '동행 내역' : '그대도 이리온'),
      floatingActionButton: FloatingActionButton(
          tooltip: '동행 모집 작성',
          onPressed: () async {
            if (!await ensureSignedIn(context) || !context.mounted) return;
            await Navigator.push(
                context,
                MaterialPageRoute<bool>(
                    builder: (_) => const CompanionFormScreen()));
            if (mounted) await _dataKey.currentState?.refresh();
          },
          child: const Icon(Icons.add)),
      body: AppContent(
          child: Column(children: [
        Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              TextField(
                  controller: _search,
                  style: const TextStyle(fontSize: 14),
                  textInputAction: TextInputAction.search,
                  decoration: const InputDecoration(
                      hintText: '어디로 함께 떠날까요?',
                      prefixIcon: Icon(Icons.search, size: 20)),
                  onChanged: (v) => setState(() => _query = v.trim())),
            ])),
        Expanded(
            child: ActivityData(
                key: _dataKey,
                authenticated: widget.mine,
                load: () => ApiClient.instance.get('/companions', query: {
                      if (widget.mine) 'mine': 'true',
                    }),
                builder: (context, data, refresh) {
                  final today =
                      DateTime.now().toIso8601String().substring(0, 10);
                  final all = activityItems(data);
                  final now = DateTime.now();
                  final day = DateTime(now.year, now.month, now.day);
                  final saturday = day.add(
                      Duration(days: now.weekday == 7 ? -1 : 6 - now.weekday));
                  final sunday = saturday.add(const Duration(days: 1));
                  final items = all
                      .where((r) =>
                          '${r['place_name']} ${r['place_address'] ?? ''} ${r['title']} ${r['text']} ${r['author_nickname']}'
                              .toLowerCase()
                              .contains(_query.toLowerCase()) &&
                          matchesRegionPath(
                              '${r['place_address'] ?? ''}', _region) &&
                          (!_openOnly ||
                              ((r['date'] as String).compareTo(today) >= 0 &&
                                  (r['member_count'] as num) <
                                      (r['capacity'] as num))) &&
                          (_when == 'all' ||
                              (_when == 'today' && r['date'] == today) ||
                              (_when == 'date' &&
                                  r['date'] ==
                                      _date!
                                          .toIso8601String()
                                          .substring(0, 10)) ||
                              (_when == 'weekend' &&
                                  (r['date'] ==
                                          saturday
                                              .toIso8601String()
                                              .substring(0, 10) ||
                                      r['date'] ==
                                          sunday
                                              .toIso8601String()
                                              .substring(0, 10)))) &&
                          (!widget.mine ||
                              ((r['date'] as String).compareTo(today) < 0) ==
                                  _past))
                      .toList();
                  items.sort((a, b) => _soonest
                      ? '${a['date']}'.compareTo('${b['date']}')
                      : (b['id'] as num).compareTo(a['id'] as num));
                  return ListView(
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 96),
                      physics: const AlwaysScrollableScrollPhysics(),
                      children: [
                        SingleChildScrollView(
                            scrollDirection: Axis.horizontal,
                            child: Row(children: [
                              InkWell(
                                  borderRadius: BorderRadius.circular(20),
                                  onTap: () async {
                                    final region =
                                        await showModalBottomSheet<String>(
                                            context: context,
                                            isScrollControlled: true,
                                            useSafeArea: true,
                                            builder: (_) => RegionPicker(
                                                selected: _region));
                                    if (region != null && mounted) {
                                      setState(() => _region = region);
                                    }
                                  },
                                  child: _filterPill(
                                      _region.isEmpty
                                          ? '전국'
                                          : _region.split('/').last,
                                      active: _region.isNotEmpty)),
                              const SizedBox(width: 8),
                              PopupMenuButton<String>(
                                  tooltip: '날짜 선택',
                                  onSelected: (v) async {
                                    if (v != 'date') {
                                      setState(() {
                                        _when = v;
                                        _date = null;
                                      });
                                      return;
                                    }
                                    final now = DateTime.now();
                                    final value = await showDatePicker(
                                        context: context,
                                        initialDate: _date ?? now,
                                        firstDate: DateTime(now.year - 1),
                                        lastDate: DateTime(now.year + 3));
                                    if (value != null && mounted) {
                                      setState(() {
                                        _date = value;
                                        _when = 'date';
                                      });
                                    }
                                  },
                                  itemBuilder: (_) => const [
                                        PopupMenuItem(
                                            value: 'all', child: Text('전체 날짜')),
                                        PopupMenuItem(
                                            value: 'today', child: Text('오늘')),
                                        PopupMenuItem(
                                            value: 'weekend',
                                            child: Text('이번 주말')),
                                        PopupMenuItem(
                                            value: 'date', child: Text('직접 선택'))
                                      ],
                                  child: _filterPill(
                                      _when == 'today'
                                          ? '오늘'
                                          : _when == 'weekend'
                                              ? '이번 주말'
                                              : _date != null
                                                  ? '${_date!.month}.${_date!.day}'
                                                  : '날짜',
                                      active: _when != 'all')),
                              const SizedBox(width: 8),
                              InkWell(
                                  borderRadius: BorderRadius.circular(20),
                                  onTap: () =>
                                      setState(() => _openOnly = !_openOnly),
                                  child: _filterPill('모집 중만',
                                      active: _openOnly, arrow: false)),
                              if (widget.mine) ...[
                                const SizedBox(width: 8),
                                InkWell(
                                    onTap: () => setState(() => _past = !_past),
                                    child: _filterPill('지난 일정',
                                        active: _past, arrow: false))
                              ],
                            ])),
                        const SizedBox(height: 20),
                        const Divider(height: 1, color: Color(0xFFE8ECE9)),
                        const SizedBox(height: 14),
                        Row(children: [
                          Expanded(
                              child: Text('함께할 동행 ${items.length}개',
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w700))),
                          PopupMenuButton<bool>(
                              tooltip: '동행 정렬',
                              initialValue: _soonest,
                              onSelected: (v) => setState(() => _soonest = v),
                              itemBuilder: (_) => const [
                                    PopupMenuItem(
                                        value: true, child: Text('일정 빠른순')),
                                    PopupMenuItem(
                                        value: false, child: Text('최신 등록순'))
                                  ],
                              child: Row(children: [
                                Text(_soonest ? '일정 빠른순' : '최신 등록순'),
                                const Icon(Icons.expand_more, size: 18)
                              ])),
                          if (_query.isNotEmpty ||
                              _region.isNotEmpty ||
                              _when != 'all' ||
                              _openOnly)
                            TextButton(
                                onPressed: () => setState(() {
                                      _search.clear();
                                      _query = '';
                                      _region = '';
                                      _when = 'all';
                                      _date = null;
                                      _openOnly = false;
                                    }),
                                child: const Text('초기화'))
                        ]),
                        const SizedBox(height: 8),
                        if (items.isEmpty)
                          const Padding(
                              padding: EdgeInsets.all(30),
                              child: Text('조건에 맞는 동행이 없어요.')),
                        ...items.map((r) => Card(
                            margin: const EdgeInsets.only(bottom: 12),
                            child: ListTile(
                                title:
                                    Text(r['title'] ?? r['place_name'] ?? ''),
                                subtitle: Text(
                                    '${r['place_name']} · ${r['date']}\n${r['author_nickname']}'),
                                isThreeLine: true,
                                trailing: Text(
                                    '${r['member_count']}/${r['capacity']}명'),
                                onTap: () => _open(r))))
                      ]);
                }))
      ])));
}
