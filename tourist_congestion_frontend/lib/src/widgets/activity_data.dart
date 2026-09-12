import '../services/activity_changes.dart';
import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../services/app_session.dart';
import '../screens/auth_screen.dart';

String activityDate(dynamic value) {
  final date = DateTime.tryParse(value?.toString() ?? '')?.toLocal();
  if (date == null) return '';
  String pad(int n) => n.toString().padLeft(2, '0');
  return '${date.year}.${pad(date.month)}.${pad(date.day)} ${pad(date.hour)}:${pad(date.minute)}';
}

List<Map<String, dynamic>> activityItems(dynamic value) =>
    ((value is Map ? value['items'] : value) as List? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
void activityError(BuildContext context, Object error) =>
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(error is ApiException
            ? error.message
            : '요청을 처리하지 못했어요. 다시 시도해 주세요.')));

class ActivityData extends StatefulWidget {
  const ActivityData(
      {super.key,
      required this.load,
      required this.builder,
      this.authenticated = false});
  final Future<dynamic> Function() load;
  final Widget Function(BuildContext, dynamic, Future<void> Function()) builder;
  final bool authenticated;
  @override
  State<ActivityData> createState() => ActivityDataState();
}

class ActivityDataState extends State<ActivityData> {
  dynamic _data;
  Object? _error;
  bool _loading = true;
  int _generation = 0;
  @override
  void initState() {
    super.initState();
    AppSession.instance.addListener(_session);
    activityChanges.addListener(_session);
    refresh();
  }

  @override
  void dispose() {
    AppSession.instance.removeListener(_session);
    activityChanges.removeListener(_session);
    super.dispose();
  }

  void _session() {
    refresh();
  }

  @override
  void didUpdateWidget(covariant ActivityData oldWidget) {
    super.didUpdateWidget(oldWidget);
  }

  Future<void> refresh() async {
    final generation = ++_generation;
    if (widget.authenticated && !AppSession.instance.isAuthenticated) {
      if (mounted) {
        setState(() {
          _data = null;
          _loading = false;
          _error = null;
        });
      }
      return;
    }
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final value = await widget.load();
      if (mounted && generation == _generation) {
        setState(() {
          _data = value;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() {
          _error = e;
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.authenticated && !AppSession.instance.isAuthenticated) {
      return Center(
          child: FilledButton(
              onPressed: () async {
                if (await ensureSignedIn(context)) await refresh();
              },
              child: const Text('로그인하고 확인하기')));
    }
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
          child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(_error is ApiException
                    ? (_error as ApiException).message
                    : '데이터를 불러오지 못했어요.'),
                const SizedBox(height: 12),
                OutlinedButton(onPressed: refresh, child: const Text('다시 시도'))
              ])));
    }
    return RefreshIndicator(
        onRefresh: refresh, child: widget.builder(context, _data, refresh));
  }
}
