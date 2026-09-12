import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';

class PointsScreen extends StatelessWidget {
  const PointsScreen({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: const GreenAppBar(title: '포인트'),
      body: AppContent(
          child: ActivityData(
              authenticated: true,
              load: () => ApiClient.instance.get('/points'),
              builder: (context, data, refresh) => ListView(
                      padding: const EdgeInsets.all(20),
                      physics: const AlwaysScrollableScrollPhysics(),
                      children: [
                        Container(
                          padding: const EdgeInsets.all(24),
                          decoration: BoxDecoration(
                              color: const Color(0xFF2D4435),
                              borderRadius: BorderRadius.circular(22)),
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Row(children: [
                                  Icon(Icons.toll_rounded,
                                      color: Color(0xFFCDE2BB), size: 20),
                                  SizedBox(width: 8),
                                  Text('보유 포인트',
                                      style: TextStyle(
                                          fontSize: 13,
                                          color: Color(0xFFDDE7DD))),
                                ]),
                                const SizedBox(height: 14),
                                Text('${data['balance']} P',
                                    style: const TextStyle(
                                        fontSize: 34,
                                        fontWeight: FontWeight.w700,
                                        color: Colors.white)),
                              ]),
                        ),
                        const SizedBox(height: 12),
                        OutlinedButton(
                            style: OutlinedButton.styleFrom(
                                backgroundColor: Colors.white,
                                padding: const EdgeInsets.all(18),
                                side:
                                    const BorderSide(color: Color(0xFFE1E9E2)),
                                shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(16))),
                            onPressed: () => Navigator.push(
                                context,
                                MaterialPageRoute<void>(
                                    builder: (_) => const RewardsScreen())),
                            child: const Row(children: [
                              Icon(Icons.card_giftcard_outlined, size: 22),
                              SizedBox(width: 12),
                              Expanded(
                                  child: Text('포인트 리워드 둘러보기',
                                      style: TextStyle(
                                          fontSize: 14,
                                          fontWeight: FontWeight.w600))),
                              Icon(Icons.chevron_right, size: 20),
                            ])),
                        const SizedBox(height: 28),
                        Row(children: [
                          const Expanded(
                              child: Text('포인트 내역',
                                  style: TextStyle(
                                      fontSize: 17,
                                      fontWeight: FontWeight.w700))),
                          IconButton(
                              tooltip: '포인트 내역 새로고침',
                              onPressed: refresh,
                              icon: const Icon(Icons.refresh_rounded,
                                  size: 20, color: Color(0xFF728578))),
                        ]),
                        const SizedBox(height: 12),
                        Container(
                          decoration: BoxDecoration(
                              color: Colors.white,
                              border:
                                  Border.all(color: const Color(0xFFE1E9E2)),
                              borderRadius: BorderRadius.circular(20)),
                          child: activityItems(data).isEmpty
                              ? const Padding(
                                  padding: EdgeInsets.symmetric(
                                      horizontal: 24, vertical: 40),
                                  child: Center(
                                      child: Column(children: [
                                    CircleAvatar(
                                        radius: 26,
                                        backgroundColor: Color(0xFFF0F4EF),
                                        child: Icon(Icons.receipt_long_outlined,
                                            color: Color(0xFF8CA08D),
                                            size: 26)),
                                    SizedBox(height: 16),
                                    Text('아직 포인트 내역이 없어요',
                                        style: TextStyle(
                                            fontSize: 14,
                                            fontWeight: FontWeight.w600)),
                                    SizedBox(height: 6),
                                    Text('포인트가 적립되거나 사용되면 여기에 표시돼요.',
                                        textAlign: TextAlign.center,
                                        style: TextStyle(
                                            fontSize: 12,
                                            height: 1.5,
                                            color: Color(0xFF87948B))),
                                  ])))
                              : Column(children: [
                                  for (final r in activityItems(data))
                                    ListTile(
                                        contentPadding:
                                            const EdgeInsets.symmetric(
                                                horizontal: 20, vertical: 8),
                                        title: Text(r['reason'] ?? '',
                                            style: const TextStyle(
                                                fontSize: 14,
                                                fontWeight: FontWeight.w600)),
                                        subtitle: Text(
                                            activityDate(r['created_at']),
                                            style: const TextStyle(
                                                fontSize: 11,
                                                color: Color(0xFF87948B))),
                                        trailing: Text(
                                            '${(r['amount'] as num) > 0 ? '+' : ''}${r['amount']} P',
                                            style: TextStyle(
                                                fontSize: 15,
                                                fontWeight: FontWeight.w700,
                                                color: (r['amount'] as num) > 0
                                                    ? const Color(0xFF56806A)
                                                    : const Color(
                                                        0xFF617066)))),
                                ]),
                        )
                      ]))));
}

class RewardsScreen extends StatelessWidget {
  const RewardsScreen({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: const GreenAppBar(title: '포인트 리워드'),
        body: AppContent(
            child: ActivityData(
          load: () => ApiClient.instance.get('/rewards'),
          builder: (context, rewards, refresh) => ListView(
            padding: const EdgeInsets.all(20),
            children: [Text(rewards['message'] ?? '현재 교환 가능한 리워드가 없어요.')],
          ),
        )),
      );
}
