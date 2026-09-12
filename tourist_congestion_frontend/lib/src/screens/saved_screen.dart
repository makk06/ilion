import '../services/activity_changes.dart';
import '../theme/app_theme.dart';
import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';
import 'auth_screen.dart';
import 'review_form_screen.dart';

class SavedScreen extends StatelessWidget {
  const SavedScreen({super.key, this.mine = false});
  final bool mine;
  @override
  Widget build(BuildContext context) => ReviewFeed(mine: mine);
}

class ReviewFeed extends StatefulWidget {
  const ReviewFeed(
      {super.key, this.mine = false, this.placeId, this.placeName});
  final bool mine;
  final int? placeId;
  final String? placeName;
  @override
  State<ReviewFeed> createState() => _ReviewFeedState();
}

class _ReviewFeedState extends State<ReviewFeed> {
  final _dataKey = GlobalKey<ActivityDataState>();
  final _busy = <int>{};
  final _expanded = <int>{};
  bool _photosOnly = false;
  String _sort = 'latest';
  String? _loadedPlaceName;
  static const _green = AppColors.primary;
  static const _muted = AppColors.textMuted;

  Future<void> _edit([Map<String, dynamic>? review]) async {
    if (!await ensureSignedIn(context) || !mounted) return;
    await Navigator.push(
        context,
        MaterialPageRoute<bool>(
            builder: (_) => ReviewFormScreen(
                review: review,
                placeId: review?['place_id'] ?? widget.placeId,
                placeName: review?['place_name'] ??
                    widget.placeName ??
                    _loadedPlaceName)));
    if (mounted) await _dataKey.currentState?.refresh();
  }

