import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import '../theme/app_theme.dart';
import 'package:url_launcher/url_launcher.dart';
import 'saved_screen.dart';
import '../models/place.dart';
import '../services/app_session.dart';
import '../services/place_service.dart';
import '../services/place_location.dart';
import '../widgets/app_chrome.dart';
import '../widgets/place_image.dart';
import '../widgets/crowd_badge.dart';
import '../widgets/crowd_evidence.dart';
import 'nearby_places_screen.dart';

class PlaceDetailScreen extends StatefulWidget {
  const PlaceDetailScreen({super.key, required this.place});
  final Place place;
  @override
  State<PlaceDetailScreen> createState() => _PlaceDetailScreenState();
}

class _PlaceDetailScreenState extends State<PlaceDetailScreen> {
  late Place _place;
  bool _loading = true, _saving = false;
  String? _error;
  final _scroll = ScrollController();
  final _anchors = List.generate(3, (_) => GlobalKey());
  int _selectedSection = 0;
  static const _tabHeight = 52.0;

  double? _sectionOffset(int index) {
    final render = _anchors[index].currentContext?.findRenderObject();
    if (render == null || !render.attached) return null;
    return RenderAbstractViewport.of(render)
        .getOffsetToReveal(render, 0)
        .offset;
  }

  void _syncSection() {
    if (!_scroll.hasClients) return;
    var selected = 0;
    for (var i = 0; i < _anchors.length; i++) {
      final offset = _sectionOffset(i);
      if (offset != null && _scroll.offset >= offset - 1) selected = i;
    }
    if (selected != _selectedSection && mounted) {
      setState(() => _selectedSection = selected);
    }
  }

