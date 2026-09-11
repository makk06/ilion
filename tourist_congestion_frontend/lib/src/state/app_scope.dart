import 'package:flutter/material.dart';

import 'preference_store.dart';
import 'recommendation_request.dart';
import 'saved_store.dart';

/// 앱 전역 상태 묶음.
class AppState {
  AppState()
      : preferenceStore = PreferenceStore(),
        savedStore = SavedStore(),
        recommendationRequest = RecommendationRequest();

  /// 사용자 취향(추천 알고리즘 입력). 마이페이지에서 계속 수정할 수 있다.
  final PreferenceStore preferenceStore;

  /// 저장한 장소.
  final SavedStore savedStore;

  /// 지도 탭 → 추천 탭 대안 추천 요청.
  final RecommendationRequest recommendationRequest;

  late final Listenable listenable = Listenable.merge([
    preferenceStore,
    savedStore,
    recommendationRequest,
  ]);

  void dispose() {
    preferenceStore.dispose();
    savedStore.dispose();
    recommendationRequest.dispose();
  }
}

/// 앱 전역 상태를 하위 화면에 내려 주는 위젯.
/// 외부 상태관리 패키지 없이 `ChangeNotifier` + `InheritedWidget` 만 쓴다.
///
/// - 값을 읽고 화면도 같이 갱신: `AppScope.watch(context).savedStore`
/// - 콜백 안에서 읽기만: `AppScope.read(context).savedStore.toggle(place)`
///
/// `MaterialApp` 바깥에 두어야 바텀시트·다이얼로그에서도 접근할 수 있다.
class AppScope extends StatefulWidget {
  const AppScope({super.key, required this.child});

  final Widget child;

  static AppState watch(BuildContext context) {
    final inherited =
        context.dependOnInheritedWidgetOfExactType<_AppScopeInherited>();
    assert(inherited != null, 'AppScope 가 위젯 트리에 없습니다.');
    return inherited!.state;
  }

  static AppState read(BuildContext context) {
    final inherited =
        context.getInheritedWidgetOfExactType<_AppScopeInherited>();
    assert(inherited != null, 'AppScope 가 위젯 트리에 없습니다.');
    return inherited!.state;
  }

  @override
  State<AppScope> createState() => _AppScopeState();
}

class _AppScopeState extends State<AppScope> {
  final AppState _state = AppState();

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _state.listenable,
      builder: (context, child) => _AppScopeInherited(
        state: _state,
        version: Object(),
        child: child!,
      ),
      child: widget.child,
    );
  }
}

class _AppScopeInherited extends InheritedWidget {
  const _AppScopeInherited({
    required this.state,
    required this.version,
    required super.child,
  });

  final AppState state;

  /// 알림이 올 때마다 새 객체로 바뀌어 의존 위젯을 다시 빌드시킨다.
  final Object version;

  @override
  bool updateShouldNotify(_AppScopeInherited oldWidget) =>
      version != oldWidget.version;
}
