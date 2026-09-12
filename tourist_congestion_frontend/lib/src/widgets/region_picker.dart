import 'package:flutter/material.dart';
import '../services/api_client.dart';

class RegionPicker extends StatefulWidget {
  const RegionPicker({super.key, required this.selected});
  final String selected;
  @override
  State<RegionPicker> createState() => _RegionPickerState();
}

class _RegionPickerState extends State<RegionPicker> {
  List<Map<String, dynamic>>? _roots;
  final List<Map<String, dynamic>> _trail = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final data = await ApiClient.instance.get('/places/regions') as Map;
      if (!mounted) return;
      setState(() {
        _roots = (data['items'] as List).cast<Map<String, dynamic>>();
        _trail.clear();
        var nodes = _roots!;
        for (final name in widget.selected.split('/')) {
          final node = nodes.where((n) => n['name'] == name).firstOrNull;
          if (node == null) break;
          _trail.add(node);
          nodes = (node['children'] as List).cast<Map<String, dynamic>>();
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final nodes = _trail.isEmpty
        ? _roots ?? <Map<String, dynamic>>[]
        : (_trail.last['children'] as List).cast<Map<String, dynamic>>();
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * .7,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Expanded(
                child: Text('지역 선택',
                    style:
                        TextStyle(fontSize: 20, fontWeight: FontWeight.w700))),
            IconButton(
                tooltip: '닫기',
                onPressed: () => Navigator.pop(context),
                icon: const Icon(Icons.close)),
          ]),
          const Text('등록된 장소가 있는 지역을 단계별로 선택하세요.',
              style: TextStyle(fontSize: 12, color: Colors.grey)),
          const SizedBox(height: 12),
          Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
            TextButton(
                onPressed: () => setState(_trail.clear),
                child: const Text('전국')),
            for (var i = 0; i < _trail.length; i++) ...[
              const Icon(Icons.chevron_right, size: 16),
              TextButton(
                  onPressed: () =>
                      setState(() => _trail.removeRange(i + 1, _trail.length)),
                  child: Text(_trail[i]['name'] as String)),
            ],
          ]),
          const Divider(),
          Expanded(
              child: _error != null
                  ? Center(
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                      Text(_error!),
                      TextButton(onPressed: _load, child: const Text('다시 시도'))
                    ]))
                  : _roots == null
                      ? const Center(child: CircularProgressIndicator())
                      : ListView(children: [
                          ListTile(
                              title: Text(_trail.isEmpty
                                  ? '전국 전체'
                                  : '${_trail.last['name']} 전체'),
                              leading: const Icon(Icons.check_circle_outline),
                              onTap: () => Navigator.pop(
                                  context,
                                  _trail.isEmpty
                                      ? ''
                                      : _trail.last['path'] as String)),
                          for (final node in nodes)
                            ListTile(
                                title: Text(node['name'] as String),
                                trailing: const Icon(Icons.chevron_right),
                                onTap: () => setState(() => _trail.add(node))),
                        ])),
          SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _roots == null || _error != null
                    ? null
                    : () => Navigator.pop(context,
                        _trail.isEmpty ? '' : _trail.last['path'] as String),
                child: Text(
                    _trail.isEmpty ? '전국으로 보기' : '${_trail.last['name']} 선택'),
              )),
        ]),
      ),
    );
  }
}
