import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/api_client.dart';
import '../services/activity_changes.dart';
import '../widgets/activity_place_picker.dart';
import '../widgets/app_chrome.dart';
import '../widgets/activity_data.dart';
import 'auth_screen.dart';

class ReviewFormScreen extends StatefulWidget {
  const ReviewFormScreen(
      {super.key, this.placeId, this.placeName, this.review});
  final int? placeId;
  final String? placeName;
  final Map<String, dynamic>? review;
  @override
  State<ReviewFormScreen> createState() => _ReviewFormScreenState();
}

class _ReviewFormScreenState extends State<ReviewFormScreen> {
  final _text = TextEditingController();
  int? _placeId;
  String? _placeName;
  int _rating = 0;
  Uint8List? _photoBytes;
  String? _validation;
  XFile? _photo;
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    _placeId = widget.placeId ?? widget.review?['place_id'];
    _placeName = widget.placeName ?? widget.review?['place_name'];
    _text.text = widget.review?['text'] ?? '';
    _rating = widget.review?['rating'] ?? 0;
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _selectPlace() async {
    final selected = await selectActivityPlace(context);
    if (selected != null && mounted) {
      setState(() {
        _placeId = selected['id'];
        _placeName = selected['name'];
      });
    }
  }

  Future<void> _submit() async {
    if (_busy) return;
    if (_placeId == null || _rating == 0 || _text.text.trim().isEmpty) {
      setState(() => _validation = _placeId == null
          ? '후기를 남길 장소를 선택해 주세요.'
          : _rating == 0
              ? '별점을 선택해 주세요.'
              : '후기 내용을 입력해 주세요.');
      return;
    }
    setState(() => _validation = null);
    if (!await ensureSignedIn(context) || !mounted) return;
    setState(() => _busy = true);
    try {
      if (widget.review != null && _photo != null) {
        await ApiClient.instance.upload('/reviews/${widget.review!['id']}',
            fields: {'text': _text.text.trim(), 'rating': '$_rating'},
            bytes: await _photo!.readAsBytes(),
            filename: _photo!.name,
            method: 'PATCH');
      } else if (widget.review != null) {
        await ApiClient.instance.patch('/reviews/${widget.review!['id']}',
            body: {'text': _text.text.trim(), 'rating': _rating});
      } else if (_photo != null) {
        await ApiClient.instance.upload('/reviews',
            fields: {
              'place_id': '$_placeId',
              'text': _text.text.trim(),
              'rating': '$_rating'
            },
            bytes: await _photo!.readAsBytes(),
            filename: _photo!.name);
      } else {
        await ApiClient.instance.post('/reviews', body: {
          'place_id': _placeId,
          'text': _text.text.trim(),
          'rating': _rating
        });
      }
      activityChanged();
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) activityError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pickPhoto() async {
    try {
      final photo = await ImagePicker().pickImage(
          source: ImageSource.gallery, maxWidth: 1600, imageQuality: 85);
      if (photo == null) return;
      final bytes = await photo.readAsBytes();
      if (bytes.length > 10 * 1024 * 1024) {
        throw const ApiException('사진은 10MB 이하로 첨부해 주세요.');
      }
      if (mounted) {
        setState(() {
          _photo = photo;
          _photoBytes = bytes;
        });
      }
    } catch (e) {
      if (mounted) activityError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: const Color(0xFFF6F8F6),
        appBar: GreenAppBar(title: widget.review == null ? '후기 작성' : '후기 수정'),
        bottomNavigationBar: SafeArea(
          child: Center(
              heightFactor: 1,
              child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 560),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      if (_validation != null)
                        Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Text(_validation!,
                                style: TextStyle(
                                    color: Theme.of(context).colorScheme.error,
                                    fontSize: 13))),
                      SizedBox(
                          width: double.infinity,
                          child: FilledButton(
                            onPressed: _busy ? null : _submit,
                            child: Text(_busy
                                ? '등록 중…'
                                : widget.review == null
                                    ? '후기 등록'
                                    : '수정 완료'),
                          )),
                    ]),
                  ))),
        ),
        body: AppContent(
            child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
          children: [
            _panel(
                child: InkWell(
              onTap: widget.review == null && widget.placeId == null && !_busy
                  ? _selectPlace
                  : null,
              borderRadius: BorderRadius.circular(18),
              child: Row(children: [
                Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                        color: const Color(0xFFEDF4EE),
                        borderRadius: BorderRadius.circular(12)),
                    child: const Icon(Icons.place_outlined,
                        color: Color(0xFF638A6B))),
                const SizedBox(width: 12),
                Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      const Text('후기를 남길 장소',
                          style: TextStyle(
                              fontSize: 11, color: Color(0xFF849187))),
                      const SizedBox(height: 5),
                      Text(
                          _placeName ?? (_placeId == null ? '장소 선택' : '선택한 장소'),
                          style: const TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w700)),
                    ])),
                if (widget.review == null && widget.placeId == null)
                  const Icon(Icons.chevron_right, color: Color(0xFF849187)),
              ]),
            )),
            const SizedBox(height: 16),
            _panel(
                child: Column(children: [
              const Text('이번 방문은 어떠셨나요?',
                  style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              const Text('별점을 눌러 만족도를 알려주세요',
                  style: TextStyle(fontSize: 12, color: Color(0xFF849187))),
              const SizedBox(height: 14),
              Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                for (var n = 1; n <= 5; n++)
                  IconButton(
                    tooltip: '$n점',
                    onPressed: _busy ? null : () => setState(() => _rating = n),
                    icon: Icon(
                        n <= _rating
                            ? Icons.star_rounded
                            : Icons.star_outline_rounded,
                        size: 36,
                        color: n <= _rating
                            ? const Color(0xFFEAB34C)
                            : const Color(0xFFCDD6CE)),
                  ),
              ]),
              const SizedBox(height: 8),
              Text(
                  [
                    '별점을 선택해 주세요',
                    '많이 아쉬웠어요',
                    '조금 아쉬웠어요',
                    '보통이에요',
                    '좋았어요',
                    '정말 좋았어요'
                  ][_rating],
                  style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF64856B))),
            ])),
            const SizedBox(height: 16),
            _panel(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  const Text('방문 경험을 들려주세요',
                      style:
                          TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  const Text('분위기, 혼잡도, 방문 팁을 남겨주시면 도움이 돼요.',
                      style: TextStyle(
                          fontSize: 12, height: 1.5, color: Color(0xFF849187))),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _text,
                    minLines: 5,
                    maxLines: 12,
                    maxLength: 3000,
                    enabled: !_busy,
                    decoration: const InputDecoration(
                      labelText: '여행 후기',
                      alignLabelWithHint: true,
                      hintText: '직접 방문하며 좋았던 점과 아쉬웠던 점을 자유롭게 적어주세요.',
                      hintMaxLines: 3,
                      fillColor: Color(0xFFFAFBFA),
                    ),
                  ),
                ])),
            const SizedBox(height: 16),
            _panel(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Row(children: [
                    const Expanded(
                        child: Text('사진으로 전하는 순간',
                            style: TextStyle(
                                fontSize: 16, fontWeight: FontWeight.w700))),
                    Text(
                        _photo != null || widget.review?['photo_url'] != null
                            ? '1 / 1'
                            : '0 / 1',
                        style: const TextStyle(
                            fontSize: 12, color: Color(0xFF849187))),
                  ]),
                  const SizedBox(height: 6),
                  const Text('선택 사항 · JPG, PNG, WEBP · 최대 10MB',
                      style: TextStyle(fontSize: 11, color: Color(0xFF849187))),
                  const SizedBox(height: 14),
                  if (_photoBytes != null)
                    ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: Image.memory(_photoBytes!,
                            height: 180,
                            width: double.infinity,
                            fit: BoxFit.cover,
                            errorBuilder: (_, e, s) =>
                                const Text('사진 미리보기를 불러오지 못했어요.')))
                  else if (widget.review?['photo_url'] != null)
                    ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: Image.network(
                            ApiClient.instance
                                .mediaUrl(widget.review!['photo_url']),
                            height: 180,
                            width: double.infinity,
                            fit: BoxFit.cover,
                            errorBuilder: (_, e, s) =>
                                const Text('기존 사진을 불러오지 못했어요.'))),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                      onPressed: _busy ? null : _pickPhoto,
                      icon: const Icon(Icons.add_a_photo_outlined, size: 20),
                      label: Text(
                          _photo != null || widget.review?['photo_url'] != null
                              ? '사진 바꾸기'
                              : '사진 첨부 (선택)')),
                  if (_photo != null)
                    TextButton(
                        onPressed: _busy
                            ? null
                            : () => setState(() {
                                  _photo = null;
                                  _photoBytes = null;
                                }),
                        child: const Text('첨부 취소')),
                ])),
            const SizedBox(height: 16),
            const Text(
                '직접 경험한 내용을 작성해 주세요. 사진만으로 방문 인증이 완료되지는 않으며, 포인트는 실제 적립 내역에서 확인할 수 있어요.',
                style: TextStyle(
                    fontSize: 11, height: 1.6, color: Color(0xFF8C978F))),
          ],
        )),
      );

  Widget _panel({required Widget child}) => Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: const Color(0xFFE5EBE6))),
        child: Material(type: MaterialType.transparency, child: child),
      );
}
