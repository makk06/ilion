import 'package:flutter/foundation.dart';

import '../models/place.dart';
import '../services/app_session.dart';

/// Shared saved-state adapter: account and guest persistence belong to AppSession.
class SavedStore extends ChangeNotifier {
  SavedStore({AppSession? session})
      : _session = session ?? AppSession.instance {
    _session.addListener(notifyListeners);
  }

  final AppSession _session;
  final Set<int> _pending = {};

  int get count => _session.favoriteIds.length;
  bool isSaved(int placeId) => _session.favoriteIds.contains(placeId);
  bool isPending(int placeId) => _pending.contains(placeId);

  Future<bool> toggle(Place place) async {
    if (!_pending.add(place.id)) return isSaved(place.id);
    notifyListeners();
    try {
      await _session.toggleFavorite(place.id);
      return isSaved(place.id);
    } finally {
      _pending.remove(place.id);
      if (!_disposed) notifyListeners();
    }
  }

  bool _disposed = false;
  @override
  void dispose() {
    _disposed = true;
    _session.removeListener(notifyListeners);
    super.dispose();
  }
}