  Future<void> _act(Map<String, dynamic> review, String action) async {
    if (!await ensureSignedIn(context) || !mounted) return;
    final id = review['id'] as int;
    if (_busy.contains(id)) return;
    if (action == 'delete') {
      final yes = await showDialog<bool>(
          context: context,
          builder: (c) => AlertDialog(
                  title: const Text('후기를 삭제할까요?'),
                  content: const Text('삭제한 후기는 복원할 수 없어요.'),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(c, false),
                        child: const Text('취소')),
                    FilledButton(
                        onPressed: () => Navigator.pop(c, true),
                        child: const Text('삭제'))
                  ]));
      if (yes != true || !mounted) return;
    }
    setState(() => _busy.add(id));
    try {
      if (action == 'delete') {
        await ApiClient.instance.delete('/reviews/$id');
      } else if (review['is_liked'] == true) {
        await ApiClient.instance.delete('/reviews/$id/like');
      } else {
        await ApiClient.instance.post('/reviews/$id/like');
      }
      activityChanged();
      await _dataKey.currentState?.refresh();
    } catch (e) {
      if (mounted) activityError(context, e);
    } finally {
      if (mounted) setState(() => _busy.remove(id));
    }
  }

  bool _hasPhoto(Map<String, dynamic> review) =>
      review['photo_url']?.toString().trim().isNotEmpty == true;
  int _rating(Map<String, dynamic> review) =>
      (review['rating'] as num? ?? 0).toInt();
  DateTime _date(Map<String, dynamic> review) =>
      DateTime.tryParse(review['created_at']?.toString() ?? '') ??
      DateTime(1970);

  Widget _stars(num rating, {double size = 15}) => Semantics(
      label: '별점 $rating점',
      child: Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(
              5,
              (i) => Icon(
                  rating >= i + 1
                      ? Icons.star_rounded
                      : rating > i
                          ? Icons.star_half_rounded
                          : Icons.star_outline_rounded,
                  size: size,
                  color: _green))));

  Widget _summary(List<Map<String, dynamic>> items) {
    final average = items.isEmpty
        ? 0.0
        : items.fold<int>(0, (sum, r) => sum + _rating(r)) / items.length;
    return Padding(
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (widget.placeName != null || _loadedPlaceName != null) ...[
            Text(widget.placeName ?? _loadedPlaceName!,
                style: const TextStyle(fontSize: 14, color: _muted)),
            const SizedBox(height: 8)
          ],
          Text('후기 ${items.length}개',
              style:
                  const TextStyle(fontSize: 21, fontWeight: FontWeight.w700)),
          const SizedBox(height: 22),
          Row(children: [
            Expanded(
                flex: 4,
                child: Column(children: [
                  Text(items.isEmpty ? '—' : average.toStringAsFixed(1),
                      style: const TextStyle(
                          fontSize: 42,
                          fontWeight: FontWeight.w700,
                          height: 1.1)),
                  const SizedBox(height: 6),
                  _stars(average, size: 19),
                  const SizedBox(height: 7),
                  Text(items.isEmpty ? '첫 후기를 기다려요' : '방문자 평균 평점',
                      style: const TextStyle(fontSize: 11, color: _muted))
                ])),
            const SizedBox(width: 28),
            Expanded(
                flex: 6,
                child: Column(
                    children: List.generate(5, (index) {
                  final rating = 5 - index;
                  final count = items.where((r) => _rating(r) == rating).length;
                  return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Row(children: [
                        Text('$rating점',
                            style:
                                const TextStyle(fontSize: 11, color: _muted)),
                        const SizedBox(width: 9),
                        Expanded(
                            child: ClipRRect(
                                borderRadius: BorderRadius.circular(4),
                                child: LinearProgressIndicator(
                                    value: items.isEmpty
                                        ? 0
                                        : count / items.length,
                                    minHeight: 5,
                                    color: _green,
                                    backgroundColor: const Color(0xffedf0eb)))),
                        const SizedBox(width: 9),
                        SizedBox(
                            width: 20,
                            child: Text('$count',
                                textAlign: TextAlign.right,
                                style: const TextStyle(
                                    fontSize: 11, color: _muted)))
                      ]));
                })))
          ]),
          const SizedBox(height: 24),
          SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                  onPressed: _edit,
                  style: FilledButton.styleFrom(
                      backgroundColor: _green,
                      foregroundColor: Colors.white,
                      minimumSize: const Size(0, 46),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14))),
                  icon: const Icon(Icons.edit_outlined, size: 17),
                  label: const Text('후기 작성'))),
        ]));
  }

  Widget _photo(Map<String, dynamic> r) {
    final url = ApiClient.instance.mediaUrl(r['photo_url']);
    Widget picture({BoxFit fit = BoxFit.cover}) => Image.network(url,
        fit: fit,
        errorBuilder: (_, e, s) => const Center(
            child: Icon(Icons.broken_image_outlined, color: _muted)));
    return Padding(
        padding: const EdgeInsets.only(top: 14),
        child: Semantics(
            label: '후기 사진 확대',
            button: true,
            child: InkWell(
                onTap: () => showDialog<void>(
                    context: context,
                    builder: (c) => Dialog(
                            child: Stack(children: [
                          Padding(
                              padding: const EdgeInsets.all(16),
                              child: InteractiveViewer(
                                  minScale: 0.5,
                                  maxScale: 4,
                                  child: picture(fit: BoxFit.contain))),
                          Positioned(
                              top: 0,
                              right: 0,
                              child: IconButton(
                                  tooltip: '사진 닫기',
                                  onPressed: () => Navigator.pop(c),
                                  icon: const Icon(Icons.close)))
                        ]))),
                borderRadius: BorderRadius.circular(12),
                child: ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child:
                        SizedBox(width: 96, height: 96, child: picture())))));
  }

  Widget _review(Map<String, dynamic> r) {
    final id = r['id'] as int;
    final text = r['text']?.toString() ?? '';
    final expanded = _expanded.contains(id);
    final date = activityDate(r['created_at']).split(' ').first;
    return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const CircleAvatar(
                radius: 16,
                backgroundColor: Color(0xffedf2eb),
                child: Icon(Icons.person_outline_rounded,
                    size: 19, color: _green)),
            const SizedBox(width: 10),
            Expanded(
                child: Text(r['author_nickname']?.toString() ?? '방문자',
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600))),
            Text(date, style: const TextStyle(fontSize: 11, color: _muted)),
            if (r['is_mine'] == true)
              PopupMenuButton<String>(
                  tooltip: '후기 관리',
                  onSelected: (v) => v == 'edit' ? _edit(r) : _act(r, v),
                  itemBuilder: (_) => const [
                        PopupMenuItem(value: 'edit', child: Text('수정')),
                        PopupMenuItem(value: 'delete', child: Text('삭제'))
                      ])
          ]),
          const SizedBox(height: 12),
          _stars(_rating(r)),
          if (widget.placeId == null) ...[
            const SizedBox(height: 8),
            Text(r['place_name']?.toString() ?? '',
                style: const TextStyle(fontSize: 12, color: _muted))
          ],
          const SizedBox(height: 10),
          Text(text,
              maxLines: text.length > 160 && !expanded ? 4 : null,
              overflow:
                  text.length > 160 && !expanded ? TextOverflow.ellipsis : null,
              style: const TextStyle(
                  fontSize: 14, height: 1.65, color: Color(0xff303730))),
          if (text.length > 160)
            TextButton(
                onPressed: () => setState(
                    () => expanded ? _expanded.remove(id) : _expanded.add(id)),
                child: Text(expanded ? '접기' : '더보기')),
          if (_hasPhoto(r)) _photo(r),
          const SizedBox(height: 14),
          OutlinedButton.icon(
              onPressed: _busy.contains(id) ? null : () => _act(r, 'like'),
              style: OutlinedButton.styleFrom(
                  foregroundColor: r['is_liked'] == true ? _green : _muted,
                  side: BorderSide(
                      color: r['is_liked'] == true
                          ? _green
                          : const Color(0xffe3e7e1)),
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  minimumSize: const Size(0, 34),
                  visualDensity: VisualDensity.compact,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8))),
              icon: Icon(
                  r['is_liked'] == true
                      ? Icons.thumb_up_alt
                      : Icons.thumb_up_alt_outlined,
                  size: 14),
              label: Text('도움돼요 ${r['like_count'] ?? 0}',
                  style: const TextStyle(fontSize: 11))),
        ]));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      backgroundColor: Colors.white,
      appBar: GreenAppBar(title: widget.mine ? '내 후기 관리' : '여행 후기'),
      body: AppContent(
          child: ActivityData(
              key: _dataKey,
              authenticated: widget.mine,
              load: () => ApiClient.instance.get('/reviews', query: {
                    if (widget.mine) 'mine': 'true',
                    if (widget.placeId != null) 'place_id': '${widget.placeId}'
                  }),
              builder: (context, data, refresh) {
                final items = activityItems(data);
                _loadedPlaceName = widget.placeId != null && items.isNotEmpty
                    ? items.first['place_name'] as String?
                    : null;
                final visible =
                    items.where((r) => !_photosOnly || _hasPhoto(r)).toList();
                visible.sort((a, b) {
                  int comparison = 0;
                  if (_sort == 'helpful') {
                    comparison = (b['like_count'] as num? ?? 0)
                        .compareTo(a['like_count'] as num? ?? 0);
                  }
                  if (_sort == 'rating') {
                    comparison = _rating(b).compareTo(_rating(a));
                  }
                  return comparison != 0
                      ? comparison
                      : _date(b).compareTo(_date(a));
                });
                return ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    children: [
                      if (widget.mine)
                        Padding(
                            padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
                            child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('내가 작성한 후기 ${items.length}개',
                                      style: const TextStyle(
                                          fontSize: 18,
                                          fontWeight: FontWeight.w700)),
                                  const SizedBox(height: 6),
                                  const Text('방문했던 장소의 후기를 확인하고 수정할 수 있어요.',
                                      style: TextStyle(
                                          fontSize: 12, color: _muted)),
                                ]))
                      else
                        _summary(items),
                      const Divider(
                          height: 8, thickness: 8, color: Color(0xfff4f6f4)),
                      Padding(
                          padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
                          child: Row(children: [
                            SizedBox(
                                width: 140,
                                child: Align(
                                    alignment: Alignment.centerLeft,
                                    child: FilterChip(
                                        materialTapTargetSize:
                                            MaterialTapTargetSize.shrinkWrap,
                                        visualDensity: VisualDensity.compact,
                                        padding: const EdgeInsets.symmetric(
                                            horizontal: 8, vertical: 6),
                                        label: Text('사진 후기만',
                                            style: TextStyle(
                                                fontSize: 13,
                                                fontWeight: FontWeight.w500,
                                                color: _photosOnly
                                                    ? Colors.white
                                                    : const Color(0xff424b45))),
                                        checkmarkColor: Colors.white,
                                        selected: _photosOnly,
                                        onSelected: (value) =>
                                            setState(() => _photosOnly = value),
                                        avatar: Icon(Icons.photo_outlined,
                                            size: 16,
                                            color: _photosOnly
                                                ? Colors.white
                                                : _muted),
                                        backgroundColor: Colors.white,
                                        selectedColor: _green,
                                        side: BorderSide(
                                            color: _photosOnly
                                                ? _green
                                                : AppColors.border),
                                        shape: RoundedRectangleBorder(
                                            borderRadius:
                                                BorderRadius.circular(20))))),
                            const Spacer(),
                            DropdownButtonHideUnderline(
                                child: DropdownButton<String>(
                                    isDense: true,
                                    alignment: Alignment.centerRight,
                                    value: _sort,
                                    style: const TextStyle(
                                        fontSize: 13, color: Color(0xff424b45)),
                                    icon: const Icon(Icons.keyboard_arrow_down,
                                        size: 18),
                                    items: const [
                                      DropdownMenuItem(
                                          value: 'latest', child: Text('최신순')),
                                      DropdownMenuItem(
                                          value: 'helpful', child: Text('도움순')),
                                      DropdownMenuItem(
                                          value: 'rating',
                                          child: Text('높은 평점순'))
                                    ],
                                    onChanged: (value) {
                                      if (value != null) {
                                        setState(() => _sort = value);
                                      }
                                    }))
                          ])),
                      if (visible.isEmpty)
                        Padding(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 20, vertical: 40),
                            child: Column(children: [
                              const Icon(Icons.rate_review_outlined,
                                  size: 30, color: _muted),
                              const SizedBox(height: 12),
                              Text(
                                  items.isEmpty
                                      ? (widget.mine
                                          ? '아직 작성한 후기가 없어요.'
                                          : '아직 등록된 후기가 없어요.')
                                      : '사진이 있는 후기가 아직 없어요.',
                                  style: const TextStyle(color: _muted)),
                              const SizedBox(height: 8),
                              if (_photosOnly && items.isNotEmpty)
                                TextButton(
                                    onPressed: () =>
                                        setState(() => _photosOnly = false),
                                    child: const Text('전체 후기 보기'))
                            ])),
                      for (final r in visible) ...[
                        _review(r),
                        const Divider(
                            height: 1,
                            indent: 20,
                            endIndent: 20,
                            color: Color(0xffedf0eb))
                      ],
                      const SizedBox(height: 24),
                    ]);
              })));
}
