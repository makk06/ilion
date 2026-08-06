import 'package:flutter/material.dart';

import '../data/mock_places.dart';
import '../theme/app_theme.dart';
import '../widgets/crowd_badge.dart';
import '../widgets/place_card.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: CustomScrollView(
        slivers: [
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 12),
            sliver: SliverList.list(
              children: [
                const _HomeHeader(),
                const SizedBox(height: 20),
                _SearchBar(onTap: () {}),
                const SizedBox(height: 16),
                const _MapPreview(),
                const SizedBox(height: 24),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('지금 가기 좋은 곳', style: Theme.of(context).textTheme.titleMedium),
                    TextButton(onPressed: () {}, child: const Text('전체 보기')),
                  ],
                ),
                Text(
                  '현재 위치와 혼잡도를 바탕으로 골랐어요',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AppColors.textMuted,
                      ),
                ),
                const SizedBox(height: 12),
              ],
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
            sliver: SliverList.separated(
              itemCount: mockPlaces.length,
              itemBuilder: (context, index) => PlaceCard(place: mockPlaces[index]),
              separatorBuilder: (_, __) => const SizedBox(height: 12),
            ),
          ),
        ],
      ),
    );
  }
}

class _HomeHeader extends StatelessWidget {
  const _HomeHeader();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.location_on_rounded, size: 18, color: AppColors.primary),
                  SizedBox(width: 4),
                  Text('서울특별시 성동구', style: TextStyle(fontWeight: FontWeight.w600)),
                  Icon(Icons.keyboard_arrow_down_rounded, size: 18),
                ],
              ),
              const SizedBox(height: 8),
              Text('어디로 떠나볼까요?', style: Theme.of(context).textTheme.headlineSmall),
            ],
          ),
        ),
        IconButton.filledTonal(
          onPressed: () {},
          icon: const Icon(Icons.notifications_none_rounded),
        ),
      ],
    );
  }
}

class _SearchBar extends StatelessWidget {
  const _SearchBar({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 16, vertical: 15),
          child: Row(
            children: [
              Icon(Icons.search_rounded, color: AppColors.textMuted),
              SizedBox(width: 10),
              Text('장소나 지역을 검색해 보세요', style: TextStyle(color: AppColors.textMuted)),
              Spacer(),
              Icon(Icons.tune_rounded, color: AppColors.primary),
            ],
          ),
        ),
      ),
    );
  }
}

class _MapPreview extends StatelessWidget {
  const _MapPreview();

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 4 / 3,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: ColoredBox(
          color: const Color(0xFFE8EEE8),
          child: Stack(
            children: [
              CustomPaint(size: Size.infinite, painter: _MapPainter()),
              const Positioned(top: 26, left: 44, child: _MapPin(label: '여유', color: AppColors.low)),
              const Positioned(top: 90, right: 42, child: _MapPin(label: '보통', color: AppColors.medium)),
              const Positioned(bottom: 42, left: 118, child: _MapPin(label: '혼잡', color: AppColors.high)),
              Positioned(
                right: 14,
                bottom: 14,
                child: FloatingActionButton.small(
                  heroTag: 'current-location',
                  onPressed: () {},
                  backgroundColor: Colors.white,
                  child: const Icon(Icons.my_location_rounded, color: AppColors.primary),
                ),
              ),
              const Positioned(
                left: 14,
                bottom: 14,
                child: Card(
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        CrowdBadge.compact(label: '여유', color: AppColors.low),
                        SizedBox(width: 5),
                        CrowdBadge.compact(label: '보통', color: AppColors.medium),
                        SizedBox(width: 5),
                        CrowdBadge.compact(label: '혼잡', color: AppColors.high),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MapPin extends StatelessWidget {
  const _MapPin({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(20),
        boxShadow: const [BoxShadow(color: Color(0x26000000), blurRadius: 8, offset: Offset(0, 3))],
      ),
      child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700)),
    );
  }
}

class _MapPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final road = Paint()
      ..color = Colors.white.withValues(alpha: 0.85)
      ..strokeWidth = 14
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    final river = Paint()
      ..color = const Color(0xFFB9DDF5)
      ..strokeWidth = 28
      ..style = PaintingStyle.stroke;

    canvas.drawLine(Offset(-20, size.height * .72), Offset(size.width + 30, size.height * .43), river);
    canvas.drawLine(Offset(size.width * .12, -10), Offset(size.width * .38, size.height + 10), road);
    canvas.drawLine(Offset(-10, size.height * .32), Offset(size.width + 10, size.height * .68), road);
    canvas.drawLine(Offset(size.width * .73, -10), Offset(size.width * .58, size.height + 10), road);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
