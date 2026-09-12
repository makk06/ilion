import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../widgets/activity_data.dart';
import '../widgets/app_chrome.dart';

class NotificationsScreen extends StatelessWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: const GreenAppBar(title: '내 활동 알림'),
        body: AppContent(
            child: ActivityData(
          authenticated: true,
          load: () => ApiClient.instance.get('/notifications'),
          builder: (context, data, refresh) {
            final items = activityItems(data);
            return ListView(
              padding: const EdgeInsets.all(20),
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                const Text('최근 계정 활동을 확인하세요. 아래로 당기면 새로고침됩니다.'),
                const SizedBox(height: 16),
                if (items.isEmpty) const Text('아직 새 활동이 없어요.'),
                for (final item in items)
                  Card(
                      child: ListTile(
                    leading: const Icon(Icons.notifications_outlined),
                    title: Text(item['title'] as String? ?? '활동 알림'),
                    subtitle: Text(
                        '${item['body'] ?? ''}\n${activityDate(item['created_at'])}'),
                    isThreeLine: true,
                  )),
                TextButton.icon(
                    onPressed: refresh,
                    icon: const Icon(Icons.refresh),
                    label: const Text('새로고침')),
              ],
            );
          },
        )),
      );
}
