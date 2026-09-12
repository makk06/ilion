import 'package:flutter/material.dart';
import '../models/place.dart';
import '../services/place_service.dart';
import '../widgets/app_chrome.dart';
import '../widgets/place_card.dart';
import 'map_screen.dart';
import 'place_detail_screen.dart';

class NearbyPlacesScreen extends StatefulWidget {
  const NearbyPlacesScreen({super.key, required this.place});
  final Place place;
  @override
  State<NearbyPlacesScreen> createState() => _NearbyPlacesScreenState();
}

class _NearbyPlacesScreenState extends State<NearbyPlacesScreen> {
  List<Place> _places = [];
  bool _loading = true, _sameCategory = true, _more = false, _relaxed = false;
  String? _error;
  int _page = 1, _request = 0;
  int? _selected;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool append = false}) async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _error = null;
      if (!append) {
        _places = [];
        _page = 1;
        _more = false;
      }
    });
    try {
      final result = await PlaceService.instance.nearby(
          latitude: widget.place.latitude!,
          longitude: widget.place.longitude!,
          category: _sameCategory ? widget.place.category : '',
          estimateLevel: _relaxed ? 'LOW' : '',
          page: append ? _page + 1 : 1);
      if (mounted && request == _request) {
        setState(() {
          final items = result.items
              .where((p) =>
                  p.id != widget.place.id &&
                  (!_relaxed ||
                      (!p.isStale &&
                          p.observedAt != null &&
                          !p.isReplaced &&
                          !p.isDemo)))
              .toList();
          _places = append ? [..._places, ...items] : items;
          _page = result.page;
          _more = result.hasMore;
        });
      }
    } catch (e) {
      if (mounted && request == _request) setState(() => _error = '$e');
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: GreenAppBar(title: '주변 장소 둘러보기', actions: [
        IconButton(
            tooltip: '지도로 비교',
            color: Colors.white,
            disabledColor: Colors.white38,
            onPressed: _places.isEmpty
                ? null
                : () async {
                    final id = await Navigator.push<int>(
                        context,
                        MaterialPageRoute(
                            builder: (_) => MapScreen(
                                places: _places, selectedId: _selected)));
                    if (mounted) setState(() => _selected = id);
                  },
            icon: const Icon(Icons.map_outlined))
      ]),
      body: AppContent(
          child: RefreshIndicator(
              onRefresh: () => _load(),
              child: ListView(padding: const EdgeInsets.all(20), children: [
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: const Color(0xFFE4EBE5))),
                  child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                            width: 44,
                            height: 44,
                            decoration: BoxDecoration(
                                color: const Color(0xFFEDF4EE),
                                borderRadius: BorderRadius.circular(13)),
                            child: const Icon(Icons.near_me_outlined,
                                color: Color(0xFF67866D))),
                        const SizedBox(width: 14),
                        Expanded(
                            child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                              const Text('이 장소를 기준으로',
                                  style: TextStyle(
                                      fontSize: 11, color: Color(0xFF839086))),
                              const SizedBox(height: 5),
                              Text(widget.place.name,
                                  style: const TextStyle(
                                      fontSize: 18,
                                      fontWeight: FontWeight.w700)),
                              const SizedBox(height: 8),
                              const Text('반경 10km · 가까운 순',
                                  style: TextStyle(
                                      fontSize: 12, color: Color(0xFF63816A))),
                            ])),
                      ]),
                ),
                const SizedBox(height: 24),
                const Text('어떤 곳을 찾으세요?',
                    style:
                        TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                const SizedBox(height: 12),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  FilterChip(
                    label: const Text('같은 종류', style: TextStyle(fontSize: 13)),
                    avatar: const Icon(Icons.category_outlined, size: 17),
                    selected: _sameCategory,
                    onSelected: (v) {
                      setState(() => _sameCategory = v);
                      _load();
                    },
                    selectedColor: const Color(0xFFE4EFE3),
                    backgroundColor: Colors.white,
                    side: const BorderSide(color: Color(0xFFDDE6DC)),
                  ),
                  FilterChip(
                    label: const Text('여유로운 곳', style: TextStyle(fontSize: 13)),
                    avatar: const Icon(Icons.spa_outlined, size: 17),
                    selected: _relaxed,
                    onSelected: (v) {
                      setState(() => _relaxed = v);
                      _load();
                    },
                    selectedColor: const Color(0xFFE4EFE3),
                    backgroundColor: Colors.white,
                    side: const BorderSide(color: Color(0xFFDDE6DC)),
                  ),
                ]),
                const SizedBox(height: 8),
                Text(
                    _relaxed
                        ? '예상 혼잡도가 여유 단계인 곳입니다. 낮은 신뢰도도 함께 확인해 주세요.'
                        : _sameCategory && widget.place.category.isNotEmpty
                            ? '${widget.place.category} 분류의 주변 장소를 찾아드려요.'
                            : '종류에 상관없이 가까운 장소를 찾아드려요.',
                    style: const TextStyle(
                        fontSize: 12, height: 1.5, color: Color(0xFF839086))),
                const SizedBox(height: 24),
                if (_loading) const LinearProgressIndicator(),
                if (_error != null) ...[
                  Text(_error!),
                  TextButton(
                      onPressed: () => _load(append: _places.isNotEmpty),
                      child: const Text('다시 시도'))
                ],
                if (!_loading && _error == null && _places.isEmpty)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 24, vertical: 32),
                    decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: const Color(0xFFE4EBE5))),
                    child: Column(children: [
                      Container(
                          padding: const EdgeInsets.all(18),
                          decoration: const BoxDecoration(
                              color: Color(0xFFF0F5EF), shape: BoxShape.circle),
                          child: const Icon(Icons.travel_explore_rounded,
                              size: 32, color: Color(0xFF8CA38D))),
                      const SizedBox(height: 18),
                      Text(_more ? '다음 장소도 살펴볼까요?' : '조건에 맞는 장소가 아직 없어요',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 8),
                      Text(
                          _more
                              ? '다음 결과에서 주변 장소를 더 찾아보세요.'
                              : _sameCategory || _relaxed
                                  ? '필터를 풀면 더 다양한 주변 장소를\n만날 수 있어요.'
                                  : '반경 10km 안에 등록된 다른 장소가 없어요.',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              fontSize: 13,
                              height: 1.6,
                              color: Color(0xFF839086))),
                      if (!_more && (_sameCategory || _relaxed)) ...[
                        const SizedBox(height: 20),
                        FilledButton(
                            onPressed: () {
                              setState(() {
                                _sameCategory = false;
                                _relaxed = false;
                              });
                              _load();
                            },
                            child: const Text('주변 장소 전체 보기')),
                      ],
                    ]),
                  ),
                if (_places.isNotEmpty) ...[
                  Row(children: [
                    const Expanded(
                        child: Text('가까운 주변 장소',
                            style: TextStyle(
                                fontSize: 16, fontWeight: FontWeight.w700))),
                    Text('${_places.length}곳${_more ? '+' : ''}',
                        style: const TextStyle(
                            fontSize: 13, color: Color(0xFF63816A)))
                  ]),
                  const SizedBox(height: 12),
                ],
                for (final p in _places)
                  Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: PlaceCard(
                          place: p,
                          onTap: () {
                            setState(() => _selected = p.id);
                            Navigator.push(
                                context,
                                MaterialPageRoute<void>(
                                    builder: (_) =>
                                        PlaceDetailScreen(place: p)));
                          })),
                if (_more)
                  TextButton(
                      onPressed: _loading ? null : () => _load(append: true),
                      child: const Text('더 보기')),
                const SizedBox(height: 16),
                const Text('거리는 직선 기준이며 실제 이동 거리·시간과 다를 수 있어요.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        fontSize: 11, height: 1.5, color: Color(0xFF8A958C)))
              ]))));
}
