import 'package:flutter/material.dart';
import '../models/place.dart';
import '../screens/place_detail_screen.dart';
import '../screens/profile_places_screens.dart';
import '../services/api_client.dart';
import '../services/app_session.dart';
import '../services/place_service.dart';
import 'place_image.dart';

/// A compact, account-aware recent history strip for the profile page.
class ProfileRecentPlaces extends StatefulWidget {
  const ProfileRecentPlaces({super.key});

  @override
  State<ProfileRecentPlaces> createState() => _ProfileRecentPlacesState();
}

class _ProfileRecentPlacesState extends State<ProfileRecentPlaces> {
  late final AppSession _session;
  List<Place> _places = [];
  bool _loading = true;
  bool _failed = false;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _session = AppSession.instance;
    _session.addListener(_load);
    _load();
  }

  @override
  void dispose() {
    _generation++;
    _session.removeListener(_load);
    super.dispose();
  }

  Future<void> _load() async {
    final generation = ++_generation;
    setState(() {
      _loading = true;
      _failed = false;
      _places = [];
    });
    try {
      final ids = await _session.loadRecentPlaces();
      if (!mounted || generation != _generation) return;
      final places = await Future.wait(ids.take(6).map((id) async {
        try {
          return await PlaceService.instance.detail(id);
        } on ApiException catch (error) {
          if (error.statusCode == 404) return null;
          rethrow;
        }
      }));
      if (!mounted || generation != _generation) return;
      setState(() {
        _places = places.whereType<Place>().toList();
        _loading = false;
      });
    } catch (_) {
      if (!mounted || generation != _generation) return;
      setState(() {
        _failed = true;
        _loading = false;
      });
    }
  }

  Future<void> _open(Widget screen) async {
    await Navigator.push(
        context, MaterialPageRoute<void>(builder: (_) => screen));
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) => ColoredBox(
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 20),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Row(children: [
                const Expanded(
                    child: Text('최근 본 장소',
                        style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: Color(0xff242b26)))),
                TextButton(
                    onPressed: () => _open(const RecentPlacesScreen()),
                    style: TextButton.styleFrom(
                        foregroundColor: const Color(0xff858c86),
                        visualDensity: VisualDensity.compact),
                    child: const Row(mainAxisSize: MainAxisSize.min, children: [
                      Text('전체보기', style: TextStyle(fontSize: 12)),
                      Icon(Icons.chevron_right, size: 16)
                    ])),
              ]),
            ),
            const SizedBox(height: 12),
            if (_loading)
              const Padding(
                  padding: EdgeInsets.fromLTRB(20, 8, 20, 24),
                  child: LinearProgressIndicator(
                      minHeight: 2,
                      color: Color(0xff7c9b80),
                      backgroundColor: Color(0xfff0f3ef)))
            else if (_failed)
              Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Row(children: [
                    const Expanded(
                        child: Text('최근 본 장소를 불러오지 못했어요.',
                            style: TextStyle(
                                fontSize: 12, color: Color(0xff858c86)))),
                    TextButton(onPressed: _load, child: const Text('다시 시도'))
                  ]))
            else if (_places.isEmpty)
              const Padding(
                  padding: EdgeInsets.fromLTRB(20, 8, 20, 22),
                  child: Text('관심 있는 장소를 둘러보면 여기에 모아드려요.',
                      style: TextStyle(fontSize: 12, color: Color(0xff858c86))))
            else
              SizedBox(
                  height: 176,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    itemCount: _places.length,
                    separatorBuilder: (_, index) => const SizedBox(width: 12),
                    itemBuilder: (context, index) {
                      final place = _places[index];
                      return SizedBox(
                          width: 112,
                          child: InkWell(
                              borderRadius: BorderRadius.circular(14),
                              onTap: () =>
                                  _open(PlaceDetailScreen(place: place)),
                              child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    PlaceImage(
                                        url: place.imageUrl,
                                        width: 112,
                                        height: 100),
                                    const SizedBox(height: 8),
                                    Text(place.name,
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                            fontSize: 12,
                                            fontWeight: FontWeight.w600,
                                            height: 1.4,
                                            color: Color(0xff242b26))),
                                    const SizedBox(height: 3),
                                    Text(place.category,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                            fontSize: 10,
                                            color: Color(0xff858c86))),
                                  ])));
                    },
                  )),
          ]),
        ),
      );
}
