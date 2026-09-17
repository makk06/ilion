# UX Contract

## Product context
한국 여행 서비스, ko-KR, Gregorian dates and local displayed observation timestamps. Mobile-first Flutter web/app. Product register with familiar Korean action labels. Accessibility target WCAG2.2AA; full certification is not claimed.

## Business-context sources
| Domain / scope | Authoritative source | Source type | Reviewed date |
|---|---|---|---|
| Permissions and activity lifecycle | docs/activity-api.md; backend/users/activity_views.py | API contract | 2026-09-12 |
| Guest/account boundaries | frontend/lib/src/services/app_session.dart (under tourist_congestion_frontend) | Implementation evidence of user-approved behavior | 2026-09-12 |
| Tabs / recommendation integration | docs/main-merge-20260912.md plus user request to add Recommendation and Saved bottom tabs | Explicit user decision | 2026-09-12 |
| Points and rewards | docs/activity-api.md /points and /rewards | API contract; no redemption provider | 2026-09-12 |
No billing, retention or legal policy is changed by this visual redesign.

## Visual contract
DESIGN.md mirrors runtime AppColors/AppTheme, then shared Material widgets. Light theme only. Review runtime token changes against the documented palette. Existing detail/form states are not redesigned as part of this primary-tab slice.

## Canonical UI Map
| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | Flutter Material DropdownButton/PopupMenuButton; RegionPicker | Existing Flutter implementation | Authored Material popup; hierarchical region sheet | companion_filters_test, region_picker_test, browser open popup |
| Date | showDatePicker with app ko locale | app.dart / companion screen | Authored Material calendar | companion_filters_test |
| Form | Existing Flutter Form/TextFormField | Screen validators + API | Existing create/edit, unchanged | activity_flow_test |
| Scrollbar | AppTheme.scrollbarTheme + MaterialScrollBehavior | app_theme.dart | Flutter scroll surfaces, platform visibility; no DOM CSS shadow system | narrow/wide browser; no hidden scrollbars |
| Toast | ScaffoldMessenger / activityError | activity_data.dart | success/error | public_login_test, activity_flow_test |
| CRUD | ApiClient, PlaceService, AppSession | API contracts | actual request + owning list refresh | activity_flow_test, guest_places_test |
| Search | AppSearchField | app_chrome.dart | explicit remote submit / immediate local filter | app_search_field_test, widget_test |

## Navigation and state
Six bottom destinations keep IndexedStack state; recommendations/saved load on first visit. Detail routes use Navigator.push/pop and preserve list context. URL query persistence is intentionally deferred for this existing mobile Navigator architecture; no secret, coordinates or private queries are added to URLs. Title remains app-level 이리ON. All pages keep a clear heading. No new deep-link contract is implied.

## Flow ledger
| Operation | Trigger | Pending | Success destination | Success feedback | Failure recovery | Source ref |
|---|---|---|---|---|---|---|
| Search | 검색/Enter | existing list loader | same home | actual result list | inline retry; superseded requests ignored | PlaceService / home_screen |
| Clear search | 검색어 지우기 | clear immediately | same page, input focused | unfiltered query | normal list retry | AppSearchField |
| Save place | 저장 heart | disabled pending | stay | saved state/snackbar | error preserves state | AppSession |
| Public post/reaction | 후기 작성 / 동행 모집 / 도움돼요 | existing login then mutation | existing flow | existing feedback | login page or request error | activity-api.md |
| Points/rewards | 포인트 내역 / 리워드 보기 | API loading | existing screen | actual balance/catalog | retry; never pretend zero on error | activity-api.md |

## Async and recovery
Read requests time out through ApiClient; home generation checks ignore old results. Public personal mutations use existing duplicate guards and server validation. Guest favorites/recent/plans remain local; login does not silently merge them. Search clearing restores focus. No optimistic monetary operations. Existing Material modal behavior owns Escape and focus; no custom overlays are introduced.

## Verification
Run Flutter format, analyze, full tests and web build. Runtime browser check primary navigation, selected state, recommendation/saved empty/data states, open filter popup and narrow layout. Existing tests cover API failures, empty lists, login guards and persistence; new shared search test covers clear/focus. Static premium audit is supplemental and does not prove Flutter semantics or browser behavior. Native-device and complete screen-reader certification remain outside this desktop verification.

## Crowd estimation contract (2026-09-12)

Authoritative scope: approved nationwide crowd implementation plan; docs/crowd-estimation.md and backend/API.md. `Place` owns the observation/estimate compatibility choice, `EstimatedCrowdLevel` owns five labels, `AppColors.estimate*` owns colors, `CrowdBadge` owns wrapping and `CrowdEvidence` owns detailed evidence/forecast display. All cards, map markers, saved places and recommendations use these owners.

Always label estimates as 예상, Tier C as 낮은 신뢰도, cached/stale inputs as 오래된 정보 and samples as 개발 샘플. Area population never becomes facility visitor counts. Source-specific timestamps come from the API; local cache expiry is separate. Closed places never gain a quietness recommendation bonus. Keep existing four-level observations distinguishable as 서울시 제공 when the new field is absent. Tests: crowd_estimate_test.dart and backend places/test_crowd_api.py. Narrow 320px cards must wrap badge text without hiding quality warnings.

Mean forecast API contract: `scope=area_population` adds an explicit area-relative disclaimer in CrowdEvidence; `confidence_status=not_calibrated` displays 근거 품질 미평가. Null forecasts retain 정보 부족. Only backend gate-approved deployments enter this variant. See docs/mean-crowd.md.
# 방문 판단 계약 (2026-09-13)

공통 원천은 `CrowdForecast`와 `relative-choice-v2` API다. 시각 선택은 `PersonalizedRecommendationsScreen`, 추천 입력은 `RecommendationEngine`, 공통 절대 한국 시각은 `forecastTimeLabel`, 단계 표시는 `ForecastEvidence`와 `RecommendationCard`가 담당한다. 선택 만료 시 현재로 자동 전환하지 않는다. 앱 복귀와 주기 갱신에서 제공 시각을 재검사한다. 현재 경로는 유지하고 미래는 정확히 일치하는 검증된 입력만 사용한다. `hourly_decision_test`와 `decision_screen_test`가 경계·결측·그룹 분리·만료 상태를 검증한다.

2026-09-15: 표시와 판단 검증은 같은 대상의 발행 당시 과거 분포를 사용한다. '매우 붐빔'은 85백분위 초과이며, 놓침은 실제 >85·예측 ≤85다. 고정 인구 임계값으로 새 단계 안내를 판정하지 않는다. v1 검증 결과로 v2 기능을 활성화하지 않는다.
