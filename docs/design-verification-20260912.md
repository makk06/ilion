# Primary-tab redesign verification — 2026-09-12

Scope: original forest/sage identity and six bottom destinations retained. Shared colors, typography, search, card layouts and navigation selection were refined. No API contracts, permissions, points rules or map data sources changed.

Runtime owner: `tourist_congestion_frontend/lib/src/theme/app_theme.dart`; documented by DESIGN.md. Flutter widgets own scrolling, popups, focus and semantics, not a parallel HTML/CSS component system.

Checks:
- Flutter analyze: no issues.
- Flutter full suite: 76 passed after bottom-bar sizing correction.
- Web build: passed; final header alignment also passed 8 focused tests and a fresh web build.
- DESIGN.md official lint: 0 errors, 4 orphaned-color warnings (tokens are consumed by Dart, not frontmatter component recipes).
- Premium strict project audit: 0 findings, source roots limited to the product frontend (excludes third-party Python environment).
- Browser: actual home data/map, recommendation cards, guest saved empty state, points card, six-tab selection and open/close RegionPicker. Popup close restored focus to the trigger.
- Narrow 390px widget tests cover navigation, recommendation cards, companion filters and profile.
- Shared search test verifies immediate clearing and input focus restoration. Existing tests cover API errors, no-results, guest/auth state and actual list-detail transitions.

Limitations: static premium audit does not understand all Flutter render semantics. This is not a WCAG certification. Native mobile devices, full screen-reader matrix and physical Korean IME were not exercised. No new remote assets or dependencies were added.

Place detail section navigation: preserved hero; pinned 52px introduction/info/reviews bar with instant anchors and manual scroll tracking. Existing ReviewFeed supports embedded non-scrolling rendering. Focused sticky test and 12 activity/auth/embed tests passed; analyzer clean. Reference: https://www.musinsa.com/products/4038035
