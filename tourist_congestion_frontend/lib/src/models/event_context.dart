class EventNotice {
  EventNotice.fromJson(Map<String, dynamic> json)
      : name = json['name'] as String? ?? '',
        message = json['message'] as String? ?? '',
        source = json['source'] as String? ?? '',
        sourceUrl = json['source_url'] as String? ?? '',
        timeQuality = json['time_quality'] as String? ?? 'date_only',
        startsAt = DateTime.tryParse(json['starts_at'] as String? ?? ''),
        endsAt = DateTime.tryParse(json['ends_at'] as String? ?? ''),
        receivedAt = DateTime.tryParse(json['received_at'] as String? ?? '');
  final String name, message, source, sourceUrl, timeQuality;
  final DateTime? startsAt, endsAt, receivedAt;
}

class EventContext {
  EventContext.fromJson(Map<String, dynamic> json)
      : validAt = DateTime.tryParse(json['valid_at'] as String? ?? ''),
        checkedAt = DateTime.tryParse(json['checked_at'] as String? ?? ''),
        delayed = json['collection_status'] == 'delayed',
        events = (json['events'] is List ? json['events'] as List : [])
            .whereType<Map>().map((v) => EventNotice.fromJson(Map<String, dynamic>.from(v))).toList();
  final DateTime? validAt, checkedAt;
  final bool delayed;
  final List<EventNotice> events;
  static EventContext? parse(dynamic json) => json is Map
      ? EventContext.fromJson(Map<String, dynamic>.from(json)) : null;
}