  void _jumpToSection(int index) {
    final offset = _sectionOffset(index);
    if (offset == null || !_scroll.hasClients) return;
    _scroll.jumpTo(offset.clamp(0.0, _scroll.position.maxScrollExtent));
    setState(() => _selectedSection = index);
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_syncSection);
    _place = widget.place;
    _load();
    _recordRecent();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final p = await PlaceService.instance.detail(widget.place.id);
      if (mounted) setState(() => _place = p);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _recordRecent() async {
    try {
      await AppSession.instance.recordRecent(widget.place.id);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('최근 본 장소 저장 실패: $e')));
      }
    }
  }

  Future<void> _website() async {
    final uri = Uri.tryParse(_place.homepageUrl ?? '');
    try {
      if (uri == null ||
          !['http', 'https'].contains(uri.scheme) ||
          !await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        throw Exception('웹사이트를 열 수 없습니다.');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await AppSession.instance.toggleFavorite(_place.id);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: AppSession.instance,
      builder: (context, _) => Scaffold(
          appBar: GreenAppBar(title: _place.name, actions: [
            IconButton(
                tooltip: AppSession.instance.favoriteIds.contains(_place.id)
                    ? '즐겨찾기 해제'
                    : '즐겨찾기 저장',
                onPressed: _saving ? null : _save,
                icon: Icon(AppSession.instance.favoriteIds.contains(_place.id)
                    ? Icons.favorite
                    : Icons.favorite_border))
          ]),
          body: AppContent(
              child: RefreshIndicator(
                  onRefresh: _load,
                  child: LayoutBuilder(
                      builder: (context, constraints) => CustomScrollView(
                              controller: _scroll,
                              physics: const AlwaysScrollableScrollPhysics(),
                              slivers: [
                                SliverToBoxAdapter(
                                    child: Padding(
                                        padding: const EdgeInsets.all(20),
                                        child: Column(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.stretch,
                                            children: [
                                              if (_loading)
                                                const LinearProgressIndicator(),
                                              if (_error != null) ...[
                                                Text(
                                                    '상세 정보를 갱신하지 못했습니다. 목록 정보를 표시합니다.\n$_error'),
                                                TextButton(
                                                    onPressed: _load,
                                                    child: const Text('다시 시도'))
                                              ],
                                              GestureDetector(
                                                  onTap: _place.imageUrl == null
                                                      ? null
                                                      : () => showDialog<void>(
                                                          context: context,
                                                          builder: (context) =>
                                                              Dialog(
                                                                  child: Stack(
                                                                      children: [
                                                                    InteractiveViewer(
                                                                        child: PlaceImage(
                                                                            url: _place
                                                                                .imageUrl,
                                                                            height:
                                                                                400,
                                                                            width:
                                                                                double.infinity)),
                                                                    Positioned(
                                                                        right:
                                                                            4,
                                                                        top: 4,
                                                                        child: IconButton.filled(
                                                                            tooltip:
                                                                                '닫기',
                                                                            onPressed: () =>
                                                                                Navigator.pop(context),
                                                                            icon: const Icon(Icons.close)))
                                                                  ]))),
                                                  child: PlaceImage(
                                                      url: _place.imageUrl,
                                                      height: 210,
                                                      width: double.infinity)),
                                              const SizedBox(height: 16),
                                              Row(
                                                  crossAxisAlignment:
                                                      CrossAxisAlignment.start,
                                                  children: [
                                                    Expanded(
                                                        child: Text(_place.name,
                                                            style: Theme.of(
                                                                    context)
                                                                .textTheme
                                                                .headlineSmall)),
                                                    const SizedBox(width: 12),
                                                    FilledButton.icon(
                                                      style: FilledButton
                                                          .styleFrom(
                                                        minimumSize:
                                                            const Size(0, 40),
                                                        padding:
                                                            const EdgeInsets
                                                                .symmetric(
                                                                horizontal: 12),
                                                        textStyle:
                                                            const TextStyle(
                                                                fontSize: 12,
                                                                fontWeight:
                                                                    FontWeight
                                                                        .w700),
                                                      ),
                                                      onPressed: _place
                                                              .hasCoordinates
                                                          ? () =>
                                                              openPlaceDirections(
                                                                  context,
                                                                  _place)
                                                          : null,
                                                      icon: const Icon(
                                                          Icons
                                                              .directions_outlined,
                                                          size: 17),
                                                      label: const Text(
                                                          '카카오맵 길찾기'),
                                                    ),
                                                  ]),
                                              const SizedBox(height: 6),
                                              Row(children: [
                                                Text(_place.category,
                                                    style: const TextStyle(
                                                        color:
                                                            Color(0xFF7A8980),
                                                        fontSize: 13)),
                                                if (_place.rating != null) ...[
                                                  const SizedBox(width: 12),
                                                  const Icon(Icons.star_rounded,
                                                      size: 17,
                                                      color: Color(0xFFE9B65B)),
                                                  const SizedBox(width: 4),
                                                  Text(
                                                      _place.rating!
                                                          .toStringAsFixed(1),
                                                      style: const TextStyle(
                                                          fontWeight:
                                                              FontWeight.w700)),
                                                  const Text(' / 5',
                                                      style: TextStyle(
                                                          color:
                                                              Color(0xFF7A8980),
                                                          fontSize: 12)),
                                                ],
                                              ]),
                                              const SizedBox(height: 16),
                                              Material(
                                                  type:
                                                      MaterialType.transparency,
                                                  child: Column(
                                                      crossAxisAlignment:
                                                          CrossAxisAlignment
                                                              .start,
                                                      children: [
                                                        Row(children: [
                                                          const Icon(
                                                              Icons
                                                                  .people_outline_rounded,
                                                              size: 20,
                                                              color: Color(
                                                                  0xFF56806A)),
                                                          const SizedBox(
                                                              width: 8),
                                                          const Text('지금의 혼잡도',
                                                              style: TextStyle(
                                                                  fontSize: 13,
                                                                  color: Color(
                                                                      0xFF617066),
                                                                  fontWeight:
                                                                      FontWeight
                                                                          .w600)),
                                                          const SizedBox(
                                                              width: 10),
                                                          CrowdBadge(
                                                              label: _place
                                                                  .crowdText,
                                                              color: _place
                                                                  .crowdColor),
                                                          if (!_place.isStale &&
                                                              _observedTime !=
                                                                  null) ...[
                                                            const SizedBox(
                                                                width: 8),
                                                            Text(_observedTime!,
                                                                style: const TextStyle(
                                                                    fontSize:
                                                                        11,
                                                                    color: Color(
                                                                        0xFF7A8980))),
                                                          ],
                                                        ]),
                                                        const SizedBox(
                                                            height: 14),
                                                        if (_place.isDemo)
                                                          _notice(
                                                              '개발 샘플 · 실제 현장 혼잡도가 아닙니다.',
                                                              Icons
                                                                  .science_outlined),
                                                        if (_place.isStale) ...[
                                                          const SizedBox(
                                                              height: 8),
                                                          _notice(
                                                              '오래된 정보',
                                                              Icons
                                                                  .history_rounded,
                                                              warning: true,
                                                              time:
                                                                  _observedTime),
                                                        ],
                                                        if (_place.crowdLevel ==
                                                            null)
                                                          const Text(
                                                              '이 장소의 혼잡도 관측 자료가 없습니다.',
                                                              style: TextStyle(
                                                                  color: Color(
                                                                      0xFF7A8980),
                                                                  fontSize:
                                                                      13)),
                                                      ])),
                                            ]))),
                                SliverPersistentHeader(
                                    pinned: true,
                                    delegate: _PlaceSectionsHeader(
                                      selected: _selectedSection,
                                      onSelected: _jumpToSection,
                                    )),
                                SliverToBoxAdapter(
                                    child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.stretch,
                                        children: [
                                      _detailSection(
                                          key: _anchors[0],
                                          title: '장소소개',
                                          children: [
                                            Text(
                                                _place.description.isEmpty
                                                    ? '등록된 장소 소개가 없습니다.'
                                                    : _place.description,
                                                style: const TextStyle(
                                                    fontSize: 15,
                                                    height: 1.8,
                                                    color: AppColors.text)),
                                            const SizedBox(height: 24),
                                            OutlinedButton(
                                                style: OutlinedButton.styleFrom(
                                                    padding: const EdgeInsets
                                                        .symmetric(
                                                        horizontal: 16,
                                                        vertical: 16),
                                                    backgroundColor:
                                                        const Color(0xFFEFF6EF),
                                                    side: BorderSide.none),
                                                onPressed: _place.hasCoordinates
                                                    ? () => Navigator.push(
                                                        context,
                                                        MaterialPageRoute<void>(
                                                            builder: (_) =>
                                                                NearbyPlacesScreen(
                                                                    place:
                                                                        _place)))
                                                    : null,
                                                child: const Row(children: [
                                                  Icon(Icons.explore_outlined,
                                                      size: 20),
                                                  SizedBox(width: 10),
                                                  Expanded(
                                                      child: Text(
                                                          '이리ON, 비슷한 곳 보기',
                                                          style: TextStyle(
                                                              fontWeight:
                                                                  FontWeight
                                                                      .w700))),
                                                  Icon(Icons.chevron_right,
                                                      size: 20)
                                                ])),
                                          ]),
                                      _detailSection(
                                          key: _anchors[1],
                                          title: '이용정보',
                                          children: [
                                            _info('주소', _place.area,
                                                icon:
                                                    Icons.location_on_outlined),
                                            const Divider(
                                                height: 24,
                                                color: AppColors.border),
                                            _info('운영시간', _place.openingHours,
                                                icon: Icons.schedule_rounded),
                                            _info('휴무', _place.holidays,
                                                icon:
                                                    Icons.event_busy_outlined),
                                            _info('연락처', _place.phone,
                                                icon: Icons.call_outlined),
                                            _info('입장료', _place.admissionFee,
                                                icon: Icons
                                                    .confirmation_number_outlined),
                                            _info('주차', _place.parking,
                                                icon: Icons
                                                    .local_parking_rounded),
                                            const SizedBox(height: 16),
                                            const Text(
                                                '운영 정보는 변경될 수 있어요. 방문 전 운영기관에 확인해 주세요.',
                                                style: TextStyle(
                                                    fontSize: 12,
                                                    height: 1.6,
                                                    color:
                                                        AppColors.textMuted)),
                                            if (_place.homepageUrl != null)
                                              TextButton(
                                                  onPressed: _website,
                                                  child: const Text('공식 웹사이트')),
                                            Material(
                                                type: MaterialType.transparency,
                                                child: Theme(
                                                    data: Theme.of(context)
                                                        .copyWith(
                                                            dividerColor: Colors
                                                                .transparent),
                                                    child: ExpansionTile(
                                                      tilePadding:
                                                          EdgeInsets.zero,
                                                      childrenPadding:
                                                          const EdgeInsets.only(
                                                              bottom: 4),
                                                      dense: true,
                                                      title: const Text(
                                                          '관측 정보 자세히',
                                                          style: TextStyle(
                                                              fontSize: 12,
                                                              color: Color(
                                                                  0xFF64806F))),
                                                      children: [
                                                        if (_place
                                                                .crowdSource !=
                                                            null)
                                                          _info(
                                                              '출처',
                                                              _place
                                                                  .crowdSource),
                                                        if (_place.crowdArea !=
                                                            null)
                                                          _info('관측 구역',
                                                              _place.crowdArea),
                                                        Text(
                                                            _place.isReplaced
                                                                ? '이전 관측값으로 대체된 자료입니다.'
                                                                : '서울시 제공 관측 구역 자료입니다. 위의 자체 예상 혼잡도와 구분됩니다.',
                                                            style: const TextStyle(
                                                                fontSize: 12,
                                                                color: Color(
                                                                    0xFF7A8980))),
                                                        if (_place.crowdMessage
                                                            .isNotEmpty)
                                                          Padding(
                                                              padding:
                                                                  const EdgeInsets
                                                                      .only(
                                                                      top: 8),
                                                              child: Text(
                                                                  _place
                                                                      .crowdMessage,
                                                                  style: const TextStyle(
                                                                      fontSize:
                                                                          12,
                                                                      color: Color(
                                                                          0xFF7A8980)))),
                                                      ],
                                                    ))),
                                            if (_place.crowdEstimate != null)
                                              Padding(
                                                  padding:
                                                      const EdgeInsets.all(16),
                                                  child: CrowdEvidence(
                                                      estimate: _place
                                                          .crowdEstimate!)),
                                            if (!_place.hasCoordinates)
                                              const Text(
                                                  '좌표 정보가 없어 지도 기능을 이용할 수 없습니다.'),
                                          ]),
                                      Container(
                                          key: _anchors[2],
                                          constraints: BoxConstraints(
                                              minHeight: (constraints
                                                          .maxHeight -
                                                      _tabHeight)
                                                  .clamp(0, double.infinity)),
                                          color: AppColors.surface,
                                          child: ReviewFeed(
                                              embedded: true,
                                              placeId: _place.id,
                                              placeName: _place.name)),
                                    ])),
                              ]))))));

  Widget _detailSection(
          {required Key key,
          required String title,
          required List<Widget> children}) =>
      Container(
        key: key,
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.fromLTRB(20, 28, 20, 28),
        color: AppColors.surface,
        child:
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(title,
              style:
                  const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
          const SizedBox(height: 20),
          ...children,
        ]),
      );

  String? get _observedTime {
    final time = _place.observedAt?.toLocal();
    if (time == null) return null;
    return "${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}";
  }

  Widget _notice(String text, IconData icon,
          {bool warning = false, String? time}) =>
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
        decoration: BoxDecoration(
            color: warning ? const Color(0xFFFFF6E8) : const Color(0xFFF1F5F2),
            borderRadius: BorderRadius.circular(10)),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon,
              size: 16,
              color:
                  warning ? const Color(0xFFA87531) : const Color(0xFF708477)),
          const SizedBox(width: 7),
          Expanded(
              child: Text.rich(
                  TextSpan(text: text, children: [
                    if (time != null)
                      TextSpan(
                          text: "  $time",
                          style: const TextStyle(
                              fontSize: 10, fontWeight: FontWeight.w400)),
                  ]),
                  style: TextStyle(
                      fontSize: 12,
                      height: 1.4,
                      color: warning
                          ? const Color(0xFFA87531)
                          : const Color(0xFF708477)))),
        ]),
      );

  Widget _info(String label, String? value, {IconData? icon}) {
    final missing = value == null || value.trim().isEmpty;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (icon != null) ...[
          Icon(icon, size: 18, color: const Color(0xFF8A9D8F)),
          const SizedBox(width: 10)
        ],
        SizedBox(
            width: 64,
            child: Text(label,
                style:
                    const TextStyle(fontSize: 12, color: Color(0xFF7A8980)))),
        Expanded(
            child: Text(missing ? '등록된 정보 없음' : value,
                style: TextStyle(
                    fontSize: 13,
                    height: 1.5,
                    color: missing
                        ? const Color(0xFFA1AAA4)
                        : const Color(0xFF3F5145)))),
      ]),
    );
  }
}

