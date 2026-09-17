import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/event_context.dart';

class EventNoticeView extends StatelessWidget {
  const EventNoticeView({super.key, this.contextData});
  final EventContext? contextData;
  @override
  Widget build(BuildContext context) {
    final data = contextData;
    if (data == null) return const SizedBox.shrink();
    String time(DateTime at) => DateFormat('M/d HH:mm').format(at.toUtc().add(const Duration(hours: 9)));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final event in data.events) ...[
        Text(event.name, style: const TextStyle(fontWeight: FontWeight.w600)),
        Text(event.message, style: const TextStyle(fontSize: 12)),
        if (event.startsAt != null && event.endsAt != null)
          Text('${time(event.startsAt!)} ~ ${time(event.endsAt!)} (한국시간)', style: const TextStyle(fontSize: 12)),
        if (event.receivedAt != null)
          Text('확인 ${time(event.receivedAt!)}', style: const TextStyle(fontSize: 12)),
        if (Uri.tryParse(event.sourceUrl) case final Uri uri when uri.scheme == 'https' || uri.scheme == 'http')
          TextButton(onPressed: () async { await launchUrl(uri, mode: LaunchMode.externalApplication); },
              child: const Text('행사 출처 확인'))
        else Text(event.source == 'tour_api' ? '출처: 한국관광공사 TourAPI' : '출처 확인 정보', style: const TextStyle(fontSize: 12)),
      ],
      if (data.delayed) const Text('행사 최신 정보 확인 지연 · 일정이 변경됐을 수 있어요.', style: TextStyle(fontSize: 12)),
    ]);
  }
}
