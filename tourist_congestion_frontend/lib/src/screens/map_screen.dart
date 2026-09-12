import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../widgets/place_map.dart';
import '../models/place.dart';
import '../services/place_location.dart';
import '../widgets/app_chrome.dart';
import '../widgets/place_card.dart';
import 'place_detail_screen.dart';

class MapScreen extends StatefulWidget {
  const MapScreen({super.key, required this.places, this.selectedId});
  final List<Place> places;
  final int? selectedId;
  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final _controller = MapController();
  Place? _selected;
  LatLng? _location;
  bool _list = false, _locating = false;
  bool _canPop = false;
  LatLng? _focus;

  void _close() {
    if (_canPop) return;
    setState(() => _canPop = true);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) Navigator.of(context).pop(_selected?.id);
    });
  }

  @override
  void initState() {
    super.initState();
    final candidates = widget.places.where((e) => e.id == widget.selectedId);
    _selected =
        candidates.isNotEmpty ? candidates.first : widget.places.firstOrNull;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _locate() async {
    setState(() => _locating = true);
    try {
      final p = await locateUser();
      if (!mounted) return;
      final wasList = _list;
      setState(() {
        _location = LatLng(p.latitude, p.longitude);
        _focus = _location;
        _list = false;
      });
      if (!wasList) _controller.move(_location!, 13);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    } finally {
      if (mounted) setState(() => _locating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final geo = widget.places.where((e) => e.hasCoordinates).toList();
    final center = _focus ??
        (_selected?.hasCoordinates == true
            ? LatLng(_selected!.latitude!, _selected!.longitude!)
            : geo.isEmpty
                ? const LatLng(36.5, 127.8)
                : LatLng(geo.first.latitude!, geo.first.longitude!));
    return PopScope(
        canPop: _canPop,
        onPopInvokedWithResult: (didPop, result) {
          if (!didPop) _close();
        },
        child: Scaffold(
            appBar: GreenAppBar(
                title: '지도 탐색',
                leading: BackButton(onPressed: _close),
                actions: [
                  IconButton(
                      tooltip: '현재 위치',
                      onPressed: _locating ? null : _locate,
                      icon: const Icon(Icons.my_location))
                ]),
            body: AppContent(
                child: Column(children: [
              Padding(
                  padding: const EdgeInsets.all(12),
                  child: SegmentedButton<bool>(
                      segments: const [
                        ButtonSegment(value: false, label: Text('지도')),
                        ButtonSegment(value: true, label: Text('리스트'))
                      ],
                      selected: {
                        _list
                      },
                      onSelectionChanged: (v) =>
                          setState(() => _list = v.first))),
              Expanded(
                  child: _list
                      ? ListView(children: [
                          for (final p in widget.places)
                            PlaceCard(
                                place: p,
                                onTap: () {
                                  setState(() {
                                    _selected = p;
                                    _focus = null;
                                    _list = false;
                                  });
                                })
                        ])
                      : PlacesMap(
                          controller: _controller,
                          places: widget.places,
                          selectedId: _selected?.id,
                          focus: center,
                          location: _location,
                          onSelected: (p) => setState(() {
                            _selected = p;
                            _focus = null;
                          }),
                        )),
              if (geo.isEmpty)
                const Padding(
                    padding: EdgeInsets.all(8),
                    child: Text('표시할 장소 좌표가 없습니다.')),
              if (_selected != null)
                Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      PlaceCard(
                          place: _selected!,
                          onTap: () => Navigator.push(
                              context,
                              MaterialPageRoute<void>(
                                  builder: (_) =>
                                      PlaceDetailScreen(place: _selected!)))),
                      FilledButton(
                          onPressed: _selected!.hasCoordinates
                              ? () => openPlaceDirections(context, _selected!)
                              : null,
                          child: const Text('카카오맵 길찾기'))
                    ]))
            ]))));
  }
}
