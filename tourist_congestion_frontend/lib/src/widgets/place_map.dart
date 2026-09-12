import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import '../services/api_client.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/place.dart';

/// Shared interactive map for home and nearby-place exploration.
class PlacesMap extends StatefulWidget {
  const PlacesMap(
      {super.key,
      required this.places,
      required this.onSelected,
      this.selectedId,
      this.controller,
      this.focus,
      this.location});
  final List<Place> places;
  final ValueChanged<Place> onSelected;
  final int? selectedId;
  final MapController? controller;
  final LatLng? focus, location;

  @override
  State<PlacesMap> createState() => _PlacesMapState();
}

class _PlacesMapState extends State<PlacesMap>
    with SingleTickerProviderStateMixin {
  late final MapController _controller = widget.controller ?? MapController();
  late final AnimationController _zoomAnimation;

  @override
  void initState() {
    super.initState();
    _zoomAnimation = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 220));
  }

  double? _targetZoom;
  bool _tileError = false;
  int _revision = 0;
  void _reloadTiles() => setState(() {
        _tileError = false;
        _revision++;
      });

  LatLng get _center {
    if (widget.focus != null) return widget.focus!;
    final geo = widget.places.where((p) => p.hasCoordinates);
    final place = geo.where((p) => p.id == widget.selectedId).firstOrNull ??
        geo.firstOrNull;
    return place == null
        ? const LatLng(36.5, 127.8)
        : LatLng(place.latitude!, place.longitude!);
  }

  @override
  void didUpdateWidget(covariant PlacesMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    // API searches may replace the places after the map has already mounted.
    if (oldWidget.focus != widget.focus ||
        oldWidget.selectedId != widget.selectedId) {
      _zoomAnimation.stop();
      _targetZoom = null;
      _controller.move(_center, _controller.camera.zoom);
    }
  }

  @override
  void dispose() {
    _zoomAnimation.dispose();
    if (widget.controller == null) _controller.dispose();
    super.dispose();
  }

  void _zoom(double delta) {
    final camera = _controller.camera;
    final start = camera.zoom;
    final target = ((_zoomAnimation.isAnimating ? _targetZoom : start)! + delta)
        .clamp(3.0, 18.0);
    _zoomAnimation.stop();
    _targetZoom = target;
    _zoomAnimation.removeListener(_animateZoom);
    _zoomStart = start;
    _zoomCenter = camera.center;
    _zoomAnimation.addListener(_animateZoom);
    _zoomAnimation.forward(from: 0);
  }

  double _zoomStart = 13;
  LatLng? _zoomCenter;
  void _animateZoom() {
    final progress = Curves.easeOutCubic.transform(_zoomAnimation.value);
    _controller.move(
        _zoomCenter!, _zoomStart + (_targetZoom! - _zoomStart) * progress);
  }

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Stack(children: [
          FlutterMap(
            mapController: _controller,
            options: MapOptions(
              initialCenter: _center,
              initialZoom: widget.places.any((p) => p.hasCoordinates) ? 13 : 7,
              minZoom: 3,
              maxZoom: 18,
              onPositionChanged: (_, hasGesture) {
                if (hasGesture) {
                  _zoomAnimation.stop();
                  _targetZoom = null;
                }
              },
              interactionOptions: InteractionOptions(
                flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
                cursorKeyboardRotationOptions:
                    CursorKeyboardRotationOptions.disabled(),
              ),
            ),
            children: [
              TileLayer(
                key: ValueKey(_revision),
                urlTemplate:
                    '${ApiClient.instance.baseUrl}/maps/vworld/{z}/{x}/{y}.png',
                // Render 256px source tiles at 128 logical pixels. Source zoom 19
                // is the final supported level, so camera zoom stops at 18.
                retinaMode: true,
                maxNativeZoom: 19,
                maxZoom: 19,
                errorTileCallback: (_, error, stackTrace) {
                  if (mounted && !_tileError) {
                    WidgetsBinding.instance.addPostFrameCallback((_) {
                      if (mounted) setState(() => _tileError = true);
                    });
                  }
                },
              ),
              MarkerLayer(markers: [
                for (final p in widget.places.where((p) => p.hasCoordinates))
                  Marker(
                    point: LatLng(p.latitude!, p.longitude!),
                    width: 48,
                    height: 48,
                    child: IconButton(
                      tooltip: '${p.name} · ${p.crowdText}',
                      onPressed: () => widget.onSelected(p),
                      icon: Icon(Icons.location_on,
                          size: p.id == widget.selectedId ? 38 : 26,
                          color: p.id == widget.selectedId
                              ? Theme.of(context).colorScheme.primary
                              : const Color(0xFF6D8C80)),
                    ),
                  ),
                if (widget.location != null)
                  Marker(
                      point: widget.location!,
                      child: const Icon(Icons.my_location, color: Colors.blue)),
              ]),
              Align(
                alignment: Alignment.bottomRight,
                child: ColoredBox(
                  color: const Color(0xDDF7F5EE),
                  child: Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 5, vertical: 3),
                    child: Wrap(alignment: WrapAlignment.end, children: [
                      for (final source in const [
                        ('© 공간정보 오픈플랫폼 브이월드', 'https://www.vworld.kr/'),
                      ])
                        InkWell(
                          onTap: () => launchUrl(Uri.parse(source.$2)),
                          child: Text(source.$1,
                              style: const TextStyle(
                                  fontSize: 10, color: Color(0xFF6F756F))),
                        ),
                    ]),
                  ),
                ),
              ),
            ],
          ),
          Positioned(
              top: 12,
              right: 12,
              child: Material(
                color: Colors.white,
                elevation: 2,
                borderRadius: BorderRadius.circular(12),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  IconButton(
                      tooltip: '지도 확대',
                      onPressed: () => _zoom(1),
                      icon: const Icon(Icons.add)),
                  IconButton(
                      tooltip: '지도 축소',
                      onPressed: () => _zoom(-1),
                      icon: const Icon(Icons.remove)),
                ]),
              )),
          if (_tileError)
            Positioned(
                left: 8,
                bottom: 28,
                right: 64,
                child: Material(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(8),
                  child: TextButton.icon(
                    onPressed: _reloadTiles,
                    icon: const Icon(Icons.refresh, size: 18),
                    label: const Text('지도 배경 다시 불러오기'),
                  ),
                )),
        ]),
      );
}
