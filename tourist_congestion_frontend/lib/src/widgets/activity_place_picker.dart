import 'package:flutter/material.dart';
import '../services/api_client.dart';
import 'activity_data.dart';

Future<Map<String, dynamic>?> selectActivityPlace(BuildContext context) =>
    showModalBottomSheet<Map<String, dynamic>>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (context) => const FractionallySizedBox(
            heightFactor: .8, child: _PlacePicker()));

class _PlacePicker extends StatefulWidget {
  const _PlacePicker();
  @override
  State<_PlacePicker> createState() => _PlacePickerState();
}

class _PlacePickerState extends State<_PlacePicker> {
  final _search = TextEditingController();
  final _items = <Map<String, dynamic>>[];
  int _page = 0, _pages = 1, _generation = 0;
  bool _busy = false;
  Object? _error;
  @override
  void initState() {
    super.initState();
    _load(reset: true);
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({bool reset = false}) async {
    if (_busy && !reset) return;
    final token = ++_generation;
    final page = reset ? 1 : _page + 1;
    setState(() {
      _busy = true;
      _error = null;
      if (reset) _items.clear();
    });
    try {
      final data = await ApiClient.instance.get('/places',
          query: {'keyword': _search.text.trim(), 'page': '$page'});
      if (!mounted || token != _generation) return;
      setState(() {
        _items.addAll(activityItems(data));
        _page = page;
        _pages = (data['pagination']?['total_pages'] as num?)?.toInt() ?? page;
      });
    } catch (e) {
      if (mounted && token == _generation) setState(() => _error = e);
    } finally {
      if (mounted && token == _generation) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => SafeArea(
          child: Column(children: [
        Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
                controller: _search,
                decoration: InputDecoration(
                    labelText: '관광지 검색',
                    suffixIcon: IconButton(
                        tooltip: '검색',
                        onPressed: () => _load(reset: true),
                        icon: const Icon(Icons.search))),
                onSubmitted: (_) => _load(reset: true))),
        Expanded(
            child: ListView(children: [
          ..._items.map((p) => ListTile(
              title: Text(p['name']),
              subtitle: Text(p['address'] ?? ''),
              onTap: () => Navigator.pop(context, p))),
          if (_busy)
            const Padding(
                padding: EdgeInsets.all(20),
                child: Center(child: CircularProgressIndicator())),
          if (_error != null)
            TextButton(
                onPressed: () => _load(reset: _items.isEmpty),
                child: const Text('불러오지 못했어요. 다시 시도')),
          if (!_busy && _error == null && _items.isEmpty)
            const Padding(
                padding: EdgeInsets.all(20), child: Text('검색 결과가 없어요.')),
          if (!_busy && _error == null && _page < _pages)
            TextButton(onPressed: _load, child: const Text('더 보기'))
        ]))
      ]));
}
