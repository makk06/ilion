import 'package:flutter/foundation.dart';

class ActivityChanges extends ChangeNotifier {
  void changed() => notifyListeners();
}

final activityChanges = ActivityChanges();
void activityChanged() => activityChanges.changed();
