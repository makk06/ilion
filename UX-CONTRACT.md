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
