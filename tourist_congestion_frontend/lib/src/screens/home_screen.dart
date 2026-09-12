import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../models/place.dart';
import '../services/place_service.dart';
import '../services/place_location.dart';
import '../widgets/app_chrome.dart';
import '../widgets/place_card.dart';
import 'notifications_screen.dart';
import 'auth_screen.dart';
import '../widgets/region_picker.dart';
import '../widgets/place_map.dart';
import 'place_detail_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _search = TextEditingController();
  List<Place> _places = [];
  String _region = '', _crowd = '', _keyword = '';
  String? _error;
  bool _loading = false, _more = false, _nearby = false;
  bool _showList = false;
  int _page = 1, _request = 0;
  int? _selected;
  double? _latitude, _longitude;
  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
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
      final result = _nearby
          ? await PlaceService.instance.nearby(
              latitude: _latitude!,
              longitude: _longitude!,
              radiusKm: 10,
              page: append ? _page + 1 : 1)
          : await PlaceService.instance.list(
              keyword: _keyword,
              regionPath: _region,
              estimateLevel: _crowd,
              page: append ? _page + 1 : 1);
      if (!mounted || request != _request) return;
      setState(() {
        _places = append ? [..._places, ...result.items] : result.items;
        _page = result.page;
        _more = result.hasMore;
        if (!_places.any((p) => p.id == _selected)) {
          _selected = _places.firstOrNull?.id;
        }
      });
    } catch (error) {
      if (mounted && request == _request) setState(() => _error = '$error');
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  Future<void> _locate() async {
    try {
      final p = await locateUser();
      if (!mounted) return;
      setState(() {
        _latitude = p.latitude;
        _longitude = p.longitude;
        _nearby = true;
      });
      await _load();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: GreenAppBar(title: '지금, 이리ON', actions: [
        IconButton(
            tooltip: '알림',
            onPressed: () async {
              if (!await ensureSignedIn(context) || !context.mounted) return;
              await Navigator.push(
                  context,
                  MaterialPageRoute<void>(
                      builder: (_) => const NotificationsScreen()));
            },
            icon: const Icon(Icons.notifications_outlined)),
      ]),
      body: AppContent(
          child: RefreshIndicator(
              onRefresh: () => _load(),
              child: ListView(padding: const EdgeInsets.all(20), children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: SizedBox(
                      width: 240,
                      child: SegmentedButton<bool>(
                        segments: const [
                          ButtonSegment(
                              value: false,
                              label: Text('지도'),
                              icon: Icon(Icons.map_outlined)),
                          ButtonSegment(
                              value: true,
                              label: Text('리스트'),
                              icon: Icon(Icons.list)),
                        ],
                        selected: {_showList},
                        onSelectionChanged: (v) =>
                            setState(() => _showList = v.first),
                      )),
                ),
                const SizedBox(height: 16),
                AppSearchField(
                    controller: _search,
                    hintText: '관광지 또는 지역 검색',
                    onSearch: () {
                      _keyword = _search.text.trim();
                      _nearby = false;
                      _load();
                    },
                    onClear: () {
                      _search.clear();
                      _keyword = '';
                      _nearby = false;
                      _load();
                    },
                    onSubmitted: (v) {
                      _keyword = v.trim();
                      _nearby = false;
                      _load();
                    }),
                const SizedBox(height: 12),
                Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                              minimumSize: const Size(0, 36),
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 10),
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              textStyle: const TextStyle(fontSize: 12),
                              side: const BorderSide(color: AppColors.border),
                              shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(20))),
                          onPressed: () async {
                            final region = await showModalBottomSheet<String>(
                                context: context,
                                isScrollControlled: true,
                                useSafeArea: true,
                                builder: (_) =>
                                    RegionPicker(selected: _region));
                            if (region == null || !mounted) return;
                            setState(() {
                              _region = region;
                              _nearby = false;
                            });
                            _load();
                          },
                          icon:
                              const Icon(Icons.location_on_outlined, size: 16),
                          label: Text(_region.isEmpty
                              ? '전국'
                              : _region.split('/').last)),
                      _filterDropdown(DropdownButton<String>(
                          isDense: true,
                          iconSize: 18,
                          style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: AppColors.text),
                          value: _crowd,
                          items: const [
                            DropdownMenuItem(value: '', child: Text('모든 혼잡도')),
                            DropdownMenuItem(
                                value: 'VERY_LOW', child: Text('매우 여유')),
                            DropdownMenuItem(value: 'LOW', child: Text('여유')),
                            DropdownMenuItem(
                                value: 'NORMAL', child: Text('보통')),
                            DropdownMenuItem(value: 'HIGH', child: Text('혼잡')),
                            DropdownMenuItem(
                                value: 'VERY_HIGH', child: Text('매우 혼잡'))
                          ],
                          onChanged: (v) {
                            setState(() {
                              _crowd = v!;
                              _nearby = false;
                            });
                            _load();
                          })),
                      OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                              fixedSize: const Size.fromHeight(36),
                              minimumSize: const Size(0, 36),
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 10),
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.standard,
                              textStyle: const TextStyle(
                                  fontSize: 12, fontWeight: FontWeight.w500),
                              side: const BorderSide(color: AppColors.border),
                              shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(20))),
                          onPressed: _loading ? null : _locate,
                          icon: const Icon(Icons.my_location, size: 16),
                          label: const Text('내 주변 10km'))
                    ]),
                const SizedBox(height: 20),
                Text(_nearby ? '내 주변 여행지' : '어디로 떠나볼까요?',
                    style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                        color: AppColors.text)),
                const SizedBox(height: 6),
                Text(
                    _nearby
                        ? '내 위치에서 10km 이내 · 직선 거리순'
                        : '전국 예상 혼잡도를 확인하고, 낮은 신뢰도도 함께 살펴보세요.',
                    style: const TextStyle(
                        fontSize: 12, height: 1.5, color: AppColors.textMuted)),
                if (_showList) const SizedBox(height: 16),
                if (_loading) const LinearProgressIndicator(),
                if (_error != null)
                  Column(children: [
                    Text(_error!),
                    TextButton(
                        onPressed: () => _load(append: _places.isNotEmpty),
                        child: const Text('다시 시도'))
                  ]),
                if (!_loading && _error == null && _places.isEmpty)
                  const Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('조건에 맞는 장소가 없습니다. 지역명이나 검색 조건을 바꿔보세요.')),
                if (!_showList && _places.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  SizedBox(
                      height: 320,
                      child: PlacesMap(
                        places: _places,
                        selectedId: _selected,
                        onSelected: (p) => setState(() => _selected = p.id),
                      )),
                  if (!_places.any((p) => p.hasCoordinates))
                    const Text('표시할 장소 좌표가 없습니다. 리스트에서 확인해 주세요.'),
                  const SizedBox(height: 12),
                ],
                for (final p
                    in _places.where((p) => _showList || p.id == _selected))
                  Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: !_showList && p.id == _selected
                          ? BoxDecoration(
                              border: Border.all(
                                  color: Theme.of(context).colorScheme.primary),
                              borderRadius: BorderRadius.circular(16))
                          : null,
                      child: PlaceCard(
                          place: p,
                          onTap: () async {
                            setState(() => _selected = p.id);
                            await Navigator.push(
                                context,
                                MaterialPageRoute<void>(
                                    builder: (_) =>
                                        PlaceDetailScreen(place: p)));
                            if (mounted) {
                              try {
                                final updated =
                                    await PlaceService.instance.detail(p.id);
                                if (mounted) {
                                  setState(() => _places = _places
                                      .map((item) =>
                                          item.id == p.id ? updated : item)
                                      .toList());
                                }
                              } catch (_) {}
                            }
                          })),
                if (_more)
                  TextButton(
                      onPressed: _loading ? null : () => _load(append: true),
                      child: const Text('더 보기'))
              ]))));

  Widget _filterDropdown(Widget child) => Container(
        height: 36,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          border: Border.all(color: AppColors.border),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Center(
            widthFactor: 1, child: DropdownButtonHideUnderline(child: child)),
      );
}