class _PlaceSectionsHeader extends SliverPersistentHeaderDelegate {
  _PlaceSectionsHeader({required this.selected, required this.onSelected});
  final int selected;
  final ValueChanged<int> onSelected;
  @override
  double get minExtent => 52;
  @override
  double get maxExtent => 52;
  @override
  Widget build(
          BuildContext context, double shrinkOffset, bool overlapsContent) =>
      Material(
          color: AppColors.surface,
          child: Container(
              decoration: const BoxDecoration(
                  border: Border(bottom: BorderSide(color: AppColors.border))),
              child: Row(children: [
                for (var i = 0; i < 3; i++)
                  Expanded(
                      child: Semantics(
                          selected: selected == i,
                          child: InkWell(
                              onTap: () => onSelected(i),
                              child: Container(
                                alignment: Alignment.center,
                                decoration: BoxDecoration(
                                    border: Border(
                                        bottom: BorderSide(
                                            color: selected == i
                                                ? AppColors.primary
                                                : Colors.transparent,
                                            width: 2))),
                                child: Text(const ['장소소개', '이용정보', '후기'][i],
                                    style: TextStyle(
                                        fontSize: 14,
                                        fontWeight: selected == i
                                            ? FontWeight.w700
                                            : FontWeight.w500,
                                        color: selected == i
                                            ? AppColors.primary
                                            : AppColors.textMuted)),
                              )))),
              ])));
  @override
  bool shouldRebuild(covariant _PlaceSectionsHeader oldDelegate) =>
      oldDelegate.selected != selected || oldDelegate.onSelected != onSelected;
}
