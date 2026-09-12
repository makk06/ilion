# 추천 탭 · 저장 탭 구현 메모 (프런트엔드)

> 담당: 프런트엔드 — 추천 탭 / 저장 탭
> 관련 브랜치: `feature/recommend-category-filter`

## 무엇을 만들었나

| 영역 | 파일 |
| --- | --- |
| 추천 화면 | `lib/src/screens/recommend_screen.dart` |
| 저장 화면 | `lib/src/screens/saved_screen.dart` |
| 장소 상세(공용) | `lib/src/screens/place_detail_screen.dart` |
| 추천 알고리즘 | `lib/src/services/recommendation_engine.dart` |
| 취향 설정 시트 | `lib/src/widgets/preference_sheet.dart` |
| 전역 상태 | `lib/src/state/` (`app_scope`, `preference_store`, `saved_store`, `recommendation_request`) |

상태관리는 외부 패키지 없이 `ChangeNotifier` + `InheritedWidget`(`AppScope`)만 씁니다.
`AppScope`는 `MaterialApp` **바깥**에 있어야 바텀시트·다이얼로그에서도 접근됩니다.

## 다른 탭에서 쓰는 방법 (지도 탭 담당자용)

### 1. 지도에서 장소를 고른 뒤 상세 화면 열기

`PlaceDetailScreen`은 장소명 · 주소 · 거리 · 혼잡도 · 분류 · 실내외 · 날씨를 이미 그립니다.
지도 탭에서 마커를 눌렀을 때 그대로 재사용하면 됩니다.

```dart
Navigator.of(context).push(
  MaterialPageRoute<void>(builder: (_) => PlaceDetailScreen(place: place)),
);
```

### 2. "근처 비슷한 대안"을 추천 탭에서 보여 주기

상세 화면 하단 버튼이 이미 이 동작을 합니다. 지도에서 직접 호출하려면 한 줄이면 됩니다.

```dart
AppScope.read(context).recommendationRequest.requestAlternatives(place);
```

호출하면 하단 탭이 추천 탭으로 자동 전환되고, 추천 탭이 그 장소 기준 **반경 3km 안의
비슷한 대안**만 보여 줍니다. 추천 탭 헤더의 X를 누르면 일반 맞춤 추천으로 돌아옵니다.

### 3. 저장(하트)

`PlaceCard`는 `isSaved`를 넘기지 않으면 저장 상태를 전역에서 읽고, 하트를 누르면
직접 토글합니다. 지도·홈에서도 추가 작업 없이 저장 탭과 동기화됩니다.

```dart
PlaceCard(place: place, onTap: ...)           // 하트 자동 동작
AppScope.read(context).savedStore.toggle(place); // 직접 토글할 때
```

## 추천 알고리즘

취향 5개를 입력으로 받아 항목별 적합도(0~1)에 가중치를 곱해 0~100 점수를 냅니다.
점수와 함께 **추천 이유**를 같이 돌려주고, 카드에 칩으로 노출합니다.

| 항목 | 가중치 | 요약 |
| --- | --- | --- |
| 혼잡도 | 0.32 | 원하는 수준보다 붐비면 크게 감점. 반대로 너무 한산한 경우는 "활기찬 곳 선호" 사용자에게만 소폭 감점 |
| 관심 카테고리 | 0.22 | 선택한 대분류면 만점, 아니면 감점. 아무것도 안 고르면 중립(0.6) |
| 실내/실외 | 0.16 | 선호와 일치하면 만점, 상관없음이면 중립 |
| 거리 | 0.18 | 이동 가능 거리에 가까울수록 감점, 초과하면 목록에서 제외 |
| 날씨 | 0.12 | 비·눈·폭염이면 실내에 가점, 실외에 감점 (마이페이지에서 끌 수 있음) |

대안 추천(`anchor` 지정)일 때는 위 점수 60% + 유사도 40%로 섞습니다.
유사도는 같은 대분류, 공통 태그, 기준 장소와의 거리, "기준 장소보다 한산한 정도"로 계산합니다.

취향은 마이페이지 → 여행 취향 설정, 또는 추천 탭 헤더의 취향 카드에서 **언제든 수정**할 수 있고
바꾸는 즉시 추천 순서에 반영됩니다.

## 백엔드 연동 시 바꿀 곳

- 장소 목록: `lib/src/data/mock_places.dart` → 장소 API 응답. `Place` 필드는 백엔드
  `Place` 모델(주소, 위경도, `indoor_outdoor`, 대분류=TourAPI `contentTypeId`)에 맞춰 뒀습니다.
- 혼잡도: `Place.crowdScore`(0~100) 한 값만 채우면 `CrowdLevel`(여유/보통/혼잡)은 앱에서 계산합니다.
- 추천 점수: 서버 추천 API가 생기면 `RecommendationEngine.recommend`만 교체하면 되고,
  화면은 `Recommendation`(장소 + 점수 + 이유)만 봅니다.
- 취향 저장: 현재는 메모리에만 있습니다. `UserPreference.toJson` / `fromJson`이 준비돼 있으니
  `PreferenceStore`에 서버 호출이나 로컬 저장(`shared_preferences`)을 붙이면 됩니다.
- 저장 목록: `SavedStore`도 같은 이유로 메모리 보관입니다. 앱을 끄면 사라집니다.

## 아직 안 된 것

- 취향·저장 목록 영구 저장 (로그인 또는 로컬 저장소 필요)
- 실제 날씨 API 연동 (지금은 목 데이터의 고정 예보)
- 거리 계산은 목 데이터의 `distanceKm` 사용. 실제 현재 위치 연동은 지도 탭 쪽 위치 권한 작업 후 연결
